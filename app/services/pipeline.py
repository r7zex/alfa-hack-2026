"""Transactional state machine; locks plus CAS protect every consequential write."""
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select, update, func, or_
from app.models.auth import Business
from app.models.loan_application import LoanApplication
from app.models.document import Document
from app.models.pipeline import (ApplicationDocument, ApplicationEvent, ProcessingRun,
                                 CreditOffer, DemoContract, DemoDisbursement)
from app.services.credit_policy import evaluate, mock_checks, terms
from app.credit_products import validate_product_terms

EDITABLE = {'draft', 'needs_info'}
REVIEW = {'pending'}
TRANSITIONS = {
    'draft': {'submitted'}, 'needs_info': {'submitted'}, 'submitted': {'processing'},
    'processing': {'pending', 'processing_error'}, 'processing_error': {'processing'},
    'pending': {'needs_info', 'approved', 'rejected'},
    'approved': {'offer_accepted', 'offer_declined', 'needs_info'},
    'offer_accepted': {'signed'}, 'signed': {'disbursed'},
}


def now():
    return datetime.now(timezone.utc)


async def locked(db, application_id, business_id=None, *, admin=False):
    query = select(LoanApplication).where(LoanApplication.id == application_id)
    if not admin:
        query = query.where(LoanApplication.business_id == business_id)
    row = await db.scalar(query.with_for_update().execution_options(populate_existing=True))
    if row is None or (admin and row.status == 'draft'):
        raise HTTPException(404, 'Заявка не найдена')
    return row


async def event(db, row, actor_id, new_status, reason, details=None):
    old, version = row.status, row.version
    if new_status != old and new_status not in TRANSITIONS.get(old, set()):
        raise HTTPException(409, 'Недопустимый переход состояния')
    result = await db.execute(update(LoanApplication).where(
        LoanApplication.id == row.id, LoanApplication.version == version,
        LoanApplication.status == old,
    ).values(status=new_status, version=version + 1, updated_at=now())
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, 'Заявка изменена параллельным запросом; обновите страницу')
    row.status, row.version = new_status, version + 1
    db.add(ApplicationEvent(application_id=row.id, version=version + 1, actor_id=actor_id,
                            old_status=old, new_status=new_status, reason=reason, details=details or {}))


async def documents_for(db, row):
    return list((await db.scalars(select(Document).join(
        ApplicationDocument, ApplicationDocument.document_id == Document.id
    ).where(ApplicationDocument.application_id == row.id)
      .order_by(Document.created_at, Document.id))).all())


async def process(db, row):
    business = await db.get(Business, row.business_id)
    if business is None:
        raise HTTPException(422, 'Для проверки необходима организация')
    checks = mock_checks(row.mock_scenario, row)
    docs = await documents_for(db, row)
    risk, policy = evaluate(row, checks, [d.document_type for d in docs], business.type.value)
    run = ProcessingRun(application_id=row.id, application_version=row.version, checks=checks, risk=risk, policy=policy)
    db.add(run)
    await event(db, row, None, 'processing_error' if policy['recommendation'] == 'technical_error' else 'pending',
                '; '.join(policy['reasons']), dict(recommendation=policy['recommendation']))
    return run


async def latest_run(db, row):
    return await db.scalar(select(ProcessingRun).where(ProcessingRun.application_id == row.id)
                           .order_by(ProcessingRun.application_version.desc()).limit(1))


async def latest_offer(db, row):
    return await db.scalar(select(CreditOffer).where(CreditOffer.application_id == row.id)
                           .order_by(CreditOffer.version.desc()).limit(1))


async def decide(db, row, admin, payload):
    # A legacy approval has no versioned offer/contract. An analyst can explicitly
    # request clarification before creating verified terms through the normal flow.
    if row.status == 'approved' and payload.status == 'needs_info' and await latest_offer(db, row) is None:
        row.decision_comment = payload.comment
        row.decided_by_user_id, row.decided_at = admin.id, now()
        await event(db, row, admin.id, 'needs_info', payload.comment, {'legacy_approval_review': True})
        return
    if row.status not in REVIEW:

        raise HTTPException(409, 'Заявка не ожидает решения аналитика')
    run = await latest_run(db, row)
    # Pre-integration pending applications receive a reproducible assessment too.
    if run is None:
        await event(db, row, admin.id, row.status, 'Проверка ранее отправленной заявки')
        business = await db.get(Business, row.business_id)
        if not business:
            raise HTTPException(409, 'Привязка организации отсутствует')
        checks = mock_checks(row.mock_scenario, row)
        docs = await documents_for(db, row)
        risk, policy = evaluate(row, checks, [d.document_type for d in docs], business.type.value)
        run = ProcessingRun(application_id=row.id, application_version=row.version, checks=checks, risk=risk, policy=policy)
        db.add(run)
    if payload.status == 'approved':
        recommendation = run.policy['recommendation']
        if recommendation in {'technical_error', 'request_info', 'recommend_rejection'}:
            raise HTTPException(409, 'Одобрение недоступно: устраните замечания проверок')
        amount = payload.alternative_amount or row.amount
        if recommendation == 'alternative_terms' and amount > run.policy['alternative_amount']:
            raise HTTPException(422, 'Сумма превышает допустимую по демо-политике')
        try:
            validate_product_terms(row.product_id, amount, row.months)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if amount > row.amount:
            raise HTTPException(422, 'Предложение не может превышать запрошенную сумму')
        previous = await latest_offer(db, row)
        version = previous.version + 1 if previous else 1
        values = terms(row.product_id, amount, row.months)
        offer_id = uuid4()
        text = (f'ДЕМОНСТРАЦИОННЫЙ ДОГОВОР v{version}. Предложение {offer_id}. '
                f'Сумма {amount} ₽, срок {row.months} мес., ставка {values["annual_rate"]}% годовых, '
                f'платёж {values["monthly_payment"]} ₽. Схема: {values["repayment_mode"]}; '
                f'основной долг к концу срока {values["principal_due"]} ₽. '
                'Учебная симуляция. Реальные обязательства и банковские операции не возникают.')
        db.add(CreditOffer(id=offer_id, application_id=row.id, version=version,
                           **values, status='offered', contract_text=text,
                           contract_sha256=sha256(text.encode()).hexdigest()))
    row.decision_comment = payload.comment or None
    row.alternative_amount = payload.alternative_amount
    row.decided_by_user_id, row.decided_at = admin.id, now()
    await event(db, row, admin.id, payload.status, payload.comment or 'Аналитик одобрил демонстрационное предложение')


async def offer_action(db, row, user, action, offer_id, acknowledged=False, contract_hash=None):
    offer = await latest_offer(db, row)
    if not offer or offer.id != offer_id:
        raise HTTPException(409, 'Версия предложения устарела или отсутствует')
    if action == 'accept':
        if offer.status in {'accepted', 'signed', 'disbursed'}:
            return
        if row.status != 'approved' or offer.status != 'offered':
            raise HTTPException(409, 'Предложение недоступно')
        if not acknowledged:
            raise HTTPException(422, 'Подтвердите согласие с предложенными условиями')
        offer.status, offer.accepted_by, offer.accepted_at = 'accepted', user.id, now()
        offer.consent = dict(terms_accepted=True, offer_version=offer.version, at=now().isoformat())
        await event(db, row, user.id, 'offer_accepted', 'Клиент принял предложение', {'offer_id': str(offer.id)})
    elif action == 'decline':
        if offer.status == 'declined':
            return
        if row.status != 'approved':
            raise HTTPException(409, 'Предложение нельзя отклонить в этом состоянии')
        offer.status = 'declined'
        await event(db, row, user.id, 'offer_declined', 'Клиент отклонил предложение')
    elif action == 'sign':
        if offer.status in {'signed', 'disbursed'}:
            return
        if row.status != 'offer_accepted' or offer.status != 'accepted':
            raise HTTPException(409, 'Сначала примите предложение')
        if not acknowledged or contract_hash != offer.contract_sha256:
            raise HTTPException(422, 'Подтвердите ознакомление с актуальной версией демо-договора')
        db.add(DemoContract(offer_id=offer.id, signed_by=user.id,
                            contract_sha256=offer.contract_sha256, acknowledgment=True))
        offer.status = 'signed'
        await event(db, row, user.id, 'signed', 'Выполнено демонстрационное подписание')
    elif action == 'disburse':
        if offer.status == 'disbursed':
            return
        if row.status != 'signed' or offer.status != 'signed':
            raise HTTPException(409, 'Сначала подпишите демо-договор')
        db.add(DemoDisbursement(application_id=row.id, offer_id=offer.id, amount=offer.amount))
        offer.status = 'disbursed'
        await event(db, row, user.id, 'disbursed', 'Моделируемая выдача завершена; реальные деньги не переводились')
    else:
        raise HTTPException(404, 'Операция не найдена')
