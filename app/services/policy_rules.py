"""Versioned educational rules and explainable product affordability."""
from datetime import date
from math import floor
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from app.models.operations import PolicyVersion, SystemSetting
from app.credit_products import PRODUCTS
from app.services.credit_policy import payment, evaluate


class RuleDefinition(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_debt_burden:float=Field(default=.5,gt=0,le=.8)
    min_cash_buffer:int=Field(default=50000,ge=0,le=10000000)
    auto_limit:int=Field(default=1500000,ge=0,le=15000000)
    underwriter_limit:int=Field(default=5000000,ge=50000,le=15000000)
    min_business_months:int=Field(default=6,ge=0,le=120)
    offer_valid_days:int=Field(default=7,ge=1,le=30)


async def active_rules(db):
    from app.services.operations import upsert
    default=RuleDefinition().model_dump()
    await db.execute(upsert(db,PolicyVersion).values(id=1,definition=default).on_conflict_do_nothing())
    await db.execute(upsert(db,SystemSetting).values(key='active_policy',value={'version':1}).on_conflict_do_nothing())
    setting=await db.get(SystemSetting,'active_policy')
    row=await db.get(PolicyVersion,setting.value['version'])
    return row.id,dict(row.definition)


def business_age(business):
    if not business.registration:return None
    today=date.today()
    return max(0,(today.year-business.registration.year)*12+today.month-business.registration.month)


def assess(row,checks,docs,business,rules,version):
    risk,policy=evaluate(row,checks,[d.document_type for d in docs],business.type.value)
    cash=(row.revenue or 0)-(row.expenses or 0)
    rate=PRODUCTS[row.product_id].annual_rate
    installment=payment(row.amount,row.months,rate)
    if row.product_id=='overdraft':installment=row.amount/row.months+row.amount*rate/1200
    burden=((row.debt_payment or 0)+installment)/max(1,cash)
    capacity=max(0,min(cash*rules['max_debt_burden']-(row.debt_payment or 0),cash-rules['min_cash_buffer']-(row.debt_payment or 0)))
    affordable=floor(capacity/max(installment/row.amount,1e-9))
    age=business_age(business)
    hard_stop='negative' in {c['status'] for c in checks} or cash<=(row.debt_payment or 0)
    if policy['recommendation'] not in {'technical_error','request_info'} and not hard_stop:
        policy.update(recommendation='recommend_approval',alternative_amount=None,
                      reasons=['Денежный поток покрывает платёж по действующей версии демонстрационных правил'])
        if cash-(row.debt_payment or 0)<rules['min_cash_buffer']:
            policy.update(recommendation='recommend_rejection',reasons=['Свободный денежный поток меньше демонстрационного финансового запаса'])
        elif age is not None and age<rules['min_business_months']:
            policy.update(recommendation='recommend_rejection',reasons=['Срок работы бизнеса меньше демонстрационного минимума'])
        elif row.amount>affordable:
            if affordable>=PRODUCTS[row.product_id].min_amount:
                policy.update(recommendation='alternative_terms',alternative_amount=min(row.amount,affordable),reasons=['Меньшая сумма сохраняет финансовый запас и допустимую долговую нагрузку'])
            else:policy.update(recommendation='recommend_rejection',reasons=['Нет доступной суммы в пределах долговой нагрузки'])
    policy.update(version=version,rules_snapshot=rules,age_months=age,
                  max_affordable_amount=max(0,affordable),requires_escalation=row.amount>rules['underwriter_limit'])
    risk.update(debt_service_ratio=round(burden,4),version=version)
    return risk,policy


def recommend_financial(purpose,amount,months,business,revenue,expenses,debt_payment,has_collateral=False):
    from app.services.credit_policy import recommendations
    matches={r['productId']:r for r in recommendations(purpose,amount,months)}
    cash=revenue-expenses
    age=business_age(business) if business else None
    rows=[]
    for product in PRODUCTS.values():
        in_limits=product.min_amount<=amount<=product.max_amount and product.min_months<=months<=product.max_months
        use_months=min(product.max_months,max(product.min_months,months))
        reserve=max(0,cash*.5-debt_payment)
        factor=payment(1000000,use_months,product.annual_rate)/1000000
        available=max(0,min(product.max_amount,floor(reserve/factor)))
        eligible=in_limits and available>=amount and (age is None or age>=6)
        reasons=[]
        if not in_limits:reasons.append('Сумма или срок вне лимитов продукта')
        if available<amount:reasons.append('Платёж превышает доступный денежный поток')
        if age is not None and age<6:reasons.append('Бизнес работает менее 6 месяцев')
        if not reasons:reasons.append(matches.get(product.id,{}).get('reason','Допустим по финансовым параметрам'))
        rows.append(dict(productId=product.id,eligible=eligible,compatibility='подходит' if eligible else 'нужны другие условия',
                         reasons=reasons,available_amount=available,months=use_months,annual_rate=product.annual_rate,
                         monthly_payment=payment(min(product.max_amount,max(product.min_amount,amount)),use_months,product.annual_rate),
                         has_collateral=has_collateral,collateral_required=False,business_type=business.type.value if business else None,
                         business_age_months=age,score=(10 if eligible else 0)+matches.get(product.id,{}).get('score',0)))
    return sorted(rows,key=lambda r:-r['score'])
