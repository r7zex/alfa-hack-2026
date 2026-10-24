"""Application access is scoped to a verified business from Auth."""
from uuid import UUID

from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.loan_application import LoanApplication


class ApplicationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def claim_legacy_demo(self, business_id: int, user_id: int, legacy_key: str | None) -> None:
        if not legacy_key:
            return
        # Claim only unclaimed rows from a known synthetic demo account.
        await self.session.execute(
            update(LoanApplication)
            .where(LoanApplication.owner_id == legacy_key)
            .where(LoanApplication.business_id.is_(None))
            .where(LoanApplication.created_by_user_id.is_(None))
            .values(business_id=business_id, created_by_user_id=user_id)
        )
        await self.session.commit()

    async def get_owned(self, application_id: UUID, business_id: int) -> LoanApplication | None:
        return await self.session.scalar(
            select(LoanApplication).where(
                LoanApplication.id == application_id,
                LoanApplication.business_id == business_id,
            )
        )

    async def list_owned(self, business_id: int) -> list[LoanApplication]:
        rows = await self.session.scalars(
            select(LoanApplication)
            .where(LoanApplication.business_id == business_id)
            .order_by(LoanApplication.created_at.desc())
        )
        return list(rows.all())

    async def add(self, application: LoanApplication) -> LoanApplication:
        self.session.add(application)
        await self.session.commit()
        await self.session.refresh(application)
        return application

    async def save(self, application: LoanApplication) -> LoanApplication:
        await self.session.commit()
        await self.session.refresh(application)
        return application
