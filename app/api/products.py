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
