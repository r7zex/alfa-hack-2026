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
    'draft': {'submitted', 'cancelled'}, 'needs_info': {'submitted', 'cancelled'}, 'submitted': {'processing', 'data_check', 'cancelled'},
    'processing': {'pending', 'processing_error'}, 'processing_error': {'processing', 'submitted', 'cancelled'},
    'pending': {'needs_info', 'approved', 'counter_offer', 'rejected', 'escalated', 'cancelled'},
    'approved': {'offer_accepted', 'offer_declined', 'needs_info', 'pending', 'cancelled'},
    'data_check': {'enrichment', 'needs_info', 'processing_error'},
    'enrichment': {'scoring', 'processing_error', 'rejected'},
    'scoring': {'decision', 'processing_error'},
    'decision': {'pending', 'approved', 'counter_offer', 'rejected', 'needs_info', 'processing_error'},
    'counter_offer': {'offer_accepted', 'offer_declined', 'pending', 'cancelled'},
    'escalated': {'pending', 'approved', 'counter_offer', 'rejected', 'needs_info', 'cancelled'},
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
    if new_status != old and new_status in {'submitted','pending','approved','counter_offer','rejected','needs_info','escalated','signed','disbursed','processing_error'}:
        from app.services.operations import notify
        await notify(db,row,f'state:{row.id}:{version+1}',new_status,reason)
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
                           .order_by(CreditOffer.version.desc()).limit(1).execution_options(populate_existing=True))


async def decide(db, row, admin, payload):
    # A legacy approval has no versioned offer/contract. An analyst can explicitly
    # request clarification before creating verified terms through the normal flow.
    if row.status == 'approved' and payload.status == 'needs_info' and await latest_offer(db, row) is None:
        row.decision_comment = payload.comment
        row.decided_by_user_id, row.decided_at = admin.id, now()
        await event(db, row, admin.id, 'needs_info', payload.comment, {'legacy_approval_review': True})
        return
    from app.models.user import UserRole
    from app.models.operations import DecisionRecord, ApplicationTask
    from app.services.policy_rules import active_rules
    from app.services.offers import create_offer
    if row.status not in {'pending','escalated'}:
        raise HTTPException(409,'Заявка не ожидает решения аналитика')
    if payload.status=='pending' and row.status!='escalated':
        raise HTTPException(409,'Возврат доступен только для эскалации')
    if row.status=='escalated' and admin.role not in {UserRole.ADMIN,UserRole.APPROVER}:
        raise HTTPException(403,'Эскалацию рассматривает согласующий')
    if row.assigned_to_user_id not in (None,admin.id) and admin.role==UserRole.UNDERWRITER:
        raise HTTPException(409,'Заявка находится в работе другого сотрудника')
    run=await latest_run(db,row)
    if run is None:
        business=await db.get(Business,row.business_id)
        if not business:raise HTTPException(409,'Привязка организации отсутствует')
        checks=mock_checks(row.mock_scenario,row);docs=await documents_for(db,row)
        risk,policy=evaluate(row,checks,[d.document_type for d in docs],business.type.value)
        run=ProcessingRun(application_id=row.id,application_version=row.version,checks=checks,risk=risk,policy=policy)
        db.add(run)
    version,rules=await active_rules(db)
    if run.policy.get('rules_snapshot'):
        rules=run.policy['rules_snapshot'];version=run.policy['version']
    terms_snapshot={}
    if payload.status in {'approved','counter_offer'}:
        if run.policy['recommendation'] in {'technical_error','request_info','recommend_rejection'}:
            raise HTTPException(409,'Одобрение недоступно: устраните замечания проверок')
        amount=payload.alternative_amount or row.amount
        months=payload.months or row.months
        product_id=payload.product_id or row.product_id
        from app.credit_products import PRODUCTS
        rate=payload.annual_rate if payload.annual_rate is not None else PRODUCTS[product_id].annual_rate if product_id in PRODUCTS else None
        if amount>rules['underwriter_limit'] and admin.role==UserRole.UNDERWRITER:
            raise HTTPException(403,'Сумма выше полномочий аналитика; передайте на согласование')
        if amount>row.amount:raise HTTPException(422,'Сумма превышает запрос клиента')
        try:validate_product_terms(product_id,amount,months)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        from app.services.credit_policy import payment
        cash=(row.revenue or 0)-(row.expenses or 0)
        if payment(amount,months,float(rate))+(row.debt_payment or 0)>cash*rules['max_debt_burden']:
            raise HTTPException(422,'Предложение превышает допустимую долговую нагрузку')
        if run.policy['recommendation']=='alternative_terms' and amount>run.policy['alternative_amount']:
            raise HTTPException(422,'Сумма превышает допустимую по демо-политике')
        if product_id=='equipment' and not any(d.document_type=='invoice' for d in await documents_for(db,row)):
            raise HTTPException(409,'Для оборудования нужен документ поставщика')
        await create_offer(db,row,amount=amount,months=months,annual_rate=rate,product_id=product_id,
                           reason=payload.comment,valid_days=payload.valid_days or rules['offer_valid_days'])
        terms_snapshot=dict(amount=amount,months=months,annual_rate=float(rate),product_id=product_id)
    if payload.status=='needs_info':
        for task in payload.tasks:
            db.add(ApplicationTask(application_id=row.id,created_by=admin.id,**task.model_dump()))
        if not payload.tasks:
            from app.services.operations import ensure_tasks
            await ensure_tasks(db,row,run.policy.get('missing_documents',[]),payload.comment)
    row.decision_comment=payload.comment or None;row.alternative_amount=payload.alternative_amount
    row.decided_by_user_id=admin.id;row.decided_at=now();row.assigned_to_user_id=None if payload.status in {'escalated','pending'} else admin.id
    reason=payload.comment or 'Аналитик одобрил демонстрационное предложение'
    await event(db,row,admin.id,payload.status,reason,{'rules_version':version,'automatic':False,'terms':terms_snapshot})
    db.add(DecisionRecord(application_id=row.id,actor_id=admin.id,rules_version=version,action=payload.status,reason=reason,terms=terms_snapshot))


async def offer_action(db, row, user, action, offer_id, acknowledged=False, contract_hash=None):
    from app.services.operations import aware
    if action in {"accept", "sign", "disburse"} and not user.can_sign:
        raise HTTPException(403, "Нужно право подписи организации")
    offer = await latest_offer(db, row)
    if not offer or offer.id != offer_id:
        raise HTTPException(409, 'Версия предложения устарела или отсутствует')
    if action == 'accept':
        if offer.status in {'accepted', 'signed', 'disbursed'}:
            return
        if offer.expires_at and aware(offer.expires_at)<=now():
            raise HTTPException(409,'Срок предложения истёк')
        if row.status not in {'approved','counter_offer'} or offer.status != 'offered':
            raise HTTPException(409, 'Предложение недоступно')
        if not acknowledged:
            raise HTTPException(422, 'Подтвердите согласие с предложенными условиями')
        offer.status, offer.accepted_by, offer.accepted_at = 'accepted', user.id, now()
        offer.consent = dict(terms_accepted=True, offer_version=offer.version, at=now().isoformat())
        await event(db, row, user.id, 'offer_accepted', 'Клиент принял предложение', {'offer_id': str(offer.id)})
    elif action == 'decline':
        if offer.status == 'declined':
            return
        if row.status not in {'approved','counter_offer'}:
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
        from app.services.loans import new_loan
        db.add(new_loan(row,offer))
        db.add(DemoDisbursement(application_id=row.id, offer_id=offer.id, amount=offer.amount))
        offer.status = 'disbursed'
        await event(db, row, user.id, 'disbursed', 'Моделируемая выдача завершена; реальные деньги не переводились')
    else:
        raise HTTPException(404, 'Операция не найдена')
