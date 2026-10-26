"""Kill and recover only the explicitly selected disposable worker container."""
import json
import os
import subprocess
import hashlib
from time import monotonic,sleep
import pytest
from e2e_product import browser,pages,create_ui,status,workflow

PROJECT=os.getenv('E2E_DOCKER_PROJECT','')
pytestmark=pytest.mark.skipif(os.getenv('E2E_ALLOW_WORKER_CRASH')!='1' or not PROJECT,
                            reason='Explicit isolated worker-crash environment required')


def test_actual_worker_crash_and_lease_recovery(pages):
    assert PROJECT.startswith('delora-'),'Use a separate Delora QA project'
    ids=subprocess.check_output(['docker','ps','-aq','--filter',f'label=com.docker.compose.project={PROJECT}',
                                 '--filter','label=com.docker.compose.service=worker'],text=True).split()
    assert len(ids)==1,'Exactly one disposable worker required'
    worker=ids[0]
    config=json.loads(subprocess.check_output(['docker','inspect',worker],text=True))[0]
    env=dict(item.split('=',1) for item in config['Config']['Env'])
    assert int(env.get('WORKER_LEASE_SECONDS','60'))<=15,'Set a short lease only for this isolated test'
    subprocess.run(['docker','stop','-t','2',worker],check=True,capture_output=True)
    try:
        page=pages('auto');id_=create_ui(page)
        assert workflow(page,id_)['status']=='submitted'
        subprocess.run(['docker','start',worker],check=True,capture_output=True)
        until=monotonic()+30
        while True:
            job=workflow(page,id_)['jobs'][-1]
            if job['status']=='RUNNING' and 1<=job['stage']<=5:break
            assert monotonic()<until,job
            sleep(.05)
        subprocess.run(['docker','kill','--signal','KILL',worker],check=True,capture_output=True)
        subprocess.run(['docker','start',worker],check=True,capture_output=True)
        data=status(page,id_,'approved',timeout=80)
        assert data['jobs'][-1]['attempts']==2
        assert len(data['ml'])==len(data['offers'])==1
        assert len({h['version'] for h in data['history']})==len(data['history'])
    finally:
        subprocess.run(['docker','start',worker],check=True,capture_output=True)


@pytest.mark.skipif(os.getenv('E2E_ALLOW_SERVICE_RESTART')!='1',reason='Explicit disposable app/DB restart required')
def test_database_and_app_restart_preserves_cookie_pdf_and_workflow(pages):
    from e2e_product import BASE
    page=pages('completed')
    applications=page.request.get(BASE+'/api/applications').json()
    id_=next(a['id'] for a in applications if a['status']=='disbursed')
    before=workflow(page,id_);doc_id=before['documents'][0]['id']
    content=page.request.get(BASE+f'/api/documents/{doc_id}/content').body()
    for service in ['db','app']:
        ids=subprocess.check_output(['docker','ps','-aq','--filter',f'label=com.docker.compose.project={PROJECT}',
                                     '--filter',f'label=com.docker.compose.service={service}'],text=True).split()
        assert len(ids)==1
        subprocess.run(['docker','restart',ids[0]],check=True,capture_output=True)
    until=monotonic()+90
    while True:
        try:
            if page.request.get(BASE+'/ready',timeout=2000).ok:break
        except Exception:pass
        assert monotonic()<until,'API did not recover after disposable restart'
        sleep(.5)
    assert workflow(page,id_)==before
    after=page.request.get(BASE+f'/api/documents/{doc_id}/content');assert after.ok
    assert hashlib.sha256(after.body()).digest()==hashlib.sha256(content).digest()
    page.goto(BASE+'/#/loans')
    from playwright.sync_api import expect
    expect(page.locator('h1')).to_have_text('Мои кредиты',timeout=15000)
    expect(page.locator('.loan-card')).not_to_have_count(0,timeout=15000)
