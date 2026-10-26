"""Real model, durable worker and end-to-end scoped product operations."""
import asyncio
from datetime import date,timedelta
from decimal import Decimal
from uuid import UUID,uuid4
from concurrent.futures import ThreadPoolExecutor
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,update,func
from test_auth import auth_env,signup,csrf,run_db
from test_pipeline import create,upload,flow,decision,action,CONSENT,sign_in_admin
from app.main import app
from app.models.auth import Business,User
from app.models.operations import (PipelineJob,FinancialProfile,ModelPrediction,SourceSetting,ApplicationTask,Notification,
                                 SigningChallenge,LoanAccount,StreamLease,PolicyVersion,SystemSetting)
from app.services.jobs import run_one,claim
from app.services.financial_features import STABLE,PROVENANCE
from app.services.loans import schedule
from app.services.operations import utcnow
from app.services.policy_rules import RuleDefinition


@pytest.fixture
def product_env(auth_env):
    factory,settings=auth_env
    settings.pipeline_async_enabled=True;settings.signing_require_code=True
    settings.demo_auth_enabled=True;settings.demo_signing_code_visible=True
    settings.worker_backoff_seconds=0
    return factory,settings


def setup_business(client,factory,*,profile=True):
    assert signup(client).status_code==201
    id_=client.get('/api/auth/me').json()['business_id']
    async def prepare(db):
        business=await db.get(Business,id_);business.registration=date(2020,1,1)
        if profile:db.add(FinancialProfile(business_id=id_,kind='synthetic_stable',features=STABLE,provenance=PROVENANCE))
        await db.commit()
    run_db(factory,prepare)


def process(factory,settings):assert asyncio.run(run_one(factory,settings)) is True


def submit_async(client,id_):
    r=client.post(f'/api/applications/{id_}/submit',headers=csrf(client),json=CONSENT)
    assert r.status_code==200,r.text
    return r


def ready(client,factory,settings,**changes):
    id_=create(client,**{'decisionMode':'auto',**changes})
    upload(client,id_,'statement');upload(client,id_,'accounts')
    if changes.get('productId')=='equipment':upload(client,id_,'invoice')
    assert submit_async(client,id_).json()['status']=='submitted'
    process(factory,settings)
    return id_


def test_real_model_auto_loan_otp_notifications_and_schedule(product_env):
    factory,settings=product_env
    with TestClient(app) as client,TestClient(app) as other:
        setup_business(client,factory);signup(other,'ip','other@example.com')
        id_=ready(client,factory,settings)
        data=flow(client,id_)
        assert data['status']=='approved' and data['jobs'][-1]['status']=='DONE'
        assert data['ml'][0]['result']['available'] is True and len(data['ml'][0]['features'])==24
        assert data['ml'][0]['provenance']['synthetic'] is True
        assert data['ml'][0]['result']['classification'] is None
        assert client.get(f'/api/applications/{id_}/ml').status_code==200
        assert other.get(f'/api/applications/{id_}/ml').status_code==404
        offer=data['offers'][-1]
        assert action(client,id_,offer,'accept').status_code==200
        assert action(client,id_,offer,'sign').status_code==422
        issued=client.post(f'/api/applications/{id_}/signing-code',headers=csrf(client)).json()
        challenge_id=issued['challenge_id'];code=issued['demo_code']
        assert code and len(code)==6
        assert action(client,id_,offer,'sign',challenge_id=challenge_id,code='000000' if code!='000000' else '111111').status_code==422
        async def inspect_code(db):
            row=await db.get(SigningChallenge,UUID(challenge_id));assert row.attempts==1 and row.code_hash!=code
        run_db(factory,inspect_code)
        assert action(client,id_,offer,'sign',challenge_id=challenge_id,code=code).status_code==200
        assert action(client,id_,offer,'sign',challenge_id=challenge_id,code=code).status_code==200
        assert action(client,id_,offer,'disburse').status_code==200
        assert action(client,id_,offer,'disburse').status_code==200
        loans=client.get('/api/loans').json();assert len(loans)==1
        loan=loans[0];plan=loan['schedule']
        assert len(plan)==12 and Decimal(plan[-1]['closing'])==0
        assert sum(Decimal(p['principal']) for p in plan)==Decimal(1000000)
        assert other.get('/api/loans/'+loan['id']).status_code==404
        csv=client.get('/api/loans/'+loan['id']+'/schedule.csv')
        assert csv.status_code==200 and csv.content.startswith(b'\xef\xbb\xbf')
        notes=client.get('/api/notifications').json()
        keys=[n['event_key'] for n in notes['items']];assert len(keys)==len(set(keys))
        assert client.post('/api/notifications/read-all',headers=csrf(client)).status_code==200
        assert client.get('/api/notifications').json()['unread']==0
        assert other.delete('/api/notifications/'+notes['items'][0]['id'],headers=csrf(other)).status_code==404


def test_tasks_chat_isolation_and_preparer_signature(product_env):
    factory,settings=product_env
    with TestClient(app) as client,TestClient(app) as admin,TestClient(app) as preparer:
        setup_business(client,factory);sign_in_admin(admin,settings)
        id_=create(client,decisionMode='auto');submit_async(client,id_);process(factory,settings)
        tasks=flow(client,id_)['tasks'];assert len(tasks)==2
        assert client.post(f'/api/applications/{id_}/submit',headers=csrf(client),json=CONSENT).status_code==409
        upload(client,id_,'statement');upload(client,id_,'accounts')
        assert all(t['status']=='DONE' for t in flow(client,id_)['tasks'])
        invite=client.post('/api/team/invitations',headers=csrf(client),json={'email':'preparer@example.com'})
        assert invite.status_code==201
        payload={'email':'preparer@example.com','password':'Preparing-123!','token':invite.json()['token']}
        assert preparer.post('/api/team/join',json=payload).status_code==201
        assert preparer.post('/api/team/join',json=payload).status_code==422
        assert preparer.post('/api/auth/login',json={'email':payload['email'],'password':payload['password']}).status_code==200
        assert preparer.get('/api/auth/me').json()['can_sign'] is False
        assert preparer.get(f'/api/applications/{id_}/workflow').status_code==200
        request_id=str(uuid4());message={'request_id':request_id,'text':'<script>alert(1)</script> Синтетический вопрос банку'}
        r=preparer.post(f'/api/applications/{id_}/messages',headers=csrf(preparer),json=message)
        assert r.status_code==201
        assert preparer.post(f'/api/applications/{id_}/messages',headers=csrf(preparer),json=message).json()['id']==r.json()['id']
        assert admin.get(f'/api/applications/{id_}/messages').json()['unread']==1
        assert admin.post(f'/api/applications/{id_}/messages/read',headers=csrf(admin)).status_code==200
        assert admin.get(f'/api/applications/{id_}/messages').json()['unread']==0
        submit_async(preparer,id_);process(factory,settings)
        offer=flow(client,id_)['offers'][-1]
        assert action(preparer,id_,offer,'accept').status_code==403
        assert client.post('/api/analyst/applications/'+id_+'/assign',headers=csrf(client)).status_code==403
        assert client.get('/api/analyst/analytics').status_code==403
        assert preparer.post('/api/team/invitations',headers=csrf(preparer),json={'email':'x@example.com'}).status_code==403
        assert action(client,id_,offer,'accept').status_code==200
        assert preparer.post(f'/api/applications/{id_}/signing-code',headers=csrf(preparer)).status_code==403


def test_escalation_counter_expiry_role_matrix_and_metrics(product_env):
    factory,settings=product_env
    with TestClient(app) as client,TestClient(app) as underwriter,TestClient(app) as approver:
        setup_business(client,factory)
        for who,role in [(underwriter,'underwriter'),(approver,'approver')]:
            assert who.post('/api/auth/demo',json={'account':role}).status_code==200
        id_=ready(client,factory,settings,productId='equipment',amount=10000000,months=36,revenue=5000000,expenses=1000000)
        assert flow(client,id_)['status']=='pending'
        assert underwriter.post(f'/api/analyst/applications/{id_}/assign',headers=csrf(underwriter)).status_code==200
        assert decision(underwriter,id_).status_code==403
        assert decision(underwriter,id_,'escalated').status_code==200
        assert decision(underwriter,id_).status_code==403
        assert approver.post(f'/api/analyst/applications/{id_}/assign',headers=csrf(approver)).status_code==200
        assert decision(approver,id_,'counter_offer',alternativeAmount=9000000,months=48,annual_rate=19.555,product_id='equipment').status_code==422
        r=decision(approver,id_,'counter_offer',alternativeAmount=9000000,months=48,annual_rate=19.5,product_id='equipment',valid_days=1)
        assert r.status_code==200,r.text
        offer=flow(client,id_)['offers'][-1]
        assert offer['months']==48 and float(offer['annual_rate'])==19.5
        async def expire(db):
            from app.models.pipeline import CreditOffer
            row=await db.get(CreditOffer,UUID(offer['id']));row.expires_at=utcnow()-timedelta(seconds=1);await db.commit()
        run_db(factory,expire)
        assert action(client,id_,offer,'accept').status_code==409
        assert underwriter.put('/api/admin/integrations/bki',headers=csrf(underwriter),json={'mode':'unavailable'}).status_code==403
        metrics=approver.get('/api/analyst/analytics').json()
        assert metrics['total']==1 and metrics['approved']==1
        assert next(x for x in metrics['funnel'] if x['stage']=='Решение')['count']==1


def test_worker_retry_recovery_and_missing_ml_fallback(product_env):
    factory,settings=product_env
    with TestClient(app) as client,TestClient(app) as admin:
        setup_business(client,factory,profile=False);sign_in_admin(admin,settings)
        assert admin.put('/api/admin/integrations/bki',headers=csrf(admin),json={'mode':'unavailable'}).status_code==200
        id_=create(client,decisionMode='auto');upload(client,id_,'statement');upload(client,id_,'accounts');submit_async(client,id_)
        for _ in range(3):process(factory,settings)
        failed=flow(client,id_);assert failed['status']=='processing_error'
        assert failed['jobs'][-1]['attempts']==3 and 'bki' in failed['jobs'][-1]['last_error']
        assert admin.put('/api/admin/integrations/bki',headers=csrf(admin),json={'mode':'success'}).status_code==200
        assert client.post(f'/api/applications/{id_}/retry',headers=csrf(client),json={}).status_code==200
        process(factory,settings)
        good=flow(client,id_);assert good['status']=='approved'
        assert good['ml'][-1]['result']['available'] is False
        assert len(good['offers'])==1
        assert good['ml'][-1]['features']=={}


@pytest.mark.parametrize('overdraft',[False,True])
def test_decimal_schedule_and_calendar_boundaries(overdraft):
    plan=schedule(1000000,19.5,24,date(2024,1,31),overdraft=overdraft)
    assert plan[0]['date']=='2024-02-29'
    assert sum(Decimal(r['principal']) for r in plan)==Decimal(1000000)
    for r in plan:
        assert Decimal(r['payment'])==Decimal(r['interest'])+Decimal(r['principal'])
        assert Decimal(r['closing'])==Decimal(r['opening'])-Decimal(r['principal'])
    if overdraft:assert all(Decimal(r['principal'])==0 for r in plan[:-1])


def test_expired_worker_lease_recovers_without_duplicate_results(product_env):
    factory,settings=product_env
    with TestClient(app) as client:
        setup_business(client,factory)
        id_=create(client,decisionMode='auto');upload(client,id_,'statement');upload(client,id_,'accounts');submit_async(client,id_)
        claimed=asyncio.run(claim(factory,settings));assert claimed
        async def crash(db):
            job=await db.get(PipelineJob,claimed[0]);job.lease_until=utcnow()-timedelta(seconds=2);await db.commit()
        run_db(factory,crash);process(factory,settings)
        data=flow(client,id_);assert data['status']=='approved' and len(data['ml'])==1 and len(data['offers'])==1
        assert data['jobs'][0]['attempts']==2


@pytest.mark.skipif(not os.environ.get('TEST_AUTH_DATABASE_URL','').startswith('postgresql'),reason='PostgreSQL SKIP LOCKED concurrency')
def test_parallel_workers_claim_and_fence_one_job(product_env):
    factory,settings=product_env
    with TestClient(app) as client:
        setup_business(client,factory)
        id_=create(client,decisionMode='auto');upload(client,id_,'statement');upload(client,id_,'accounts');submit_async(client,id_)
        async def parallel():return await asyncio.gather(*[run_one(factory,settings) for _ in range(4)])
        results=asyncio.run(parallel());assert results.count(True)==1
        data=flow(client,id_);assert len(data['offers'])==1 and len(data['ml'])==1


def test_stream_auth_ownership_and_per_user_limit(product_env):
    factory,settings=product_env
    with TestClient(app) as client,TestClient(app) as other,TestClient(app) as guest:
        setup_business(client,factory);signup(other,'ip','stream-other@example.com')
        id_=create(client);user_id=client.get('/api/auth/me').json()['id']
        assert guest.get(f'/api/applications/{id_}/stream').status_code==401
        assert other.get(f'/api/applications/{id_}/stream').status_code==404
        async def fill(db):
            for _ in range(3):db.add(StreamLease(user_id=user_id,expires_at=utcnow()+timedelta(seconds=50)))
            await db.commit()
        run_db(factory,fill)
        assert client.get(f'/api/applications/{id_}/stream').status_code==429
        assert other.get(f'/api/applications/{id_}/messages').status_code==404
        assert other.get(f'/api/applications/{id_}/tasks').status_code==404
        assert guest.get('/api/admin/audit').status_code==401
        assert client.get('/api/admin/audit').status_code==403


def test_otp_attempt_lock_expiry_and_hidden_code(product_env):
    factory,settings=product_env
    with TestClient(app) as client:
        setup_business(client,factory);id_=ready(client,factory,settings);offer=flow(client,id_)['offers'][-1]
        assert action(client,id_,offer,'accept').status_code==200
        issued=client.post(f'/api/applications/{id_}/signing-code',headers=csrf(client)).json()
        wrong='000000' if issued['demo_code']!='000000' else '111111'
        for _ in range(settings.signing_code_max_attempts):
            assert action(client,id_,offer,'sign',challenge_id=issued['challenge_id'],code=wrong).status_code==422
        assert action(client,id_,offer,'sign',challenge_id=issued['challenge_id'],code=issued['demo_code']).status_code==409
        async def release(db):
            row=await db.get(SigningChallenge,UUID(issued['challenge_id']));row.created_at=utcnow()-timedelta(seconds=11);await db.commit()
        run_db(factory,release);settings.demo_signing_code_visible=False
        hidden=client.post(f'/api/applications/{id_}/signing-code',headers=csrf(client)).json();assert hidden['demo_code'] is None
        async def expire(db):
            row=await db.get(SigningChallenge,UUID(hidden['challenge_id']));row.expires_at=utcnow()-timedelta(seconds=1);await db.commit()
        run_db(factory,expire)
        assert action(client,id_,offer,'sign',challenge_id=hidden['challenge_id'],code=wrong).status_code==409
        assert flow(client,id_)['status']=='offer_accepted'


def test_rule_changes_affect_finances_but_not_captured_jobs_and_are_audited(product_env):
    factory,settings=product_env
    from app.services.jobs import execute
    from app.services.policy_rules import active_rules
    with TestClient(app) as client,TestClient(app) as admin:
        setup_business(client,factory);sign_in_admin(admin,settings)
        definition=RuleDefinition(max_debt_burden=.8,min_cash_buffer=0).model_dump()
        published=admin.post('/api/admin/rules',headers=csrf(admin),json=definition);assert published.status_code==201
        id_=create(client,decisionMode='auto',revenue=200000,expenses=40000,debtPayment=0)
        upload(client,id_,'statement');upload(client,id_,'accounts');submit_async(client,id_)
        job_id,token=asyncio.run(claim(factory,settings))
        async def capture(db):
            version,rules=await active_rules(db);job=await db.get(PipelineJob,job_id)
            job.snapshot={'rules':rules,'rules_version':version,'checks':[]};await db.commit()
        run_db(factory,capture)
        definition['max_debt_burden']=.2
        assert admin.post('/api/admin/rules',headers=csrf(admin),json=definition).status_code==201
        asyncio.run(execute(factory,job_id,token,settings))
        first=flow(client,id_);assert first['status']=='approved'
        assert first['assessments'][-1]['policy']['version']==published.json()['version']
        second=ready(client,factory,settings,revenue=200000,expenses=40000,debtPayment=0)
        assert flow(client,second)['status']=='counter_offer'
        audit=admin.get('/api/admin/audit').json();assert sum(r['action']=='publish_rules' for r in audit)==2


def test_stale_worker_token_cannot_commit_after_reclaim(product_env):
    factory,settings=product_env
    from app.services.jobs import execute
    with TestClient(app) as client:
        setup_business(client,factory)
        id_=create(client,decisionMode='auto');upload(client,id_,'statement');upload(client,id_,'accounts');submit_async(client,id_)
        first=asyncio.run(claim(factory,settings))
        async def expire(db):
            row=await db.get(PipelineJob,first[0]);row.lease_until=utcnow()-timedelta(seconds=1);await db.commit()
        run_db(factory,expire);second=asyncio.run(claim(factory,settings));assert second[1]!=first[1]
        asyncio.run(execute(factory,*first,settings));assert flow(client,id_)['status']=='submitted'
        asyncio.run(execute(factory,*second,settings));assert flow(client,id_)['status']=='approved'


def test_historical_issuance_gets_one_immutable_calendar_schedule(product_env):
    factory,settings=product_env
    from app.services.maintenance import maintain
    from app.models.pipeline import DemoDisbursement
    from sqlalchemy import delete
    with TestClient(app) as client:
        setup_business(client,factory);id_=ready(client,factory,settings);offer=flow(client,id_)['offers'][-1]
        assert action(client,id_,offer,'accept').status_code==200
        code=client.post(f'/api/applications/{id_}/signing-code',headers=csrf(client)).json()
        assert action(client,id_,offer,'sign',challenge_id=code['challenge_id'],code=code['demo_code']).status_code==200
        async def fail_source(db):
            db.add(SourceSetting(name='issuance',mode='unavailable'));await db.commit()
        run_db(factory,fail_source)
        assert action(client,id_,offer,'disburse').status_code==503
        assert flow(client,id_)['status']=='signed' and not client.get('/api/loans').json()
        async def restore(db):
            source=await db.get(SourceSetting,'issuance');source.mode='success';await db.commit()
        run_db(factory,restore)
        assert action(client,id_,offer,'disburse').status_code==200
        issued=flow(client,id_);assert issued['history'][-1]['details']['source_result']['synthetic'] is True
        async def historical(db):
            await db.execute(delete(LoanAccount))
            issuance=await db.scalar(select(DemoDisbursement));issuance.created_at=utcnow().replace(year=2024,month=1,day=31)
            await db.commit()
        run_db(factory,historical)
        asyncio.run(maintain(factory));asyncio.run(maintain(factory))
        loans=client.get('/api/loans').json();assert len(loans)==1 and loans[0]['schedule'][0]['date']=='2024-02-29'


def test_stale_review_cannot_decide_resubmitted_financials(product_env):
    factory,settings=product_env
    with TestClient(app) as client,TestClient(app) as bank:
        setup_business(client,factory);sign_in_admin(bank,settings)
        id_=ready(client,factory,settings,decisionMode='manual')
        reviewed=flow(bank,id_)['version']
        assert decision(bank,id_,'needs_info').status_code==200
        for task in flow(client,id_)['tasks']:
            if task['status']=='OPEN':
                assert client.post(f'/api/applications/{id_}/tasks/{task["id"]}/complete',headers=csrf(client),json={'answer':'Данные уточнены'}).status_code==200
        assert client.patch(f'/api/applications/{id_}',headers=csrf(client),json={'revenue':1800000}).status_code==200
        submit_async(client,id_);process(factory,settings)
        stale=decision(bank,id_,expectedVersion=reviewed)
        assert stale.status_code==409 and flow(client,id_)['status']=='pending'
        assert decision(bank,id_).status_code==200
