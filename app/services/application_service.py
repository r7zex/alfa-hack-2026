"""Application state transitions and credit terms validation."""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.credit_products import validate_product_terms
from app.models.loan_application import LoanApplication
from app.repositories.application_repository import ApplicationRepository
from app.schemas.loan_application import ApplicationCreate, ApplicationUpdate


def check_terms(product_id: str, amount: int, months: int) -> None:
    try:
        validate_product_terms(product_id, amount, months)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ApplicationService:
    def __init__(self, session: AsyncSession):
        self.repo = ApplicationRepository(session)

    async def create(self, owner_id: str, payload: ApplicationCreate) -> LoanApplication:
        check_terms(payload.product_id, payload.amount, payload.months)
        return await self.repo.add(LoanApplication(
            owner_id=owner_id,
            **payload.model_dump(),
        ))

    async def list_owned(self, owner_id: str) -> list[LoanApplication]:
        return await self.repo.list_owned(owner_id)

    async def get(self, application_id: UUID, owner_id: str) -> LoanApplication:
        application = await self.repo.get_owned(application_id, owner_id)
        if application is None:
            raise HTTPException(status_code=404, detail="Application not found")
        return application

    async def update(self, application_id: UUID, owner_id: str, payload: ApplicationUpdate) -> LoanApplication:
        application = await self.get(application_id, owner_id)
        if application.status != "draft":
            raise HTTPException(status_code=409, detail="Only drafts can be changed")
        changes = payload.model_dump(exclude_unset=True)
        # Explicit null is supported only for optional financial/text fields.
        for required in ("product_id", "amount", "months", "current_step"):
            if required in changes and changes[required] is None:
                raise HTTPException(status_code=422, detail=f"{required} cannot be null")
        check_terms(
            changes.get("product_id", application.product_id),
            changes.get("amount", application.amount),
            changes.get("months", application.months),
        )
        for key, value in changes.items():
            setattr(application, key, value)
        return await self.repo.save(application)

    async def submit(self, application_id: UUID, owner_id: str) -> LoanApplication:
        application = await self.get(application_id, owner_id)
        if application.status == "pending":
            return application  # Repeated submit is safe for this basic transition.
        if application.status != "draft":
            raise HTTPException(status_code=409, detail="Application cannot be submitted")
        check_terms(application.product_id, application.amount, application.months)
        if not application.purpose or not application.purpose.strip():
            raise HTTPException(status_code=422, detail="Purpose is required")
        if (application.revenue is None or application.revenue <= 0 or
                application.expenses is None or application.debt_payment is None):
            raise HTTPException(status_code=422, detail="Financial information is incomplete")
        # Document and consent checks will be integrated with their services.
        application.status = "pending"
        return await self.repo.save(application)
