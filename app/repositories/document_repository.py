from sqlalchemy import select
from sqlalchemy.orm import undefer
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document
from app.models.loan_application import LoanApplication


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_owned(self, document_id, owner_id, *, with_content=False):
        query = select(Document).join(LoanApplication).where(
            Document.id == document_id, LoanApplication.owner_id == owner_id)
        if with_content:
            query = query.options(undefer(Document.content))
        return await self.session.scalar(query)

    async def add(self, document):
        self.session.add(document)
        try:
            await self.session.commit()
            await self.session.refresh(document)
        except BaseException:
            await self.session.rollback()
            raise
        return document
