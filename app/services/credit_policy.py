"""Reproducible educational rules, unrelated to Alfa Bank's lending policy.

Risk points are not bankruptcy probability or credit PD. No model is inferred.
"""
from datetime import datetime, timezone
from math import floor, ceil
from app.credit_products import PRODUCTS, validate_product_terms

DISCLAIMER = 'Демонстрационные правила v1; не политика Альфа-Банка, не PD и не прогноз банкротства.'


def payment(amount, months, annual_rate):
    r = annual_rate / 1200
    return ceil(amount * r / (1 - (1 + r) ** -months))


def terms(product_id, amount, months):
    product = PRODUCTS[product_id]
    overdraft = product_id == 'overdraft'
    return dict(amount=amount, months=months, annual_rate=product.annual_rate,
                monthly_payment=ceil(amount * product.annual_rate / 1200) if overdraft else payment(amount, months, product.annual_rate),
                repayment_mode='interest_and_balloon' if overdraft else 'annuity',
                principal_due=amount if overdraft else 0)


def mock_checks(scenario, application=None):
    # These are synthetic adapters, never actual registry/bureau confirmations.
    now = datetime.now(timezone.utc).isoformat()
    payloads = {
        'mock_egrul_egrip_v1': {'active': scenario != 'negative'},
        'mock_bki_v1': {'overdue': scenario == 'negative',
                        'monthly_debt_payment': application.debt_payment if application else 0},
        'mock_financials_v1': {'revenue_monthly': application.revenue if application else None,
                               'expenses_monthly': application.expenses if application else None,
                               'derived_from': 'synthetic_application'},
    }
    return [dict(source=source, status=scenario, synthetic=True, received_at=now,
                 data=data if scenario in {'success', 'negative'} else None)
            for source, data in payloads.items()]


def evaluate(application, checks, document_types, business_type):
    required = {'statement', 'tax' if business_type == 'ip' else 'accounts'}
    if application.product_id == 'equipment':
        required.add('invoice')
    missing = sorted(required - set(document_types))
    statuses = {c['status'] for c in checks}
    cash = (application.revenue or 0) - (application.expenses or 0)
    debt = application.debt_payment or 0
    p = PRODUCTS[application.product_id]
    installment = payment(application.amount, application.months, p.annual_rate)
    if p.id == 'overdraft':
        installment = ceil(application.amount / application.months + application.amount * p.annual_rate / 1200)
    burden = (debt + installment) / max(cash, 1)
    risk = dict(kind='demo_rule_based', version=1, points=min(100, max(0, round(burden * 100))),
                debt_service_ratio=round(burden, 4), disclaimer=DISCLAIMER)
    decision, reasons, alternative = 'recommend_approval', ['Денежный поток покрывает платежи по демонстрационным правилам'], None
    if statuses & {'unavailable', 'malformed'}:
        decision, reasons = 'technical_error', ['Mock-источник недоступен или вернул некорректный ответ; повторите проверку']
    elif 'negative' in statuses or cash <= debt:
        decision, reasons = 'recommend_rejection', ['Негативная mock-проверка или недостаточный свободный денежный поток']
    elif 'missing' in statuses or missing:
        decision, reasons = 'request_info', ['Нет сведений mock-источника или обязательных документов: ' + ', '.join(missing)]
    elif burden > .5:
        unit = installment / application.amount
        affordable = floor(max(0, cash * .5 - debt) / unit)
        if affordable >= p.min_amount:
            decision, reasons, alternative = 'alternative_terms', ['Сниженная сумма ограничивает демо-долговую нагрузку 50%'], min(application.amount, affordable)
        else:
            decision, reasons = 'recommend_rejection', ['Даже минимальная сумма превышает демонстрационную долговую нагрузку 50%']
    return risk, dict(version=1, recommendation=decision, reasons=reasons, alternative_amount=alternative,
                      missing_documents=missing, disclaimer=DISCLAIMER)


def recommendations(purpose, amount, months):
    ranked = []
    for p in PRODUCTS.values():
        try:
            validate_product_terms(p.id, amount, months)
        except ValueError:
            continue
        words = {'equipment': ('оборуд', 'станок', 'транспорт'), 'working': ('товар', 'запас', 'оборот'),
                 'overdraft': ('разрыв', 'сроч', 'поступлен')}
        match = any(w in purpose.casefold() for w in words[p.id])
        score = 2 if match else 0
        if p.id == 'overdraft' and months <= 3:
            score += 1
        ranked.append(dict(productId=p.id, score=score,
                           reason='Соответствует цели, сумме и сроку' if match else 'Допустим по сумме и сроку; доступен для самостоятельного выбора'))
    return sorted(ranked, key=lambda x: (-x['score'], x['productId']))
