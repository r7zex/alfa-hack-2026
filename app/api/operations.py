"""Collaboration, notifications, loan schedules and scoped bank operations."""
import csv
from io import StringIO
from datetime import timedelta
from typing import Annotated,Literal
from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import Response
from pydantic import BaseModel,ConfigDict,Field,EmailStr,field_validator
from sqlalchemy import select,func,delete
from app.dependencies import Auth,Db,Config,require_bank,require_admin,require_client,require_signer,check_origin
from app.models.auth import User,UserRole,Business
from app.models.document import Document
from app.models.pipeline import ApplicationDocument,CreditOffer
from app.models.operations import (ApplicationTask,ApplicationMessage,MessageRead,Notification,LoanAccount,FinancialProfile,
                                 SourceSetting,PolicyVersion,SystemSetting,TeamInvitation,PipelineJob,ModelPrediction,DecisionRecord,AdminAudit)
from app.services.pipeline import locked,event,latest_offer
from app.services.operations import upsert,utcnow,aware,notify
from app.services.policy_rules import RuleDefinition,active_rules
from app.services.financial_features import PROFILES,PROVENANCE
from app.services.mock_sources import SOURCES,MODES
from app.security import digest,new_token,hash_password
from app.repositories.auth import user_by_email
from starlette.concurrency import run_in_threadpool

router=APIRouter(prefix='/api',tags=['Product operations'])
Bank=Annotated[User,Depends(require_bank)]
Admin=Annotated[User,Depends(require_admin)]
Client=Annotated[User,Depends(require_client)]
Signer=Annotated[User,Depends(require_signer)]


def record(row):return {c.name:getattr(row,c.name) for c in row.__table__.columns}


async def accessible(db,id_,user):
    return await locked(db,id_,user.business_id,admin=user.role in {UserRole.ADMIN,UserRole.UNDERWRITER,UserRole.APPROVER})


class StrictInput(BaseModel):model_config=ConfigDict(extra='forbid')


class MessageInput(StrictInput):
    request_id:UUID
    text:str=Field(min_length=1,max_length=4000)
    @field_validator('text')
    @classmethod
    def clean(cls,value):
        value=value.strip()
        if not value or any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('Недопустимый текст сообщения')
        return value


@router.get('/applications/{id_}/messages')
async def messages(id_:UUID,db:Db,auth:Auth):
    await accessible(db,id_,auth.user)
    rows=(await db.scalars(select(ApplicationMessage).where(ApplicationMessage.application_id==id_)
                           .order_by(ApplicationMessage.created_at,ApplicationMessage.id).limit(300))).all()
    seen=await db.get(MessageRead,(id_,auth.user.id))
    return {'messages':[record(m) for m in rows],'unread':sum(m.author_id!=auth.user.id and (not seen or aware(m.created_at)>aware(seen.read_at)) for m in rows)}


@router.post('/applications/{id_}/messages',status_code=201)
async def message(id_:UUID,body:MessageInput,db:Db,auth:Auth):
    row=await accessible(db,id_,auth.user)
    old=await db.scalar(select(ApplicationMessage).where(ApplicationMessage.author_id==auth.user.id,ApplicationMessage.request_id==body.request_id))
    if old:
        if old.application_id!=id_ or old.text!=body.text:raise HTTPException(409,'request_id уже использован для другого сообщения')
        return record(old)
    # Serializing the application row makes duplicate requests deterministic.
    item=ApplicationMessage(id=uuid4(),application_id=id_,author_id=auth.user.id,author_role=auth.user.role.value,request_id=body.request_id,text=body.text)
    db.add(item)
    await event(db,row,auth.user.id,row.status,'Новое сообщение в переписке',{'message_id':str(item.id)})
    await notify(db,row,'message:'+str(item.id),'message','Новое сообщение по заявке',exclude_user=auth.user.id)
    await db.commit();await db.refresh(item)
    return record(item)


@router.post('/applications/{id_}/messages/read')
async def read_messages(id_:UUID,db:Db,auth:Auth):
    await accessible(db,id_,auth.user)
    await db.execute(upsert(db,MessageRead).values(application_id=id_,user_id=auth.user.id,read_at=utcnow()).on_conflict_do_update(
        index_elements=['application_id','user_id'],set_={'read_at':utcnow()}));await db.commit()
    return {'ok':True}


@router.get('/applications/{id_}/tasks')
async def tasks(id_:UUID,db:Db,auth:Auth):
    await accessible(db,id_,auth.user)
    return [record(t) for t in (await db.scalars(select(ApplicationTask).where(ApplicationTask.application_id==id_).order_by(ApplicationTask.created_at))).all()]


class TaskAnswer(StrictInput):
    answer:str=Field(default='',max_length=4000)
    document_id:UUID|None=None


@router.post('/applications/{id_}/tasks/{task_id}/complete')
async def complete_task(id_:UUID,task_id:UUID,body:TaskAnswer,db:Db,user:Client):
    row=await accessible(db,id_,user)
    task=await db.get(ApplicationTask,task_id)
    if not task or task.application_id!=id_:raise HTTPException(404,'Задача не найдена')
    if task.status=='DONE':return record(task)
    if row.status!='needs_info':raise HTTPException(409,'Заявка не ожидает уточнений')
    if task.kind=='document':
        doc=await db.get(Document,body.document_id) if body.document_id else None
        link=await db.get(ApplicationDocument,(id_,body.document_id)) if body.document_id else None
        if not doc or doc.business_id!=user.business_id or not link or doc.document_type!=task.document_type:
            raise HTTPException(422,'Приложите к заявке PDF требуемого типа')
        task.document_id=doc.id
    elif not body.answer.strip():raise HTTPException(422,'Укажите ответ на вопрос банка')
    task.status='DONE';task.answer=body.answer.strip();task.completed_at=utcnow()
    await event(db,row,user.id,row.status,'Выполнена задача: '+task.title)
    await notify(db,row,'task:'+str(task.id),'task','Клиент предоставил сведения',bank=True)
    await db.commit();return record(task)


@router.post('/analyst/applications/{id_}/assign')
async def assign(id_:UUID,db:Db,user:Bank):
    row=await accessible(db,id_,user)
    if row.status not in {'pending','escalated'}:raise HTTPException(409,'Заявка не ожидает сотрудника')
    if row.status=='escalated' and user.role==UserRole.UNDERWRITER:raise HTTPException(403,'Нужен согласующий')
    if row.assigned_to_user_id not in (None,user.id):raise HTTPException(409,'Заявку уже взял другой сотрудник')
    if row.assigned_to_user_id is None:
        row.assigned_to_user_id=user.id
        await event(db,row,user.id,row.status,'Сотрудник взял заявку в работу')
        await db.commit()
    return {'assigned_to_user_id':user.id}


class Reason(StrictInput):comment:str=Field(min_length=3,max_length=1500)


@router.post('/analyst/applications/{id_}/revoke')
async def revoke(id_:UUID,body:Reason,db:Db,user:Bank):
    row=await accessible(db,id_,user)
    if row.status not in {'approved','counter_offer'}:raise HTTPException(409,'Предложение нельзя отозвать')
    offer=await latest_offer(db,row)
    if not offer or offer.status!='offered':raise HTTPException(409,'Нет активного предложения')
    offer.status='revoked'
    await event(db,row,user.id,'pending',body.comment)
    await db.commit();return {'status':row.status}


@router.get('/notifications')
async def notifications(db:Db,auth:Auth):
    rows=(await db.scalars(select(Notification).where(Notification.user_id==auth.user.id,Notification.archived.is_(False))
                           .order_by(Notification.created_at.desc(),Notification.id).limit(200))).all()
    return {'items':[record(n) for n in rows],'unread':sum(not n.read for n in rows)}


@router.post('/notifications/read-all')
async def notifications_read_all(db:Db,auth:Auth):
    from sqlalchemy import update
    await db.execute(update(Notification).where(Notification.user_id==auth.user.id).values(read=True));await db.commit()
    return {'ok':True}


@router.post('/notifications/{id_}/read')
@router.delete('/notifications/{id_}')
async def notification_update(id_:UUID,request:Request,db:Db,auth:Auth):
    item=await db.get(Notification,id_)
    if not item or item.user_id!=auth.user.id:raise HTTPException(404,'Уведомление не найдено')
    if request.method=='DELETE':item.archived=True
    else:item.read=True
    await db.commit();return {'ok':True}


@router.get('/loans')
async def loans(db:Db,user:Client):
    return [record(l) for l in (await db.scalars(select(LoanAccount).where(LoanAccount.business_id==user.business_id).order_by(LoanAccount.issued_at.desc()))).all()]


async def owned_loan(db,id_,user):
    row=await db.get(LoanAccount,id_)
    if not row or row.business_id!=user.business_id:raise HTTPException(404,'Кредит не найден')
    return row


@router.get('/loans/{id_}')
async def loan(id_:UUID,db:Db,user:Client):return record(await owned_loan(db,id_,user))


def csv_response(rows,filename):
    output=StringIO();writer=csv.writer(output,delimiter=';')
    for row in rows:
        writer.writerow([("'"+str(v)) if str(v).lstrip().startswith(('=','+','-','@','\t','\r')) else str(v) for v in row])
    return Response(('\ufeff'+output.getvalue()).encode('utf-8'),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{filename}"'})


@router.get('/loans/{id_}/schedule.csv')
async def loan_csv(id_:UUID,db:Db,user:Client):
    row=await owned_loan(db,id_,user)
    headers=['number','date','opening','interest','principal','payment','closing']
    return csv_response([headers,*[[r[k] for k in headers] for r in row.schedule]],'payment-schedule.csv')


@router.get('/applications/{id_}/ml')
async def prediction(id_:UUID,db:Db,auth:Auth):
    await accessible(db,id_,auth.user)
    return [record(p) for p in (await db.scalars(select(ModelPrediction).where(ModelPrediction.application_id==id_).order_by(ModelPrediction.submission))).all()]


class SourceInput(StrictInput):mode:Literal['success','missing','negative','unavailable','timeout','malformed','transient']


@router.get('/admin/integrations')
async def sources(db:Db,user:Bank):
    rows={s.name:s for s in (await db.scalars(select(SourceSetting))).all()}
    return [{'name':name,'mode':rows[name].mode if name in rows else 'success','failures':rows[name].failures if name in rows else 0,
             'open_until':rows[name].open_until if name in rows else None} for name in SOURCES]


@router.put('/admin/integrations/{name}')
async def set_source(name:str,body:SourceInput,db:Db,user:Admin):
    if name not in SOURCES:raise HTTPException(404,'Источник не найден')
    await db.execute(upsert(db,SourceSetting).values(name=name,mode=body.mode,failures=0,updated_by=user.id,open_until=None)
                     .on_conflict_do_update(index_elements=['name'],set_={'mode':body.mode,'failures':0,'open_until':None,'updated_by':user.id,'updated_at':utcnow()}))
    db.add(AdminAudit(actor_id=user.id,action='source_mode',target=name,details={'mode':body.mode}))
    await db.commit();return {'name':name,'mode':body.mode}


@router.get('/admin/rules')
async def rules(db:Db,user:Bank):
    version,definition=await active_rules(db);await db.commit()
    history=(await db.scalars(select(PolicyVersion).order_by(PolicyVersion.id.desc()))).all()
    return {'version':version,'definition':definition,'history':[record(v) for v in history]}


@router.post('/admin/rules',status_code=201)
async def publish_rules(body:RuleDefinition,db:Db,user:Admin):
    await active_rules(db)
    setting=await db.scalar(select(SystemSetting).where(SystemSetting.key=='active_policy').with_for_update())
    version=(await db.scalar(select(func.max(PolicyVersion.id))))+1
    db.add(PolicyVersion(id=version,definition=body.model_dump(),created_by=user.id));setting.value={'version':version}
    db.add(AdminAudit(actor_id=user.id,action='publish_rules',target=str(version),details=body.model_dump()))
    await db.commit();return {'version':version,'definition':body.model_dump()}


class ProfileInput(StrictInput):
    kind:Literal['synthetic_stable','synthetic_stressed','missing','verified']
    features:dict[str,float|None]|None=None
    source:str=Field(default='',max_length=500)
    period:str=Field(default='2022',max_length=20)


@router.put('/admin/businesses/{business_id}/financial-profile')
async def financial_profile(business_id:int,body:ProfileInput,db:Db,user:Admin):
    if not await db.get(Business,business_id):raise HTTPException(404,'Организация не найдена')
    if body.kind=='missing':await db.execute(delete(FinancialProfile).where(FinancialProfile.business_id==business_id))
    else:
        features=PROFILES.get(body.kind,body.features)
        if features is None:raise HTTPException(422,'Укажите 24 признака')
        from ml.imported_lightgbm import validate_features,ImportedModelError
        try:validate_features(features)
        except ImportedModelError as exc:raise HTTPException(422,str(exc)) from exc
        if body.kind=='verified' and (not body.source or body.period!='2022'):
            raise HTTPException(422,'Для проверенного профиля нужны источник и период 2022')
        provenance=PROVENANCE if body.kind!='verified' else {'synthetic':False,'source':body.source,'period':body.period,'verified_by':user.id,'training_units_verified':False}
        await db.execute(upsert(db,FinancialProfile).values(business_id=business_id,kind=body.kind,features=features,provenance=provenance)
                         .on_conflict_do_update(index_elements=['business_id'],set_={'kind':body.kind,'features':features,'provenance':provenance,'updated_at':utcnow()}))
    db.add(AdminAudit(actor_id=user.id,action='financial_profile',target=str(business_id),details={'kind':body.kind,'period':body.period}))
    await db.commit();return {'kind':body.kind}


@router.get('/admin/audit')
async def audit(db:Db,user:Admin):
    from app.models.pipeline import ApplicationEvent
    changes=(await db.scalars(select(AdminAudit).order_by(AdminAudit.created_at.desc()).limit(200))).all()
    events=(await db.scalars(select(ApplicationEvent).order_by(ApplicationEvent.created_at.desc()).limit(200))).all()
    rows=[{'actor_id':r.actor_id,'action':r.action,'target':r.target,'details':r.details,'created_at':r.created_at} for r in changes]
    rows.extend({'actor_id':r.actor_id,'action':r.new_status,'target':str(r.application_id),
                 'details':{'reason':r.reason,'version':r.version},'created_at':r.created_at} for r in events)
    return sorted(rows,key=lambda r:aware(r['created_at']),reverse=True)[:200]


@router.get('/team')
async def team(db:Db,user:Client):
    rows=(await db.scalars(select(User).where(User.business_id==user.business_id))).all()
    return [{'id':u.id,'email':u.email,'can_sign':u.can_sign} for u in rows]


class InviteInput(StrictInput):email:EmailStr


@router.post('/team/invitations',status_code=201)
async def invite(body:InviteInput,db:Db,user:Signer):
    email=body.email.lower()
    if await user_by_email(db,email):raise HTTPException(409,'Пользователь уже зарегистрирован')
    token=new_token();expires=utcnow()+timedelta(hours=24)
    db.add(TeamInvitation(business_id=user.business_id,invited_by=user.id,email=email,token_hash=digest(token),expires_at=expires))
    await db.commit();return {'token':token,'email':email,'expires_at':expires,'role':'preparer'}


class JoinInput(StrictInput):
    token:str=Field(min_length=20,max_length=128)
    email:EmailStr
    password:str=Field(min_length=8,max_length=128)


@router.post('/team/join',status_code=201)
async def join(body:JoinInput,request:Request,db:Db,settings:Config):
    check_origin(request)
    from app.services.auth import rate_limit
    await rate_limit(db,request,settings,body.email.lower())
    invitation=await db.scalar(select(TeamInvitation).where(TeamInvitation.token_hash==digest(body.token)).with_for_update())
    if not invitation or invitation.email!=body.email.lower() or invitation.used_at or aware(invitation.expires_at)<=utcnow():
        raise HTTPException(422,'Приглашение недействительно')
    if await user_by_email(db,body.email.lower()):raise HTTPException(409,'Пользователь уже существует')
    db.add(User(email=body.email.lower(),password_hash=await run_in_threadpool(hash_password,body.password),
                role=UserRole.CLIENT,business_id=invitation.business_id,can_sign=False,is_demo=False))
    invitation.used_at=utcnow();await db.commit();return {'ok':True,'message':'Аккаунт сотрудника создан. Войдите с почтой и паролем.'}


@router.post('/applications/{id_}/cancel')
async def cancel(id_:UUID,db:Db,user:Client):
    row=await accessible(db,id_,user)
    if row.status=='cancelled':return {'status':row.status}
    if row.status not in {'draft','submitted','needs_info','pending','escalated','processing_error','approved','counter_offer'}:
        raise HTTPException(409,'Заявку нельзя отменить на этом этапе')
    if row.status in {'approved','counter_offer'} and not user.can_sign:raise HTTPException(403,'Нужно право подписи')
    offer=await latest_offer(db,row)
    if offer and offer.status=='offered':offer.status='revoked'
    await event(db,row,user.id,'cancelled','Заявка отменена клиентом')
    await db.commit();return {'status':row.status}
