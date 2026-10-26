"""Immutable, expiring offer versions and frozen contract text."""
from datetime import timedelta
from decimal import Decimal,ROUND_HALF_UP
from hashlib import sha256
from uuid import uuid4
from sqlalchemy import select
from app.models.pipeline import CreditOffer
from app.services.operations import utcnow
from app.services.loans import schedule
from app.credit_products import validate_product_terms,PRODUCTS


async def create_offer(db,row,*,amount=None,months=None,annual_rate=None,product_id=None,reason='',valid_days=7):
    product_id=product_id or row.product_id
    amount=amount if amount is not None else row.amount
    months=months if months is not None else row.months
    annual_rate=annual_rate if annual_rate is not None else PRODUCTS[product_id].annual_rate
    annual_rate=Decimal(str(annual_rate)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    validate_product_terms(product_id,amount,months)
    plan=schedule(amount,annual_rate,months,overdraft=product_id=='overdraft')
    old=list((await db.scalars(select(CreditOffer).where(CreditOffer.application_id==row.id).order_by(CreditOffer.version))).all())
    for offer in old:
        if offer.status=='offered':offer.status='revoked'
    version=old[-1].version+1 if old else 1
    id_=uuid4()
    text=(f'ДЕМОНСТРАЦИОННЫЙ ДОГОВОР v{version}. Предложение {id_}. Продукт {product_id}. '
          f'Сумма {amount} ₽; срок {months} мес.; ставка {annual_rate}% годовых; '
          f'первый платёж {plan[0]["payment"]} ₽; схема {"проценты и возврат долга в конце" if product_id=="overdraft" else "аннуитет"}. '
          'Условное подписание не является УКЭП. Реальные обязательства и переводы не возникают.')
    offer=CreditOffer(id=id_,application_id=row.id,version=version,product_id=product_id,amount=amount,months=months,
                      annual_rate=annual_rate,monthly_payment=plan[0]['payment'],repayment_mode='interest_and_balloon' if product_id=='overdraft' else 'annuity',
                      principal_due=amount if product_id=='overdraft' else 0,status='offered',reason=reason,
                      expires_at=utcnow()+timedelta(days=valid_days),contract_text=text,contract_sha256=sha256(text.encode()).hexdigest())
    db.add(offer)
    return offer
