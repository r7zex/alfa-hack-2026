from sqlalchemy import select, or_
from app.models.pipeline import ApplicationDocument
from sqlalchemy.orm import undefer
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document
from app.models.loan_application import LoanApplication


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_owned(self, document_id, owner_id, *, with_content=False, admin=False):
        query = select(Document)
        if admin:
            submitted = select(LoanApplication.id).where(LoanApplication.status != 'draft')
            query = query.where(Document.id.in_(
                select(ApplicationDocument.document_id).where(ApplicationDocument.application_id.in_(submitted))))
        else:
            query = query.outerjoin(LoanApplication, Document.application_id == LoanApplication.id).where(
                or_(Document.business_id == owner_id, LoanApplication.business_id == owner_id))
        query = query.where(Document.id == document_id)
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
