"""Protected, event-based metrics; no frontend random data or PII metrics."""
from collections import Counter
from statistics import median,mean
from sqlalchemy import select,func
from fastapi import APIRouter
from app.api.operations import Bank,csv_response
from app.dependencies import Db
from app.models.loan_application import LoanApplication
from app.models.pipeline import ApplicationEvent,DemoDisbursement
from app.models.operations import PipelineJob,DecisionRecord,WorkerHeartbeat
from app.services.operations import aware,utcnow

router=APIRouter(prefix='/api/analyst',tags=['Bank analytics'])


async def metrics_for(db):
    apps=list((await db.scalars(select(LoanApplication))).all())
    events=list((await db.scalars(select(ApplicationEvent).order_by(ApplicationEvent.created_at,ApplicationEvent.version))).all())
    issued=list((await db.scalars(select(DemoDisbursement))).all())
    jobs=list((await db.scalars(select(PipelineJob))).all())
    by_status=Counter(a.status for a in apps);by_product=Counter(a.product_id for a in apps)
    reached={};submitted={};decided={}
    for e in events:
        reached.setdefault(e.application_id,set()).add(e.new_status)
        if e.new_status=='submitted':submitted.setdefault(e.application_id,e.created_at)
    # Credit decisions only: request-info and routing are separate operations.
    # The event audit also covers decisions from before decision_records existed.
    for e in events:
        if e.new_status in {'approved','counter_offer','rejected'} and e.new_status!=e.old_status:
            decided.setdefault(e.application_id,e)
    for application in apps:reached.setdefault(application.id,set()).add('draft')
    durations=[max(0,(aware(d.created_at)-aware(submitted[id_])).total_seconds()) for id_,d in decided.items() if id_ in submitted]
    processing=[max(0,(aware(j.completed_at)-aware(j.created_at)).total_seconds()) for j in jobs if j.completed_at and j.status=='DONE']
    stages=[('Создание',{'draft'}),('Отправка',{'submitted'}),('Проверка',{'data_check','processing'}),
            ('Решение',{'approved','counter_offer','rejected'}),('Принятие',{'offer_accepted'}),('Подписание',{'signed'}),('Выдача',{'disbursed'})]
    return dict(total=len(apps),new=by_status['submitted'],checking=sum(by_status[s] for s in ['data_check','enrichment','scoring','decision','processing']),
                manual=by_status['pending'],escalated=by_status['escalated'],approved=by_status['approved']+by_status['counter_offer'],
                rejected=by_status['rejected'],needs_info=by_status['needs_info'],signed=by_status['signed'],disbursed=by_status['disbursed'],
                disbursed_amount=sum(i.amount for i in issued),auto_decision_share=sum(d.actor_id is None for d in decided.values())/len(decided) if decided else 0,
                median_decision_seconds=median(durations) if durations else None,mean_processing_seconds=mean(processing) if processing else None,
                technical_errors=sum(e.new_status=='processing_error' and e.old_status!='processing_error' for e in events),
                integration_error_attempts=dict(Counter(e.details['source'] for e in events if e.details.get('outcome')=='error' and e.details.get('source'))),
                by_product=dict(by_product),by_status=dict(by_status),queue=dict(Counter(j.status for j in jobs)),
                funnel=[{'stage':label,'count':sum(bool(states&targets) for states in reached.values())} for label,targets in stages],
                definitions='Доли: первое одобрение/встречное предложение/отказ на заявку с аудитом. Воронка: уникальные заявки, достигшие этапа исторически. Текущие статусы отдельно.')


@router.get('/analytics')
async def metrics(db:Db,user:Bank):return await metrics_for(db)


@router.get('/analytics.csv')
async def csv_metrics(db:Db,user:Bank):
    data=await metrics_for(db)
    return csv_response([['metric','value'],*[[k,v] for k,v in data.items() if isinstance(v,(int,float))]],'bank-metrics.csv')


@router.get('/operations')
async def operations(db:Db,user:Bank):
    latest=await db.scalar(select(func.max(WorkerHeartbeat.seen_at)))
    jobs=(await db.scalars(select(PipelineJob).where(PipelineJob.status.in_(['FAILED','PENDING','RUNNING'])).order_by(PipelineJob.created_at.desc()).limit(100))).all()
    return {'worker_healthy':bool(latest and (utcnow()-aware(latest)).total_seconds()<60),'last_heartbeat':latest,
            'jobs':[{'id':j.id,'application_id':j.application_id,'status':j.status,'stage':j.stage,'attempts':j.attempts,'last_error':j.last_error,'run_after':j.run_after} for j in jobs]}
