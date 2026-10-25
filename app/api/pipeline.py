"""Read-only workflow snapshots and explicit, versioned demo deal actions."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from app.api.applications import Client, Session, get_business_id
from app.dependencies import Auth
from app.models.auth import UserRole
from app.models.pipeline import ApplicationEvent, CreditOffer, DemoContract, DemoDisbursement, ProcessingRun
from app.schemas.document import DocumentRead
from app.services.pipeline import locked, event, process, latest_offer, offer_action, documents_for

router = APIRouter(prefix='/api/applications', tags=['Credit workflow'])


def record(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns} if row else None


@router.get('/{application_id}/workflow')
async def workflow(application_id: UUID, db: Session, auth: Auth):
    row = await locked(db, application_id, auth.user.business_id, admin=auth.user.role == UserRole.ADMIN)
    events = (await db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == row.id)
                               .order_by(ApplicationEvent.version))).all()
    runs = (await db.scalars(select(ProcessingRun).where(ProcessingRun.application_id == row.id)
                             .order_by(ProcessingRun.application_version))).all()
    offers = (await db.scalars(select(CreditOffer).where(CreditOffer.application_id == row.id)
                               .order_by(CreditOffer.version))).all()
    offer = offers[-1] if offers else None
    contract = await db.scalar(select(DemoContract).where(DemoContract.offer_id == offer.id)) if offer else None
    issuance = await db.scalar(select(DemoDisbursement).where(DemoDisbursement.application_id == row.id))
    return dict(application_id=row.id, status=row.status, version=row.version,
                history=[record(e) for e in events], assessments=[record(r) for r in runs],
                offers=[record(o) for o in offers], contract=record(contract), disbursement=record(issuance),
                documents=[DocumentRead.model_validate(d).model_dump() for d in await documents_for(db, row)])


class RetryRequest(BaseModel):
    mock_scenario: Literal['success', 'missing', 'negative', 'unavailable', 'malformed'] | None = Field(default=None, alias='mockScenario')


@router.post('/{application_id}/retry')
async def retry(application_id: UUID, body: RetryRequest, db: Session, user: Client):
    from fastapi import HTTPException
    row = await locked(db, application_id, get_business_id(user))
    if row.status == 'pending':
        return {'status': row.status}
    if row.status != 'processing_error':
        raise HTTPException(409, 'Повтор доступен только после технической ошибки')
    if body.mock_scenario:
        row.mock_scenario = body.mock_scenario
    await event(db, row, user.id, 'processing', 'Безопасный повтор демонстрационных проверок')
    await process(db, row)
    await db.commit()
    return {'status': row.status}


class OfferAction(BaseModel):
    offer_id: UUID
    acknowledged: bool = False
    contract_sha256: str | None = Field(default=None, max_length=64)


@router.post('/{application_id}/offer/{action}')
async def act(application_id: UUID, action: Literal['accept', 'decline', 'sign', 'disburse'],
              body: OfferAction, db: Session, user: Client):
    row = await locked(db, application_id, get_business_id(user))
    await offer_action(db, row, user, action, body.offer_id, body.acknowledged, body.contract_sha256)
    await db.commit()
    return {'status': row.status, 'offer_id': body.offer_id}
