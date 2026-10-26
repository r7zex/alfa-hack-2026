"""Bank analyst endpoints: role-checked access to submitted applications."""
from typing import Annotated, Literal
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.dependencies import require_bank
from app.models.auth import User
from app.models.loan_application import LoanApplication
from app.schemas.loan_application import AnalystApplicationRead

router = APIRouter(prefix="/api/analyst", tags=["Analyst"])
Db = Annotated[AsyncSession, Depends(get_db)]
Admin = Annotated[User, Depends(require_bank)]


class TaskRequest(BaseModel):
    model_config = {'extra':'forbid'}
    kind: Literal['document','information']
    title: str = Field(min_length=1,max_length=255)
    description: str = Field(default='',max_length=2000)
    required: bool = True
    document_type: Literal['statement','accounts','tax','invoice'] | None = None
    due_at: datetime | None = None

    @model_validator(mode='after')
    def validate_kind(self):
        if self.kind=='document' and not self.document_type:raise ValueError('Укажите тип документа')
        return self


class DecisionRequest(BaseModel):
    model_config = {'extra':'forbid'}
    expected_version: int = Field(ge=0,alias='expectedVersion',description='Version of the application actually reviewed by the bank employee')
    status: Literal["approved", "rejected", "needs_info", "counter_offer", "escalated", "pending"]
    comment: str = Field(default="", max_length=1500)
    alternative_amount: int | None = Field(
        default=None, ge=1, le=1_000_000_000, alias="alternativeAmount",
    )

    months: int | None = Field(default=None,ge=1,le=120)
    annual_rate: Decimal | None = Field(default=None,ge=1,le=60,max_digits=4,decimal_places=2)
    product_id: str | None = Field(default=None,max_length=40)
    valid_days: int | None = Field(default=None,ge=1,le=30)
    tasks: list[TaskRequest] = Field(default_factory=list,max_length=20)

    @model_validator(mode="after")
    def check_comment(self):
        self.comment = self.comment.strip()
        if self.status in {"rejected", "needs_info", "counter_offer", "escalated"} and not self.comment:
            raise ValueError("Для отказа укажите причину")
        return self


def with_relations():
    return (
        selectinload(LoanApplication.business),
        selectinload(LoanApplication.creator),
    )


@router.get("/applications", response_model=list[AnalystApplicationRead])
async def list_applications(
    db: Db, admin: Admin,
    status: str = Query(default="pending",max_length=24),
    mine: bool = False,
    business_id: int | None = Query(default=None, ge=1),
    created_by_user_id: int | None = Query(default=None, ge=1),
    query: str = Query(default="", max_length=100),
    sort: Literal["newest", "oldest", "amount_desc", "amount_asc", "organization"] = "newest",
):
    statement = select(LoanApplication).options(*with_relations())
    # Drafts are private to their business, not available to bank analysts.
    if status == "all":
        statement = statement.where(LoanApplication.status != "draft")
    else:
        statement = statement.where(LoanApplication.status == status)
    if mine:
        statement=statement.where(LoanApplication.assigned_to_user_id==admin.id)
    if business_id is not None:
        statement = statement.where(LoanApplication.business_id == business_id)
    if created_by_user_id is not None:
        statement = statement.where(LoanApplication.created_by_user_id == created_by_user_id)
    if query.strip():
        term = f"%{query.strip()}%"
        from app.models.business import Business
        from app.models.user import User as LoanUser
        statement = (
            statement
            .outerjoin(Business, LoanApplication.business_id == Business.id)
            .outerjoin(LoanUser, LoanApplication.created_by_user_id == LoanUser.id)
            .where(
                Business.name.ilike(term)
                | Business.inn.ilike(term)
                | LoanUser.email.ilike(term)
            )
        )
    if sort == "organization":
        from app.models.business import Business
        # Joining the same business twice would be ambiguous when searching.
        if not query.strip():
            statement = statement.outerjoin(Business, LoanApplication.business_id == Business.id)
        statement = statement.order_by(Business.name.asc(), LoanApplication.created_at.desc())
    elif sort == "oldest":
        statement = statement.order_by(LoanApplication.created_at.asc())
    elif sort == "amount_desc":
        statement = statement.order_by(LoanApplication.amount.desc(), LoanApplication.created_at.desc())
    elif sort == "amount_asc":
        statement = statement.order_by(LoanApplication.amount.asc(), LoanApplication.created_at.desc())
    else:
        statement = statement.order_by(LoanApplication.created_at.desc())
    rows = await db.scalars(statement.limit(500))
    return list(rows.all())


@router.get("/organizations")
async def organizations(db: Db, admin: Admin):
    del admin
    from app.models.business import Business
    from app.models.user import User as LoanUser
    rows = await db.execute(
        select(
            Business.id, Business.name, Business.inn,
            func.count(LoanApplication.id).label("applications"),
        )
        .join(LoanApplication, LoanApplication.business_id == Business.id)
        .where(LoanApplication.status != "draft")
        .group_by(Business.id, Business.name, Business.inn)
        .order_by(Business.name)
    )
    companies = []
    for id_, name, inn, count in rows:
        users = await db.execute(
            select(LoanUser.id, LoanUser.email)
            .join(LoanApplication, LoanApplication.created_by_user_id == LoanUser.id)
            .where(LoanApplication.business_id == id_, LoanApplication.status != "draft")
            .distinct().order_by(LoanUser.email)
        )
        companies.append({
            "id": id_, "name": name, "inn": inn, "applications": count,
            "users": [{"id": uid, "email": email} for uid, email in users],
        })
    return companies


@router.get("/applications/{application_id}", response_model=AnalystApplicationRead)
async def application_detail(application_id: UUID, db: Db, admin: Admin):
    del admin
    row = await db.scalar(
        select(LoanApplication).options(*with_relations())
        .where(LoanApplication.id == application_id, LoanApplication.status != "draft")
    )
    if row is None:
        raise HTTPException(404, "Заявка не найдена")
    return row


@router.post("/applications/{application_id}/decision", response_model=AnalystApplicationRead)
async def decide(application_id: UUID, payload: DecisionRequest, db: Db, admin: Admin):
    from app.services.pipeline import locked, decide as apply_decision
    row = await locked(db, application_id, admin=True)
    if row.version!=payload.expected_version:
        raise HTTPException(409,'Заявка изменилась после просмотра. Обновите данные и повторно проверьте решение')
    await apply_decision(db, row, admin, payload)
    await db.commit()
    return await application_detail(application_id, db, admin)
