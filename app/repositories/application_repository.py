"""DB operations for owner-scoped applications."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.loan_application import LoanApplication


class ApplicationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_owned(self, application_id: UUID, owner_id: str) -> LoanApplication | None:
        return await self.session.scalar(
            select(LoanApplication).where(
                LoanApplication.id == application_id, LoanApplication.owner_id == owner_id
            )
        )

    async def list_owned(self, owner_id: str) -> list[LoanApplication]:
        rows = await self.session.scalars(
            select(LoanApplication)
            .where(LoanApplication.owner_id == owner_id)
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
