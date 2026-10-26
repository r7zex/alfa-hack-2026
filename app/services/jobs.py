"""PostgreSQL queue with short transactions, fencing leases and bounded retries."""
import asyncio
import json
import logging
from time import monotonic
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select,or_,and_
from starlette.concurrency import run_in_threadpool
from app.models.loan_application import LoanApplication
from app.models.business import Business
from app.models.operations import PipelineJob,SourceSetting,ModelPrediction,DecisionRecord
from app.models.pipeline import ProcessingRun
from app.services.operations import upsert,utcnow,aware,ensure_tasks
from app.services.mock_sources import SOURCES,MockAdapter,SourceFailure
from app.services.financial_features import FinancialFeaturesProvider
from app.services.policy_rules import active_rules,assess
from app.services.pipeline import locked,event,documents_for
from app.services.offers import create_offer
from ml.imported_lightgbm import score_positive_class,ImportedModelError

STAGES=('data_check','enrichment','enrichment','enrichment','enrichment','enrichment','scoring','decision')
SOURCE_STAGES={1:'egrul',2:'fns',3:'bki',4:'financials',5:'turnover'}
TERMINAL={'approved','counter_offer','rejected','needs_info','escalated','pending','offer_accepted','signed','disbursed','offer_declined','cancelled'}


async def enqueue(db,row):
    row.submission+=1
    job=PipelineJob(id=uuid4(),application_id=row.id,submission=row.submission,status='PENDING',stage=0,attempts=0,snapshot={},run_after=utcnow())
    db.add(job)
    return job


async def claim(factory,settings):
    async with factory() as db:
        now=utcnow()
        job=await db.scalar(select(PipelineJob).where(or_(
            and_(PipelineJob.status=='PENDING',PipelineJob.run_after<=now),
            and_(PipelineJob.status=='RUNNING',PipelineJob.lease_until<now)))
            .order_by(PipelineJob.run_after,PipelineJob.id).with_for_update(skip_locked=True).limit(1))
        if not job:return None
        if job.attempts>=settings.worker_max_attempts:
            row=await locked(db,job.application_id,admin=True)
            job.status='FAILED';job.last_error=job.last_error or 'Worker lease expired; attempts exhausted';job.completed_at=now
            if row.status not in TERMINAL:await event(db,row,None,'processing_error',job.last_error)
            await db.commit()
            return None
        job.status='RUNNING';job.attempts+=1;job.lease_token=str(uuid4());job.lease_until=now+timedelta(seconds=settings.worker_lease_seconds)
        await db.commit()
        return job.id,job.lease_token


async def owned_job(db,id_,token):
    job=await db.scalar(select(PipelineJob).where(PipelineJob.id==id_).with_for_update().execution_options(populate_existing=True))
    if not job or job.status!='RUNNING' or job.lease_token!=token or aware(job.lease_until)<=utcnow():
        return None
    return job


async def execute(factory,id_,token,settings):
    while True:
        # Snapshot inputs and commit before any adapter or model call.
        async with factory() as db:
            job=await owned_job(db,id_,token)
            if not job:return
            row=await locked(db,job.application_id,admin=True)
            if row.submission!=job.submission or row.status in TERMINAL:
                job.status='DONE';job.completed_at=utcnow();await db.commit();return
            stage=job.stage
            if stage>=len(STAGES):return
            if stage==0 and not job.snapshot.get('rules'):
                version,rules=await active_rules(db)
                job.snapshot={'rules':rules,'rules_version':version,'checks':[]}
            snapshot=dict(job.snapshot)
            if row.status!=STAGES[stage]:
                await event(db,row,None,STAGES[stage],{
                    'data_check':'Проверяем полноту заявки','enrichment':'Получаем синтетические сведения',
                    'scoring':'Выполняем ML-инференс и оцениваем финансы','decision':'Формируем решение по демонстрационным правилам'}[STAGES[stage]])
            data={k:getattr(row,k) for k in ('mock_scenario','revenue','expenses','debt_payment')}
            data['id']=str(row.id)
            config={}
            source=SOURCE_STAGES.get(stage)
            if source:
                setting=await db.get(SourceSetting,source)
                if setting:config={'mode':setting.mode,'open':bool(setting.open_until and aware(setting.open_until)>utcnow())}
            features,provenance=(None,{})
            if stage==6:features,provenance=await FinancialFeaturesProvider().collect(db,row.business_id)
            attempt=job.attempts
            await db.commit()
        try:
            output=None
            if settings.pipeline_step_delay_seconds:await asyncio.sleep(settings.pipeline_step_delay_seconds)
            if source:output=await MockAdapter(source,config,settings.integration_timeout_seconds).get(data,attempt)
            elif stage==6:
                if features is None:output={'available':False,'reason':'compatible_features_missing'}
                else:
                    try:output={'available':True,**await run_in_threadpool(score_positive_class,features)}
                    except ImportedModelError as exc:output={'available':False,'reason':str(exc)}
            async with factory() as db:
                job=await owned_job(db,id_,token)
                if not job:return
                row=await locked(db,job.application_id,admin=True)
                if row.submission!=job.submission:return
                snapshot=dict(job.snapshot)
                if stage==0:
                    docs=await documents_for(db,row)
                    business=await db.get(Business,row.business_id)
                    required={'statement','tax' if business.type.value=='ip' else 'accounts'}
                    if row.product_id=='equipment':required.add('invoice')
                    missing=sorted(required-{d.document_type for d in docs})
                    if missing:
                        await ensure_tasks(db,row,missing)
                        await event(db,row,None,'needs_info','Не хватает обязательных документов')
                        job.status='DONE';job.completed_at=utcnow();job.stage=1
                        await db.commit();return
                if source:
                    snapshot['checks']=[*snapshot.get('checks',[]),output]
                    setting=await db.get(SourceSetting,source)
                    if setting:setting.failures=0;setting.open_until=None
                    await event(db,row,None,row.status,'Проверка '+source+': '+output['status'],{'source':source,'outcome':output['status']})
                if stage==6:
                    db.add(ModelPrediction(application_id=row.id,submission=row.submission,
                          model_sha256=output.get('artifact_sha256'),features=features or {},provenance=provenance,result=output))
                    snapshot['ml']=output
                    await event(db,row,None,row.status,'ML-score класса 1 сохранён' if output['available'] else 'ML недоступен; используется отдельная демонстрационная политика')
                if stage==7:
                    business=await db.get(Business,row.business_id)
                    docs=await documents_for(db,row)
                    risk,policy=assess(row,snapshot.get('checks',[]),docs,business,snapshot['rules'],snapshot['rules_version'])
                    db.add(ProcessingRun(application_id=row.id,application_version=row.version,checks=snapshot.get('checks',[]),risk=risk,policy=policy))
                    recommendation=policy['recommendation'];reason='; '.join(policy['reasons'])
                    target='pending'
                    if recommendation=='recommend_rejection':target='rejected'
                    elif recommendation=='request_info':
                        target='needs_info';await ensure_tasks(db,row,policy['missing_documents'],reason)
                    elif row.decision_mode=='auto' and row.amount<=snapshot['rules']['auto_limit'] and policy['age_months'] is not None:
                        target='counter_offer' if recommendation=='alternative_terms' else 'approved'
                        await create_offer(db,row,amount=policy['alternative_amount'] if target=='counter_offer' else row.amount,
                                           reason=reason,valid_days=snapshot['rules']['offer_valid_days'])
                    if target=='pending':reason='Заявка направлена кредитному специалисту. '+reason
                    await event(db,row,None,target,reason,{'rules_version':snapshot['rules_version'],'automatic':target!='pending','recommendation':recommendation})
                    db.add(DecisionRecord(application_id=row.id,actor_id=None,rules_version=snapshot['rules_version'],action=target,reason=reason,terms={}))
                    job.status='DONE';job.completed_at=utcnow()
                job.snapshot=snapshot;job.stage=stage+1;job.lease_until=utcnow()+timedelta(seconds=settings.worker_lease_seconds)
                await db.commit()
                if stage==7:return
        except Exception as exc:
            # Persist a bounded diagnostic; no request body, credentials or file contents.
            async with factory() as db:
                job=await owned_job(db,id_,token)
                if not job:return
                row=await locked(db,job.application_id,admin=True)
                diagnostic=str(exc)[:1000] if isinstance(exc,SourceFailure) else type(exc).__name__+': processing stage failed'
                job.last_error=diagnostic
                if source and (data.get('mock_scenario')=='success' or config.get('mode','success')!='success'):
                    await db.execute(upsert(db,SourceSetting).values(name=source,mode=config.get('mode','success'),failures=0).on_conflict_do_nothing())
                    setting=await db.get(SourceSetting,source)
                    setting.failures+=1
                    if setting.failures>=settings.worker_max_attempts:setting.open_until=utcnow()+timedelta(seconds=15)
                if job.attempts>=settings.worker_max_attempts:
                    job.status='FAILED';job.completed_at=utcnow()
                    await event(db,row,None,'processing_error','Техническая ошибка: '+diagnostic,{'job_id':str(job.id),'attempts':job.attempts,'source':source,'outcome':'error'})
                else:
                    job.status='PENDING';job.run_after=utcnow()+timedelta(seconds=min(30,settings.worker_backoff_seconds*2**(job.attempts-1)))
                    await event(db,row,None,row.status,'Повтор проверки: '+diagnostic,{'attempt':job.attempts,'source':source,'outcome':'error'})
                job.lease_token=None;job.lease_until=None
                await db.commit()
            return


async def run_one(factory,settings):
    claimed=await claim(factory,settings)
    if not claimed:return False
    started=monotonic()
    await execute(factory,*claimed,settings)
    async with factory() as db:
        job=await db.get(PipelineJob,claimed[0])
        logging.getLogger('worker').info(json.dumps({'event':'job_attempt_finished','job_id':str(job.id),
            'application_id':str(job.application_id),'stage':job.stage,'status':job.status,'attempts':job.attempts,
            'duration_ms':round((monotonic()-started)*1000,2)}))
    return True
