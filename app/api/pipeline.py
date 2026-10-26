"""Read-only workflow snapshots and explicit, versioned demo deal actions."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.api.applications import Client, Session, get_business_id
from app.dependencies import Auth, Config, BANK_ROLES
from app.models.auth import UserRole
from app.models.pipeline import ApplicationEvent, CreditOffer, DemoContract, DemoDisbursement, ProcessingRun
from app.schemas.document import DocumentRead
from app.services.pipeline import locked, event, process, latest_offer, offer_action, documents_for

router = APIRouter(prefix='/api/applications', tags=['Credit workflow'])


def record(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns} if row else None


@router.get('/{application_id}/workflow')
async def workflow(application_id: UUID, db: Session, auth: Auth):
    row = await locked(db, application_id, auth.user.business_id, admin=auth.user.role in BANK_ROLES)
    events = (await db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == row.id)
                               .order_by(ApplicationEvent.version))).all()
    runs = (await db.scalars(select(ProcessingRun).where(ProcessingRun.application_id == row.id)
                             .order_by(ProcessingRun.application_version))).all()
    offers = (await db.scalars(select(CreditOffer).where(CreditOffer.application_id == row.id)
                               .order_by(CreditOffer.version))).all()
    offer = offers[-1] if offers else None
    contract = await db.scalar(select(DemoContract).where(DemoContract.offer_id == offer.id)) if offer else None
    issuance = await db.scalar(select(DemoDisbursement).where(DemoDisbursement.application_id == row.id))
    from app.models.operations import ApplicationTask, PipelineJob, ModelPrediction, DecisionRecord
    tasks=(await db.scalars(select(ApplicationTask).where(ApplicationTask.application_id==row.id).order_by(ApplicationTask.created_at))).all()
    predictions=(await db.scalars(select(ModelPrediction).where(ModelPrediction.application_id==row.id).order_by(ModelPrediction.submission))).all()
    jobs=(await db.scalars(select(PipelineJob).where(PipelineJob.application_id==row.id).order_by(PipelineJob.submission))).all()
    decisions=(await db.scalars(select(DecisionRecord).where(DecisionRecord.application_id==row.id).order_by(DecisionRecord.created_at))).all()
    return dict(tasks=[record(t) for t in tasks],ml=[record(p) for p in predictions],decisions=[record(d) for d in decisions],
                jobs=[{k:getattr(j,k) for k in ['id','status','stage','attempts','last_error','created_at','completed_at']} for j in jobs],
                application_id=row.id, status=row.status, version=row.version,
                history=[record(e) for e in events], assessments=[record(r) for r in runs],
                offers=[record(o) for o in offers], contract=record(contract), disbursement=record(issuance),
                documents=[DocumentRead.model_validate(d).model_dump() for d in await documents_for(db, row)])


class RetryRequest(BaseModel):
    mock_scenario: Literal['success', 'missing', 'negative', 'unavailable', 'malformed'] | None = Field(default=None, alias='mockScenario')


@router.post('/{application_id}/retry')
async def retry(application_id: UUID, body: RetryRequest, db: Session, user: Client, settings: Config):
    from fastapi import HTTPException
    row = await locked(db, application_id, get_business_id(user))
    if row.status == 'pending':
        return {'status': row.status}
    if row.status != 'processing_error':
        raise HTTPException(409, 'Повтор доступен только после технической ошибки')
    if body.mock_scenario:
        row.mock_scenario = body.mock_scenario
    if settings.pipeline_async_enabled:
        from app.services.jobs import enqueue
        await event(db,row,user.id,'submitted','Повтор обработки после технической ошибки')
        await enqueue(db,row);await db.commit()
        return {'status':row.status}
    await event(db, row, user.id, 'processing', 'Безопасный повтор демонстрационных проверок')
    await process(db, row)
    await db.commit()
    return {'status': row.status}


class OfferAction(BaseModel):
    offer_id: UUID
    acknowledged: bool = False
    challenge_id: UUID | None = None
    code: str | None = Field(default=None,pattern=r"^[0-9]{6}$")
    contract_sha256: str | None = Field(default=None, max_length=64)


@router.post('/{application_id}/offer/{action}')
async def act(application_id: UUID, action: Literal['accept', 'decline', 'sign', 'disburse'],
              body: OfferAction, db: Session, user: Client, settings: Config):
    row = await locked(db, application_id, get_business_id(user))
    offer=await latest_offer(db,row)
    registration=None
    if action=='sign' and settings.signing_require_code and row.status not in {'signed','disbursed'}:
        from app.services.signing import verify_code
        if not offer or offer.id!=body.offer_id:
            from fastapi import HTTPException
            raise HTTPException(409,'Устаревшее предложение')
        if not user.can_sign:
            from fastapi import HTTPException
            raise HTTPException(403,'Нужно право подписи')
        await verify_code(db,offer,user,body.challenge_id,body.code,settings)
    if action=='disburse' and row.status=='signed':
        from app.models.operations import SourceSetting
        from app.services.mock_sources import MockAdapter,SourceFailure
        from app.services.operations import aware,utcnow
        from fastapi import HTTPException
        setting=await db.get(SourceSetting,'issuance')
        config={'mode':setting.mode,'open':bool(setting.open_until and aware(setting.open_until)>utcnow())} if setting else {}
        application_id=row.id
        await db.commit()
        try:
            registration=await MockAdapter('issuance',config,settings.integration_timeout_seconds).get({'id':str(application_id)},1)
            if registration['status']!='success':raise SourceFailure('issuance: '+registration['status'])
        except SourceFailure as exc:raise HTTPException(503,'Демонстрационная регистрация выдачи недоступна; повторите') from exc
        row=await locked(db,application_id,get_business_id(user))
    first_issuance=action=='disburse' and row.status=='signed'
    await offer_action(db, row, user, action, body.offer_id, body.acknowledged, body.contract_sha256)
    if first_issuance and registration:
        issuance_event=await db.scalar(select(ApplicationEvent).where(ApplicationEvent.application_id==row.id,ApplicationEvent.version==row.version))
        issuance_event.details={**issuance_event.details,'source_result':registration}
    await db.commit()
    return {'status': row.status, 'offer_id': body.offer_id}


@router.post('/{application_id}/signing-code')
async def signing_code(application_id: UUID, db: Session, user: Client, settings: Config):
    from app.services.signing import issue_code
    from fastapi import HTTPException
    row=await locked(db,application_id,get_business_id(user))
    offer=await latest_offer(db,row)
    if not offer:raise HTTPException(409,'Предложение отсутствует')
    result=await issue_code(db,row,offer,user,settings)
    await db.commit()
    return result
