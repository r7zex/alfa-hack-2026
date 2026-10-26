"""Idempotent synthetic product scenarios. Never deletes or resets user data."""
import asyncio
from datetime import date
from io import BytesIO
from uuid import UUID,uuid5
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from pyhanko.pdf_utils.writer import PdfFileWriter
from pyhanko.pdf_utils.generic import DictionaryObject,ArrayObject,NumberObject,pdf_name
from app.db.session import AsyncSessionLocal,engine
from app.models.auth import Business,BusinessType,User,UserRole
from app.models.loan_application import LoanApplication
from app.models.document import Document
from app.models.pipeline import ApplicationDocument,ApplicationEvent
from app.models.operations import FinancialProfile,PipelineJob
from app.services.financial_features import STABLE,STRESSED,PROVENANCE
from app.services.jobs import enqueue,run_one
from app.services.pipeline import event,locked,latest_offer,offer_action
from app.services.signing import issue_code,verify_code
from app.services.operations import upsert,utcnow
from app.settings import get_settings
from app.security import hash_password
from hashlib import sha256

NAMESPACE=UUID('6ed06fd9-9ac8-41b0-84bf-3084ff4057d6')
DEMO_PASSWORD='Delora-demo-2026!'
SCENARIOS=[
 ('auto','Автоматическое одобрение',{}),
 ('counter','Встречное предложение',{'amount':4000000,'revenue':1000000,'expenses':500000,'debt_payment':0,'decision_mode':'manual'}),
 ('documents','Запрос документов',{'no_documents':True}),
 ('stop','Отказ по стоп-фактору',{'mock_scenario':'negative'}),
 ('manual','Ручное рассмотрение',{'decision_mode':'manual'}),
 ('escalation','Согласование крупной суммы',{'product_id':'equipment','amount':10000000,'months':36,'revenue':5000000,'expenses':1000000}),
 ('model','Реальный ML на синтетическом профиле',{}),
 ('no_features','Отсутствуют признаки ML',{'no_features':True,'type':'ip'}),
 ('bki_down','БКИ недоступно',{'mock_scenario':'unavailable'}),
 ('recovery','Временный отказ и восстановление',{'mock_scenario':'transient'}),
 ('preparer','Сотрудник без права подписи',{'preparer':True}),
 ('completed','Завершённая демонстрационная выдача',{}),
]


def identifier(key):return uuid5(NAMESPACE,key)


def inn_for(index,kind):
    digits=list(map(int,f'9901{index:05d}' if kind=='llc' else f'99000000{index:02d}'))
    weights=([2,4,10,3,5,9,4,6,8],) if kind=='llc' else ([7,2,4,10,3,5,9,4,6,8],[3,7,2,4,10,3,5,9,4,6,8])
    for row in weights:digits.append(sum(a*b for a,b in zip(digits,row))%11%10)
    return ''.join(map(str,digits))


def synthetic_pdf():
    writer=PdfFileWriter();writer.insert_page(DictionaryObject({pdf_name('/Type'):pdf_name('/Page'),pdf_name('/MediaBox'):ArrayObject([NumberObject(x) for x in [0,0,200,200]]),pdf_name('/Resources'):DictionaryObject()}))
    output=BytesIO();writer.write(output);return output.getvalue()


async def seed():
    settings=get_settings();password_hash=hash_password(DEMO_PASSWORD);pdf=synthetic_pdf()
    # Unique email and deterministic application/document PKs are the idempotency keys.
    for index,(key,title,options) in enumerate(SCENARIOS,1):
        async with AsyncSessionLocal() as db:
            email=key+'@demo.example.com'
            user=await db.scalar(select(User).options(selectinload(User.business)).where(User.email==email))
            if user and not user.is_demo:raise ValueError('Seed email occupied by a regular user: '+email)
            if user is None:
                kind=options.get('type','llc');inn=inn_for(index,kind)
                if await db.scalar(select(Business.id).where(Business.inn==inn)):
                    raise ValueError('Seed INN occupied; existing organization preserved')
                business=Business(type=BusinessType(kind),inn=inn,name=('ИП' if kind=='ip' else 'ООО')+' «Делора '+title+'»',registration=date(2020,1,1),contact='Синтетический представитель')
                user=User(email=email,password_hash=password_hash,business=business,role=UserRole.CLIENT,is_demo=True,can_sign=True)
                db.add(user);await db.flush()
                if not options.get('no_features'):db.add(FinancialProfile(business_id=business.id,kind='synthetic_stable',features=STABLE,provenance=PROVENANCE))
            if options.get('preparer'):
                employee=await db.scalar(select(User).where(User.email=='employee@demo.example.com'))
                if employee is None:db.add(User(email='employee@demo.example.com',password_hash=password_hash,business_id=user.business_id,role=UserRole.CLIENT,is_demo=True,can_sign=False))
            app_id=identifier('application:'+key)
            if await db.get(LoanApplication,app_id) is None:
                values=dict(product_id='working',amount=1000000,months=12,revenue=1500000,expenses=700000,debt_payment=10000,
                            decision_mode='auto',mock_scenario='success')
                values.update({k:v for k,v in options.items() if k in values})
                row=LoanApplication(id=app_id,owner_id='seed:v2:'+key,business_id=user.business_id,created_by_user_id=user.id,
                                    status='draft',version=0,submission=0,current_step=3,purpose='Синтетическое финансирование бизнеса',**values)
                db.add(row);await db.flush()
                db.add(ApplicationEvent(application_id=row.id,version=0,actor_id=user.id,new_status='draft',reason='Синтетический сценарий создан',details={}))
                if not options.get('no_documents'):
                    required=['statement','tax' if user.business.type.value=='ip' else 'accounts']
                    if row.product_id=='equipment':required.append('invoice')
                    for doc_type in required:
                        doc_id=identifier('document:'+key+':'+doc_type)
                        db.add(Document(id=doc_id,business_id=user.business_id,application_id=row.id,document_type=doc_type,
                                        filename='synthetic_'+doc_type+'.pdf',content_type='application/pdf',size=len(pdf),sha256=sha256(pdf).hexdigest(),content=pdf,
                                        signature={'status':'unsigned','validation_mode':'synthetic_fixture','fns_authenticity':'not_established'}))
                        await db.flush()
                        db.add(ApplicationDocument(application_id=row.id,document_id=doc_id))
                await event(db,row,user.id,'submitted','Синтетическая заявка отправлена',{'demo_data':True,'demo_checks':True})
                await enqueue(db,row)
            await db.commit()
    for role in (UserRole.ADMIN,UserRole.UNDERWRITER,UserRole.APPROVER):
        async with AsyncSessionLocal() as db:
            email=role.value+'@demo.example.com'
            user=await db.scalar(select(User).options(selectinload(User.business)).where(User.email==email))
            if user and not user.is_demo:raise ValueError('Bank seed email occupied by regular user')
            if user is None:db.add(User(email=email,password_hash=password_hash,role=role,is_demo=True,can_sign=False))
            await db.commit()
    # The same leased queue implementation is used when no worker is running yet.
    for _ in range(70):
        if not await run_one(AsyncSessionLocal,settings):
            async with AsyncSessionLocal() as db:
                busy=await db.scalar(select(PipelineJob.id).where(PipelineJob.status.in_(['PENDING','RUNNING'])).limit(1))
            if not busy:break
            await asyncio.sleep(.2)
    async with AsyncSessionLocal() as db:
        row=await locked(db,identifier('application:completed'),admin=True)
        user=await db.get(User,row.created_by_user_id)
        offer=await latest_offer(db,row)
        if row.status=='approved' and offer:
            await offer_action(db,row,user,'accept',offer.id,True)
            local=settings.model_copy(update={'demo_auth_enabled':True,'demo_signing_code_visible':True})
            challenge=await issue_code(db,row,offer,user,local)
            await db.flush()
            await verify_code(db,offer,user,challenge['challenge_id'],challenge['demo_code'],local)
            await offer_action(db,row,user,'sign',offer.id,True,offer.contract_sha256)
            await offer_action(db,row,user,'disburse',offer.id)
            await db.commit()
    print('Synthetic scenarios prepared idempotently. Password for newly created seed accounts: see docs/demo-script.md')


def main():
    async def run():
        try:await seed()
        finally:await engine.dispose()
    asyncio.run(run())

if __name__=='__main__':main()
