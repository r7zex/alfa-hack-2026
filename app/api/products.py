"""Read-only demo credit product catalogue."""
from fastapi import APIRouter

from app.credit_products import PRODUCTS

router = APIRouter(prefix="/api/products", tags=["Products"])


@router.get("")
async def list_products() -> list[dict]:
    return [
        {
            "id": p.id,
            "name": p.name,
            "min": p.min_amount,
            "max": p.max_amount,
            "months": [p.min_months, p.max_months],
            "rate": p.annual_rate,
        }
        for p in PRODUCTS.values()
    ]


@router.get('/recommendations')
async def recommend(purpose: str = '', amount: int = 1_000_000, months: int = 12):
    from app.services.credit_policy import recommendations
    from fastapi import HTTPException
    if len(purpose) > 500 or amount <= 0 or months <= 0:
        raise HTTPException(422, 'Укажите корректные цель, сумму и срок')
    return recommendations(purpose, amount, months)


from pydantic import BaseModel,Field,ConfigDict
from app.api.applications import Client,Session

class FinancialRecommendation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    purpose:str=Field(max_length=500)
    amount:int=Field(gt=0,le=1000000000)
    months:int=Field(ge=1,le=120)
    revenue:int=Field(gt=0,le=10000000000)
    expenses:int=Field(ge=0,le=10000000000)
    debt_payment:int=Field(ge=0,le=10000000000)
    has_collateral:bool=False


@router.post('/recommendations')
async def recommend_financial(body:FinancialRecommendation,db:Session,user:Client):
    from app.services.policy_rules import recommend_financial as calculate
    from app.models.business import Business
    business=await db.get(Business,user.business_id)
    return calculate(body.purpose,body.amount,body.months,business,body.revenue,body.expenses,body.debt_payment,body.has_collateral)
