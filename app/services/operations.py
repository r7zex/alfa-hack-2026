"""Shared DB helpers for isolated collaboration and deduplicated notifications."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models.user import User,UserRole
from app.models.operations import Notification, ApplicationTask

BANK={UserRole.ADMIN,UserRole.UNDERWRITER,UserRole.APPROVER}

def upsert(db,model):
    return (pg_insert if db.get_bind().dialect.name=='postgresql' else sqlite_insert)(model)


def aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def utcnow():return datetime.now(timezone.utc)


async def notify(db,row,key,kind,text,*,bank=None,exclude_user=None):
    query=select(User.id)
    if bank is True:query=query.where(User.role.in_(BANK))
    elif bank is False:query=query.where(User.business_id==row.business_id,User.role==UserRole.CLIENT)
    else:query=query.where((User.business_id==row.business_id)|(User.role.in_(BANK)))
    ids=list((await db.scalars(query)).all())
    for user_id in ids:
        if user_id==exclude_user:continue
        await db.execute(upsert(db,Notification).values(id=uuid4(),user_id=user_id,application_id=row.id,
                         event_key=key,kind=kind,text=text[:700],read=False,archived=False)
                         .on_conflict_do_nothing(index_elements=['user_id','event_key']))


async def ensure_tasks(db,row,missing,reason='Уточните сведения'):
    existing=list((await db.scalars(select(ApplicationTask).where(
        ApplicationTask.application_id==row.id,ApplicationTask.status=='OPEN'))).all())
    for kind in missing:
        if any(t.document_type==kind for t in existing):continue
        db.add(ApplicationTask(application_id=row.id,kind='document',document_type=kind,
                               title='Приложите: '+kind,description='Обязательный PDF для выбранного продукта',required=True))
    if not missing and not existing:
        db.add(ApplicationTask(application_id=row.id,kind='information',title=reason[:255],description=reason,required=True))
