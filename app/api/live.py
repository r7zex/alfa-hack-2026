"""Bounded SSE with cookie authentication and DB-backed per-user limits."""
import asyncio
import json
from datetime import timedelta
from time import monotonic
from uuid import UUID,uuid4
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select,delete,func
from app.dependencies import Auth,Db,BANK_ROLES
from app.db.session import AsyncSessionLocal
from app.models.auth import User,AuthSession
from app.models.operations import StreamLease
from app.models.loan_application import LoanApplication
from app.models.pipeline import ApplicationEvent
from app.services.pipeline import locked
from app.services.operations import utcnow,aware

router=APIRouter(prefix='/api/applications',tags=['Live status'])


@router.get('/{id_}/stream')
async def stream(id_:UUID,request:Request,db:Db,auth:Auth):
    row=await locked(db,id_,auth.user.business_id,admin=auth.user.role in BANK_ROLES)
    await db.scalar(select(User.id).where(User.id==auth.user.id).with_for_update())
    await db.execute(delete(StreamLease).where(StreamLease.expires_at<=utcnow()))
    count=await db.scalar(select(func.count()).select_from(StreamLease).where(StreamLease.user_id==auth.user.id))
    if count>=3:raise HTTPException(429,'Слишком много подключений; используйте ручное обновление')
    lease_id=uuid4();db.add(StreamLease(id=lease_id,user_id=auth.user.id,expires_at=utcnow()+timedelta(seconds=50)))
    user_id,session_id=auth.user.id,auth.session.id
    try:cursor=max(-1,int(request.headers.get('last-event-id','-1')))
    except ValueError:raise HTTPException(422,'Некорректный Last-Event-ID') from None
    await db.commit()
    async def generate():
        nonlocal cursor
        start=monotonic()
        try:
            yield 'retry: 3000\n\n'
            while monotonic()-start<45:
                if await request.is_disconnected():return
                async with AsyncSessionLocal() as session:
                    cookie_session=await session.get(AuthSession,session_id)
                    user=await session.get(User,user_id)
                    application=await session.get(LoanApplication,id_)
                    if not cookie_session or aware(cookie_session.expires_at)<=utcnow() or not user or not application:return
                    if user.role not in BANK_ROLES and user.business_id!=application.business_id:return
                    if user.role in BANK_ROLES and application.status=='draft':return
                    rows=(await session.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id==id_,ApplicationEvent.version>cursor)
                                                 .order_by(ApplicationEvent.version).limit(100))).all()
                    for item in rows:
                        cursor=item.version
                        data={'version':cursor,'status':item.new_status,'reason':item.reason}
                        yield f'id: {cursor}\nevent: update\ndata: {json.dumps(data,ensure_ascii=False)}\n\n'
                if not rows:yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        finally:
            async with AsyncSessionLocal() as session:
                await session.execute(delete(StreamLease).where(StreamLease.id==lease_id));await session.commit()
    return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-store','X-Accel-Buffering':'no','X-Content-Type-Options':'nosniff'})
