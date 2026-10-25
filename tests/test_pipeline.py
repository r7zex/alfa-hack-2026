"""End-to-end demo lending over real auth/SQL transactions; no live bank or LLM."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_auth import auth_env, signup, csrf, run_db
from ml_fixtures import pdf_bytes
from app.main import app
from app.models.pipeline import CreditOffer, DemoContract, DemoDisbursement

CONSENT = {'demo_data': True, 'demo_checks': True}


def create(client, **changes):
    response = client.post('/api/applications', headers=csrf(client), json={
        'productId': 'working', 'amount': 1_000_000, 'months': 12,
        'purpose': 'Закупка синтетических товаров', 'revenue': 1_500_000,
        'expenses': 700_000, 'debtPayment': 10_000, **changes})
    assert response.status_code == 201, response.text
    return response.json()['id']


def upload(client, id_, kind):
    response = client.post('/api/documents/' + id_, headers=csrf(client),
                           data={'document_type': kind}, files={'file': (kind + '.pdf', pdf_bytes(), 'application/pdf')})
    assert response.status_code == 201, response.text
    return response.json()['id']


def submit(client, id_):
    response = client.post(f'/api/applications/{id_}/submit', headers=csrf(client), json=CONSENT)
    assert response.status_code == 200, response.text
    return response.json()


def flow(client, id_):
    response = client.get(f'/api/applications/{id_}/workflow')
    assert response.status_code == 200, response.text
    return response.json()


def decision(admin, id_, status='approved', **changes):
    return admin.post(f'/api/analyst/applications/{id_}/decision', headers=csrf(admin),
                      json={'status': status, 'comment': 'Синтетическое решение аналитика', **changes})


def action(client, id_, offer, operation, **changes):
    return client.post(f'/api/applications/{id_}/offer/{operation}', headers=csrf(client), json={
        'offer_id': offer['id'], 'acknowledged': True, 'contract_sha256': offer['contract_sha256'], **changes})


def sign_in_admin(client, settings):
    settings.demo_auth_enabled = True
    response = client.post('/api/auth/demo', json={'account': 'admin'})
    assert response.status_code == 200, response.text


@pytest.mark.parametrize('kind', ['ip', 'llc'])
def test_full_pipeline_persists_with_idempotency_and_roles(auth_env, kind):
    factory, settings = auth_env
    with TestClient(app) as client, TestClient(app) as admin, TestClient(app) as other:
        assert signup(client, kind).status_code == 201
        assert signup(other, 'llc' if kind == 'ip' else 'ip', 'other@example.com').status_code == 201
        sign_in_admin(admin, settings)
        id_ = create(client)
        assert admin.get(f'/api/applications/{id_}/workflow').status_code == 404
        doc = upload(client, id_, 'statement')
        upload(client, id_, 'tax' if kind == 'ip' else 'accounts')
        assert admin.get(f'/api/documents/{doc}/content').status_code == 404
        assert client.post(f'/api/applications/{id_}/submit', headers=csrf(client)).status_code == 422
        assert submit(client, id_)['status'] == 'pending'
        initial = flow(client, id_)
        assert initial['assessments'][-1]['policy']['recommendation'] == 'recommend_approval'
        assert submit(client, id_)['status'] == 'pending'
        assert len(flow(client, id_)['assessments']) == 1
        assert other.get(f'/api/documents/{doc}/content').status_code == 404
        assert admin.get(f'/api/documents/{doc}/content').content == client.get(f'/api/documents/{doc}/content').content
        assert other.get(f'/api/applications/{id_}/workflow').status_code == 404
        assert client.get('/api/analyst/applications').status_code == 403
        assert decision(admin, id_).status_code == 200
        assert decision(admin, id_).status_code == 409
        offer = flow(client, id_)['offers'][-1]
        assert action(client, id_, offer, 'sign').status_code == 409
        assert action(other, id_, offer, 'accept').status_code == 404
        assert action(client, id_, {**offer, 'id': str(uuid4())}, 'accept').status_code == 409
        assert action(client, id_, offer, 'accept', acknowledged=False).status_code == 422
        assert action(client, id_, offer, 'accept').status_code == 200
        assert action(client, id_, offer, 'accept').status_code == 200
        assert action(client, id_, offer, 'disburse').status_code == 409
        assert action(client, id_, offer, 'sign', contract_sha256='0' * 64).status_code == 422
        assert action(client, id_, offer, 'sign').status_code == 200
        assert action(client, id_, offer, 'sign').status_code == 200
        assert action(client, id_, offer, 'disburse').status_code == 200
        assert action(client, id_, offer, 'disburse').status_code == 200
        final = flow(client, id_)
        assert final['status'] == 'disbursed'
        assert final['contract']['acknowledgment'] is True
        assert final['offers'][-1]['consent']['terms_accepted'] is True
        assert final['disbursement']['amount'] == 1_000_000
        states = [h['new_status'] for h in final['history']]
        assert states[-7:] == ['submitted', 'processing', 'pending', 'approved', 'offer_accepted', 'signed', 'disbursed']
        assert client.post('/api/auth/logout', headers=csrf(client)).status_code == 204
        assert client.post('/api/auth/login', json={'email': 'client@example.com', 'password': 'Correct-Horse-123'}).status_code == 200
        assert flow(client, id_) == final
        async def inspect(db):
            for model in (CreditOffer, DemoContract, DemoDisbursement):
                assert await db.scalar(select(func.count()).select_from(model)) == 1
        run_db(factory, inspect)


@pytest.mark.parametrize('scenario,expected', [('missing','request_info'), ('negative','recommend_rejection'),
                                               ('unavailable','technical_error'), ('malformed','technical_error')])
def test_source_outcomes_and_recovery(auth_env, scenario, expected):
    _, settings = auth_env
    with TestClient(app) as client, TestClient(app) as admin:
        signup(client)
        sign_in_admin(admin, settings)
        id_ = create(client, mockScenario=scenario)
        upload(client,id_,'statement'); upload(client,id_,'accounts')
        submit(client,id_)
        snapshot = flow(client,id_)
        assert snapshot['assessments'][-1]['policy']['recommendation'] == expected
        assert all(c['synthetic'] and c['received_at'] for c in snapshot['assessments'][-1]['checks'])
        assert decision(admin,id_).status_code == 409
        if expected == 'technical_error':
            result = client.post(f'/api/applications/{id_}/retry',headers=csrf(client),json={'mockScenario':'success'})
            assert result.status_code == 200 and result.json()['status'] == 'pending'
        else:
            assert decision(admin,id_,'needs_info').status_code == 200
            assert client.patch(f'/api/applications/{id_}',headers=csrf(client),json={'mockScenario':'success'}).status_code == 200
            submit(client,id_)
        assert flow(client,id_)['assessments'][-1]['policy']['recommendation'] == 'recommend_approval'
        assert decision(admin,id_).status_code == 200


def test_alternative_rejection_decline_and_catalogue(auth_env):
    _, settings = auth_env
    with TestClient(app) as client, TestClient(app) as admin:
        signup(client)
        sign_in_admin(admin,settings)
        assert client.post('/api/applications',headers=csrf(client),json={'productId':'working','amount':1000000,'months':25}).status_code == 422
        rows=client.get('/api/products/recommendations',params={'purpose':'оборудование','amount':1000000,'months':36}).json()
        assert rows[0]['productId']=='equipment' and not any(r['productId']=='working' for r in rows)
        id_=create(client, amount=4_000_000,revenue=1_000_000,expenses=500_000,debtPayment=0)
        upload(client,id_,'statement'); upload(client,id_,'accounts'); submit(client,id_)
        policy=flow(client,id_)['assessments'][-1]['policy']
        assert policy['recommendation']=='alternative_terms'
        assert decision(admin,id_).status_code==422
        assert decision(admin,id_,alternativeAmount=policy['alternative_amount']).status_code==200
        offer=flow(client,id_)['offers'][-1]
        assert offer['amount'] < 4_000_000
        assert action(client,id_,offer,'decline').status_code==200
        assert action(client,id_,offer,'decline').status_code==200
        assert action(client,id_,offer,'accept').status_code==409
        rejected=create(client,revenue=100_000,expenses=200_000)
        submit(client,rejected)
        assert decision(admin,rejected,'rejected').status_code==200
        assert flow(client,rejected)['offers']==[]


def test_documents_reusable_and_draft_mutations_are_frozen(auth_env):
    _,settings=auth_env
    with TestClient(app) as client, TestClient(app) as other:
        signup(client); signup(other,'ip','second@example.com')
        doc=client.post('/api/documents',headers=csrf(client),data={'document_type':'statement'},
                        files={'file':('statement.pdf',pdf_bytes(),'application/pdf')}).json()
        id_=create(client,documentIds=[doc['id']])
        assert flow(client,id_)['documents'][0]['id']==doc['id']
        extra=upload(client,id_,'accounts')
        assert client.patch(f'/api/applications/{id_}',headers=csrf(client),json={'documentIds':[doc['id']]}).status_code==200
        assert [d['id'] for d in flow(client,id_)['documents']]==[doc['id']]
        assert other.patch('/api/applications/'+create(other),headers=csrf(other),json={'documentIds':[doc['id']]}).status_code==404
        submit(client,id_)
        assert client.patch(f'/api/applications/{id_}',headers=csrf(client),json={'amount':500000}).status_code==409
        assert client.post('/api/documents/'+id_,headers=csrf(client),files={'file':('new.pdf',pdf_bytes(),'application/pdf')}).status_code==409
        assert client.post(f'/api/applications/{id_}/offer/accept',json={'offer_id':str(uuid4())}).status_code==403


@pytest.mark.skipif(not os.environ.get('TEST_AUTH_DATABASE_URL','').startswith('postgresql'), reason='PostgreSQL row-lock concurrency test')
def test_concurrent_submit_decisions_accept_sign_and_disburse(auth_env):
    _,settings=auth_env
    with TestClient(app) as client, TestClient(app) as admin:
        signup(client);sign_in_admin(admin,settings)
        id_=create(client);upload(client,id_,'statement');upload(client,id_,'accounts')
        def parallel(who, path, body):
            cookies=dict(who.cookies); headers=csrf(who)
            def request(_):
                with TestClient(app) as isolated:
                    isolated.cookies.update(cookies)
                    return isolated.post(path,headers=headers,json=body).status_code
            with ThreadPoolExecutor(max_workers=4) as pool:
                return list(pool.map(request,range(4)))
        assert parallel(client,f'/api/applications/{id_}/submit',CONSENT)==[200]*4
        assert len(flow(client,id_)['assessments'])==1
        statuses=parallel(admin,f'/api/analyst/applications/{id_}/decision',{'status':'approved','comment':'Параллельный запрос'})
        assert statuses.count(200)==1 and statuses.count(409)==3
        offer=flow(client,id_)['offers'][-1]
        for op in ['accept','sign','disburse']:
            assert parallel(client,f'/api/applications/{id_}/offer/{op}',{'offer_id':offer['id'],'acknowledged':True,'contract_sha256':offer['contract_sha256']})==[200]*4
        final=flow(client,id_)
        for status in ['approved','offer_accepted','signed','disbursed']:
            assert len([h for h in final['history'] if h['new_status']==status])==1


def test_legacy_approval_can_be_revalidated_without_fabricating_old_terms(auth_env):
    factory, settings = auth_env
    from sqlalchemy import update
    from app.models.loan_application import LoanApplication
    from uuid import UUID
    with TestClient(app) as client, TestClient(app) as admin:
        signup(client); sign_in_admin(admin,settings)
        id_=create(client)
        async def legacy(db):
            await db.execute(update(LoanApplication).where(LoanApplication.id==UUID(id_)).values(status='approved'))
            await db.commit()
        run_db(factory,legacy)
        assert flow(client,id_)['offers']==[]
        assert decision(admin,id_,'needs_info').status_code==200
        upload(client,id_,'statement');upload(client,id_,'accounts');submit(client,id_)
        assert decision(admin,id_).status_code==200
        assert flow(client,id_)['offers'][-1]['version']==1
        assert decision(admin,id_,'needs_info').status_code==409
