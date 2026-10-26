"""Decimal, calendar-month repayment schedules; no real payment operations."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from app.models.operations import LoanAccount

CENT=Decimal('.01')
def money(value):return Decimal(str(value)).quantize(CENT,rounding=ROUND_HALF_UP)

def month_date(start,n):
    y,m=divmod(start.year*12+start.month-1+n,12)
    return date(y,m+1,min(start.day,monthrange(y,m+1)[1]))


def schedule(amount,rate,months,start=None,*,overdraft=False):
    if amount<=0 or months<1 or rate<0:raise ValueError('Invalid loan terms')
    start=start or date.today()
    rest=money(amount);r=Decimal(str(rate))/Decimal(1200)
    installment=money(rest/months if r==0 else rest*r/(1-(1+r)**(-months)))
    result=[]
    for n in range(1,months+1):
        opening=rest;interest=money(opening*r)
        if overdraft:principal=opening if n==months else Decimal(0)
        else:principal=opening if n==months else min(opening,max(Decimal(0),installment-interest))
        rest=money(opening-principal)
        result.append(dict(number=n,date=month_date(start,n).isoformat(),opening=str(opening),
                           interest=str(interest),principal=str(principal),payment=str(money(principal+interest)),closing=str(rest)))
    if rest!=0 or sum(Decimal(row['principal']) for row in result)!=money(amount):
        raise ValueError('Schedule does not reconcile')
    return result


def new_loan(row,offer,issued_at=None):
    loan=LoanAccount(id=uuid4(),application_id=row.id,offer_id=offer.id,business_id=row.business_id,
                       contract_number='DEMO-'+str(offer.id).upper(),product_id=offer.product_id or row.product_id,
                       amount=offer.amount,months=offer.months,annual_rate=offer.annual_rate,
                       schedule=schedule(offer.amount,offer.annual_rate,offer.months,issued_at.date() if issued_at else None,
                                         overdraft=offer.repayment_mode=='interest_and_balloon'))
    if issued_at:loan.issued_at=issued_at
    return loan
