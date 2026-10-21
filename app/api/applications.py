"""Credit application endpoints; temporary synthetic demo identity."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.loan_application import ApplicationCreate, ApplicationRead, ApplicationUpdate
from app.services.application_service import ApplicationService

router = APIRouter(prefix="/api/applications", tags=["Applications"])


def get_demo_owner(x_demo_user_id: Annotated[str | None, Header()] = None) -> str:
    # NOT authentication. Only intended for local synthetic test accounts.
    if x_demo_user_id not in ("demo-llc", "demo-ip"):
        raise HTTPException(status_code=401, detail="Use a synthetic X-Demo-User-Id")
    return x_demo_user_id


Session = Annotated[AsyncSession, Depends(get_db)]
Owner = Annotated[str, Depends(get_demo_owner)]


@router.get("", response_model=list[ApplicationRead], response_model_by_alias=True)
@router.get("/my", response_model=list[ApplicationRead], response_model_by_alias=True, include_in_schema=False)
async def list_applications(db: Session, owner: Owner):
    return await ApplicationService(db).list_owned(owner)


@router.post("", response_model=ApplicationRead, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
async def create_application(body: ApplicationCreate, db: Session, owner: Owner):
    return await ApplicationService(db).create(owner, body)


@router.get("/{application_id}", response_model=ApplicationRead, response_model_by_alias=True)
async def get_application(application_id: UUID, db: Session, owner: Owner):
    return await ApplicationService(db).get(application_id, owner)


@router.patch("/{application_id}", response_model=ApplicationRead, response_model_by_alias=True)
async def update_application(application_id: UUID, body: ApplicationUpdate, db: Session, owner: Owner):
    return await ApplicationService(db).update(application_id, owner, body)


@router.post("/{application_id}/submit", response_model=ApplicationRead, response_model_by_alias=True)
async def submit_application(application_id: UUID, db: Session, owner: Owner):
    return await ApplicationService(db).submit(application_id, owner)
