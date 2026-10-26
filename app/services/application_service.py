"""Application drafts and submissions use the shared authenticated business."""
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.credit_products import validate_product_terms
from app.models.loan_application import LoanApplication
from app.models.document import Document
from app.models.pipeline import ApplicationEvent, ApplicationDocument
from app.repositories.application_repository import ApplicationRepository
from app.schemas.loan_application import ApplicationCreate, ApplicationUpdate
from app.services.pipeline import EDITABLE, event, process


def check_terms(product_id, amount, months):
    try:
        validate_product_terms(product_id, amount, months)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class ApplicationService:
    def __init__(self, session: AsyncSession):
        self.repo = ApplicationRepository(session)

    async def attach(self, row, ids):
        if ids is None:
            return
        ids = set(ids)
        found = set((await self.repo.session.scalars(select(Document.id).where(
            Document.id.in_(ids), Document.business_id == row.business_id))).all())
        if found != ids:
            raise HTTPException(404, 'Документ не найден в вашей организации')
        await self.repo.session.execute(delete(ApplicationDocument).where(ApplicationDocument.application_id == row.id))
        self.repo.session.add_all([ApplicationDocument(application_id=row.id, document_id=id_) for id_ in ids])

    async def create(self, business_id: int, user_id: int, payload: ApplicationCreate):
        check_terms(payload.product_id, payload.amount, payload.months)
        values = payload.model_dump(exclude={'document_ids'})
        row = LoanApplication(id=uuid4(), business_id=business_id, created_by_user_id=user_id,
                              version=0, status='draft', **values)
        self.repo.session.add(row)
        await self.repo.session.flush()
        await self.attach(row, payload.document_ids)
        self.repo.session.add(ApplicationEvent(application_id=row.id, version=0, actor_id=user_id,
                                               old_status=None, new_status='draft', reason='Черновик создан', details={}))
        return await self.repo.add(row)

    async def list_owned(self, business_id):
        return await self.repo.list_owned(business_id)

    async def get(self, application_id, business_id):
        row = await self.repo.get_owned(application_id, business_id)
        if row is None:
            raise HTTPException(404, 'Application not found')
        return row

    async def update(self, application_id, business_id, payload: ApplicationUpdate, user_id=None):
        row = await self.get(application_id, business_id)
        if row.status not in EDITABLE:
            raise HTTPException(409, 'Only drafts and requested clarifications can be changed')
        changes = payload.model_dump(exclude_unset=True, exclude={'document_ids'})
        for key in ('product_id', 'amount', 'months', 'current_step', 'mock_scenario'):
            if key in changes and changes[key] is None:
                raise HTTPException(422, f'{key} cannot be null')
        check_terms(changes.get('product_id', row.product_id), changes.get('amount', row.amount), changes.get('months', row.months))
        await event(self.repo.session, row, user_id, row.status, 'Данные заявки обновлены')
        for key, value in changes.items():
            setattr(row, key, value)
        await self.attach(row, payload.document_ids)
        return await self.repo.save(row)

    async def submit(self, application_id, business_id, user_id=None, consent=None, settings=None):
        row = await self.get(application_id, business_id)
        if row.status not in EDITABLE:
            if row.status in {'pending', 'processing', 'submitted', 'approved', 'rejected', 'offer_accepted', 'signed', 'disbursed', 'offer_declined', 'processing_error', 'completed', 'data_check', 'enrichment', 'scoring', 'decision', 'counter_offer', 'escalated', 'cancelled'}:
                return row
            raise HTTPException(409, 'Application cannot be submitted')
        check_terms(row.product_id, row.amount, row.months)
        if not row.purpose or not row.purpose.strip():
            raise HTTPException(422, 'Purpose is required')
        if row.revenue is None or row.revenue <= 0 or row.expenses is None or row.debt_payment is None:
            raise HTTPException(422, 'Financial information is incomplete')
        if consent is None or not consent.demo_data or not consent.demo_checks:
            raise HTTPException(422, 'Подтвердите синтетические данные и согласие на демонстрационные проверки')
        from app.models.operations import ApplicationTask
        open_task = await self.repo.session.scalar(select(ApplicationTask.id).where(ApplicationTask.application_id==row.id,ApplicationTask.status=='OPEN',ApplicationTask.required.is_(True)).limit(1))
        if open_task:raise HTTPException(409, 'Сначала выполните обязательные задачи банка')
        await event(self.repo.session, row, user_id, 'submitted', 'Заявка отправлена', consent.model_dump())
        if settings is not None and settings.pipeline_async_enabled:
            from app.services.jobs import enqueue
            await enqueue(self.repo.session,row)
            return await self.repo.save(row)
        await event(self.repo.session, row, None, 'processing', 'Начаты демонстрационные проверки')
        await process(self.repo.session, row)
        return await self.repo.save(row)
