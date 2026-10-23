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
