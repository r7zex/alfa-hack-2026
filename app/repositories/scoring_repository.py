from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.scoring_result import ScoringResult


class ScoringRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def latest(self, application_id):
        return await self.session.scalar(select(ScoringResult).where(
            ScoringResult.application_id == application_id).order_by(
                ScoringResult.computed_at.desc(), ScoringResult.id.desc()).limit(1))

    async def add(self, result):
        self.session.add(result)
        try:
            await self.session.commit()
            await self.session.refresh(result)
        except BaseException:
            await self.session.rollback()
            raise
        return result
