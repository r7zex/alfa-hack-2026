"""Real UI acceptance A–H. Requires a seeded, isolated Compose database.

E2E_BASE_URL=http://127.0.0.1:8000 pytest -q tests/e2e_product.py
Set E2E_QWEN=1 only when the real optional Qwen service is enabled.
No API mutation shortcuts: applications, uploads and decisions use rendered UI.
"""
import os
from pathlib import Path
from time import monotonic,sleep
import pytest
from playwright.sync_api import sync_playwright,expect

BASE=os.getenv('E2E_BASE_URL','').rstrip('/')
pytestmark=pytest.mark.skipif(not BASE,reason='Explicit isolated E2E_BASE_URL required')
SHOTS=Path(os.getenv('E2E_SCREENSHOTS','/tmp/delora-e2e'))


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as engine:
        browser=engine.chromium.launch(headless=True,args=['--no-sandbox'])
        yield browser
        browser.close()


@pytest.fixture
def pages(browser,request):
    contexts=[];errors=[];pages=[]
    def new(key):
        context=browser.new_context(viewport={'width':1440,'height':1000},timezone_id='Europe/Moscow')
        contexts.append(context);page=context.new_page();pages.append(page)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('dialog',lambda dialog:dialog.accept() if dialog.type in {'confirm','prompt'} else (errors.append(dialog.message),dialog.dismiss()))
        page.goto(BASE)
        if key in {'underwriter','approver','admin'}:
            label={'underwriter':'Аналитик','approver':'Согласующий','admin':'Демо: администратор'}[key]
            page.get_by_role('button',name=label,exact=True).click()
            expect(page.get_by_role('heading',name='Заявки на рассмотрении',exact=True)).to_be_visible()
        else:
            page.get_by_role('button',name='Демо-сценарии',exact=True).click()
            page.locator('#demo-scenario-form select').select_option(key)
            page.locator('#demo-scenario-form [type=submit]').click()
            expect(page.locator('h1')).to_have_text('Бизнес растёт. Мы рядом.')
        return page
    yield new
    SHOTS.mkdir(parents=True,exist_ok=True)
    for i,page in enumerate(pages):
        page.screenshot(path=str(SHOTS/f'{request.node.name}-{i}.png'),full_page=True)
    for context in contexts:context.close()
    assert not errors,errors


def workflow(page,id_):
    response=page.request.get(BASE+f'/api/applications/{id_}/workflow')
    assert response.ok,response.text()
    return response.json()


def status(page,id_,expected,timeout=60):
    until=monotonic()+timeout
    while monotonic()<until:
        data=workflow(page,id_)
        if data['status']==expected:return data
        sleep(.3)
    raise AssertionError(f'Expected {expected}: {data}')


def create_ui(page,*,amount=1000000,months=12,revenue=1500000,expenses=700000,mode='auto',product='working',calculator=False):
    if calculator:
        page.goto(BASE+'/#/products/working')
        form=page.locator('#calculator');expect(form).to_be_visible()
        form.locator('[name=amount]').fill(str(amount));form.locator('[name=months]').fill(str(months))
        form.locator('[type=submit]').click()
    else:
        page.goto(BASE+'/#/home');page.locator('[data-action=new-application]').click()
    form=page.locator('#wizard-form');expect(form).to_be_visible()
    form.locator(f'[data-action=wizard-product][data-id={product}]').click()
    form.locator('[name=amount]').fill(str(amount));form.locator('[name=months]').fill(str(months))
    form.locator('[name=purpose]').fill('Синтетическое финансирование оборота для браузерной проверки')
    form.locator('[type=submit]').click()
    form.locator('[name=revenue]').fill(str(revenue));form.locator('[name=expenses]').fill(str(expenses))
    form.locator('[name=debtPayment]').fill('0');form.locator('[name=decisionMode]').select_option(mode)
    form.locator('[type=submit]').click()
    from app.seed import synthetic_pdf
    types=['statement','accounts']+(['invoice'] if product=='equipment' else [])
    for doc_type in types:
        choices=form.get_by_role('checkbox',name=f'e2e_{doc_type}.pdf',exact=True);before=choices.count()
        with page.expect_response(lambda r:r.request.method=='POST' and '/api/documents' in r.url):
            form.locator(f'input[data-upload={doc_type}]').set_input_files({'name':f'e2e_{doc_type}.pdf','mimeType':'application/pdf','buffer':synthetic_pdf()})
        expect(choices).to_have_count(before+1,timeout=15000)
        expect(form.get_by_role('checkbox',name=f'e2e_{doc_type}.pdf',exact=True).last).to_be_checked(timeout=15000)
    form.locator('[type=submit]').click()
    form.locator('[name=consentData]').check();form.locator('[name=consentChecks]').check()
    form.locator('[type=submit]').click()
    expect(page.locator('#modal')).to_have_count(0,timeout=15000)
    page.wait_for_url('**/#/applications/*')
    return page.url.split('/')[-1]


def bank_review(page,id_,action,**values):
    page.goto(BASE+f'/#/review/{id_}')
    expect(page.locator('.bank-decision-form')).to_be_visible(timeout=15000)
    assign=page.locator('[data-op=assign]')
    if assign.count():
        assign.click();expect(page.locator('[data-op=assign]')).to_have_count(0)
    form=page.locator('.bank-decision-form')
    form.locator('[name=status]').select_option(action)
    form.locator('[name=comment]').fill('Проверено специалистом в синтетическом браузерном сценарии')
    if any(k in values for k in ['alternativeAmount','months','annual_rate','product_id','valid_days']):
        form.get_by_text('Предложенные условия',exact=True).click()
    if 'task_kind' in values:form.get_by_text('Задача клиенту при запросе сведений',exact=True).click()
    for key,value in values.items():
        field=form.locator(f'[name={key}]')
        if field.evaluate('(el)=>el.tagName')=='SELECT':field.select_option(str(value))
        else:field.fill(str(value))
    form.locator('[type=submit]').click()
    status(page,id_,action)


def complete_deal(page,id_):
    page.goto(BASE+f'/#/applications/{id_}')
    form=page.locator('#offer-action-form[data-operation=accept]');expect(form).to_be_visible(timeout=15000)
    form.locator('[name=acknowledged]').check();form.locator('[type=submit]').click()
    expect(page.locator('[data-action=request-signing-code]')).to_be_visible(timeout=15000)
    page.locator('[data-action=request-signing-code]').click()
    code=page.locator('[data-demo-code]');expect(code).to_be_visible()
    form=page.locator('#offer-action-form[data-operation=sign]')
    form.locator('[name=code]').fill(code.inner_text());form.locator('[name=acknowledged]').check()
    form.locator('[type=submit]').click()
    page.locator('[data-action=disburse-offer]').click()
    status(page,id_,'disbursed')
    expect(page.get_by_text('Демонстрационная выдача завершена. Реальные деньги не переводились.',exact=True)).to_be_visible()


def test_a_selection_auto_sign_issue_schedule(pages):
    page=pages('auto');page.goto(BASE+'/#/products')
    form=page.locator('#recommendation-form')
    for key,value in {'purpose':'Пополнение оборотных средств','amount':'1000000','months':'12','revenue':'1500000','expenses':'700000','debt_payment':'0'}.items():
        form.locator(f'[name={key}]').fill(value)
    form.locator('[type=submit]').click()
    expect(page.locator('#recommendation-result')).to_contain_text('Доступная сумма')
    id_=create_ui(page,calculator=True)
    data=status(page,id_,'approved');assert data['jobs'][-1]['status']=='DONE'
    expect(page.locator('#offer-action-form[data-operation=accept]')).to_be_visible(timeout=15000)
    complete_deal(page,id_)
    page.goto(BASE+'/#/loans');expect(page.locator('.loan-card')).not_to_have_count(0)
    loans=page.request.get(BASE+'/api/loans').json();loan=next(l for l in loans if l['application_id']==id_)
    page.goto(BASE+'/#/loans/'+loan['id']);expect(page.locator('.schedule-table tbody tr')).to_have_count(12)
    with page.expect_download() as download:page.get_by_role('link',name='Экспорт CSV',exact=True).click()
    assert Path(download.value.path()).read_bytes().startswith(b'\xef\xbb\xbf')
    page.get_by_role('button',name='График',exact=True).click();expect(page.locator('.schedule-column')).to_have_count(12)
    page.locator('[data-schedule-range]').fill('7');expect(page.locator('main')).to_contain_text('Месяц 7:')
    page.reload();expect(page.locator('.schedule-table tbody tr')).to_have_count(12)


def test_b_manual_counter_full_terms(pages):
    client=pages('counter');bank=pages('underwriter')
    id_=create_ui(client,amount=4000000,revenue=1000000,expenses=500000,mode='manual')
    status(client,id_,'pending')
    bank_review(bank,id_,'counter_offer',alternativeAmount=2000000,months=18,annual_rate=22,product_id='working',valid_days=7)
    data=status(client,id_,'counter_offer');assert data['offers'][-1]['months']==18
    expect(client.locator('.offer-comparison')).to_contain_text('18 мес.',timeout=15000)
    complete_deal(client,id_)


def test_c_document_task_chat_resubmission(pages):
    client=pages('documents');bank=pages('underwriter')
    id_=create_ui(client,mode='manual');status(client,id_,'pending')
    bank_review(bank,id_,'needs_info',task_kind='document',task_title='Счёт на закупку',document_type='invoice')
    client.reload();expect(client.get_by_text('Счёт на закупку',exact=True)).to_be_visible()
    from app.seed import synthetic_pdf
    client.locator('input[data-upload=invoice]').set_input_files({'name':'e2e_invoice.pdf','mimeType':'application/pdf','buffer':synthetic_pdf()})
    until=monotonic()+15
    while not all(t['status']=='DONE' for t in workflow(client,id_)['tasks']):
        assert monotonic()<until;sleep(.3)
    client.get_by_role('link',name='Открыть переписку',exact=True).click()
    chat=client.locator('.bank-message-form');chat.locator('[name=text]').fill('<script>alert(1)</script> Документ приложен')
    chat.locator('[type=submit]').click();expect(client.locator('.chat-message').last).to_contain_text('<script>alert(1)</script>')
    bank.reload();expect(bank.locator('.chat-message').last).to_contain_text('Документ приложен')
    bank.locator('.bank-message-form [name=text]').fill('Спасибо, проверяем счёт')
    bank.locator('.bank-message-form [type=submit]').click()
    client.reload();expect(client.locator('.chat-message').last).to_contain_text('Спасибо')
    client.goto(BASE+f'/#/applications/{id_}')
    client.locator('[data-action=edit-application]').click()
    form=client.locator('#wizard-form');expect(form.locator('[name=consentData]')).to_be_visible()
    form.locator('[name=consentData]').check();form.locator('[name=consentChecks]').check();form.locator('[type=submit]').click()
    status(client,id_,'pending');bank_review(bank,id_,'approved')
    data=status(client,id_,'approved');assert len(data['jobs'])==2
    client.goto(BASE+'/#/notifications');expect(client.locator('.notification')).not_to_have_count(0)
    client.locator('[data-op=notifications-read-all]').click();expect(client.locator('main')).to_contain_text('0 непрочитанных')


def test_d_escalation_approver(pages):
    client=pages('escalation');bank=pages('underwriter');approver=pages('approver')
    id_=create_ui(client,amount=10000000,months=36,revenue=5000000,expenses=1000000,product='equipment')
    status(client,id_,'pending');bank_review(bank,id_,'escalated');bank_review(approver,id_,'approved')
    assert workflow(client,id_)['decisions'][-1]['action']=='approved'


def test_e_bki_fault_retry_recovery(pages):
    client=pages('auto');admin=pages('admin')
    def source(mode):
        admin.goto(BASE+'/#/integrations');form=admin.locator('.source-form[data-source=bki]')
        expect(form).to_be_visible();form.locator('[name=mode]').select_option(mode)
        with admin.expect_response(lambda r:r.request.method=='PUT' and r.url.endswith('/integrations/bki')) as saved:
            form.locator('[type=submit]').click()
        assert saved.value.ok,saved.value.text()
        expect(admin.locator('.source-form[data-source=bki] [name=mode]')).to_have_value(mode)
    source('unavailable')
    try:
        id_=create_ui(client);failed=status(client,id_,'processing_error')
        assert failed['jobs'][-1]['attempts']==3
    finally:source('success')
    client.locator('[data-action=retry-processing]').click()
    good=status(client,id_,'approved');assert len(good['offers'])==1 and len(good['ml'])==1
    assert len({h['version'] for h in good['history']})==len(good['history'])


def test_f_preparer_and_signatory(pages):
    employee=pages('employee');signer=pages('preparer')
    id_=create_ui(employee);status(employee,id_,'approved')
    expect(employee.get_by_text('Принятие и подписание доступны уполномоченному представителю организации.',exact=True)).to_be_visible(timeout=15000)
    expect(employee.locator('#offer-action-form')).to_have_count(0)
    complete_deal(signer,id_)


def test_g_real_model_persistence_and_responsive_pages(pages):
    client=pages('model');bank=pages('admin');id_=create_ui(client);data=status(client,id_,'approved')
    result=data['ml'][-1];assert len(result['features'])==24 and result['result']['available']
    assert result['result']['classification'] is None and result['provenance']['synthetic']
    expect(client.get_by_role('heading',name='Результат LightGBM',exact=True)).to_be_visible(timeout=15000)
    client.get_by_text('Вклады признаков в raw-score',exact=True).click()
    expect(client.locator('main')).to_contain_text('Это не вклады в кредитное решение')
    client.reload();assert workflow(client,id_)['ml'][-1]['result']['scores']==result['result']['scores']
    for page,routes in [(client,['home','products',f'applications/{id_}','documents','team','loans','notifications']),
                        (bank,['current',f'review/{id_}','analytics','integrations','settings','audit'])]:
        for width in [1440,1024,390,320]:
            page.set_viewport_size({'width':width,'height':900})
            for route in routes:
                page.goto(BASE+'/#/'+route);expect(page.locator('h1')).not_to_have_text('')
                page.wait_for_timeout(200)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(route,width)
                assert not page.locator('.startup-screen').count(),(route,width)
                assert page.locator('img').evaluate_all('(images)=>images.every(i=>!i.complete||i.naturalWidth>0)'),route


@pytest.mark.skipif(os.getenv('E2E_QWEN')!='1',reason='Real CPU Qwen is explicitly opt-in')
def test_h_actual_qwen_credit_and_offtopic(pages):
    page=pages('model');page.goto(BASE+'/#/assistant')
    form=page.locator('#assistant-form');expect(form).to_be_visible()
    form.locator('textarea').fill('Что такое оборотный кредит? Объясни двумя предложениями без числовых условий.')
    form.locator('[type=submit]').click()
    expect(page.locator('.assistant-message.from-assistant').last).to_contain_text('Qwen',timeout=300000)
    expect(page.locator('.assistant-message.from-assistant').last).to_contain_text('кредит')
    form.locator('textarea').fill('Какая погода завтра?');form.locator('[type=submit]').click()
    expect(page.locator('.assistant-message.from-assistant').last).to_contain_text('Ограничение темы',timeout=300000)
