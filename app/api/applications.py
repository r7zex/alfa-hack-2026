"""Client applications use authenticated user and business IDs."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import require_client, Config
from app.models.auth import User
from app.schemas.loan_application import ApplicationCreate, ApplicationRead, ApplicationUpdate
from app.services.application_service import ApplicationService

class SubmitConsent(BaseModel):
    demo_data: bool = False
    demo_checks: bool = False


router = APIRouter(prefix="/api/applications", tags=["Applications"])

Session = Annotated[AsyncSession, Depends(get_db)]
Client = Annotated[User, Depends(require_client)]


def get_business_id(user: User) -> int:
    if user.business_id is None:
        raise HTTPException(status_code=403, detail="A business is required to apply for credit")
    return user.business_id


async def claim_drafts(db: AsyncSession, user: User) -> None:
    # Compatibility only: preserve earlier synthetic drafts for these
    # two known demo users, never for a newly registered real account.
    if user.is_demo and user.business and user.business_id is not None:
        await ApplicationService(db).repo.claim_legacy_demo(
            user.business_id, user.id, "demo-" + user.business.type.value
        )


@router.get("", response_model=list[ApplicationRead], response_model_by_alias=True)
@router.get("/my", response_model=list[ApplicationRead], response_model_by_alias=True, include_in_schema=False)
async def list_applications(db: Session, user: Client):
    business_id = get_business_id(user)
    await claim_drafts(db, user)
    return await ApplicationService(db).list_owned(business_id)


@router.post("", response_model=ApplicationRead, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
async def create_application(body: ApplicationCreate, db: Session, user: Client):
    business_id = get_business_id(user)
    return await ApplicationService(db).create(business_id, user.id, body)


@router.get("/{application_id}", response_model=ApplicationRead, response_model_by_alias=True)
async def get_application(application_id: UUID, db: Session, user: Client):
    business_id = get_business_id(user)
    await claim_drafts(db, user)
    return await ApplicationService(db).get(application_id, business_id)


@router.patch("/{application_id}", response_model=ApplicationRead, response_model_by_alias=True)
async def update_application(application_id: UUID, body: ApplicationUpdate, db: Session, user: Client):
    business_id = get_business_id(user)
    await claim_drafts(db, user)
    return await ApplicationService(db).update(application_id, business_id, body, user.id)


@router.post("/{application_id}/submit", response_model=ApplicationRead, response_model_by_alias=True)
async def submit_application(application_id: UUID, db: Session, user: Client, settings: Config, body: SubmitConsent | None = Body(default=None)):
    business_id = get_business_id(user)
    await claim_drafts(db, user)
    return await ApplicationService(db).submit(application_id, business_id, user.id, body, settings)
