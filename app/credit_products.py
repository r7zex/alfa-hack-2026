"""Demo credit product catalogue; must match app/static/js/domain.mjs."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CreditProduct:
    id: str
    name: str
    min_amount: int
    max_amount: int
    min_months: int
    max_months: int
    annual_rate: int


PRODUCTS = {
    product.id: product
    for product in (
        CreditProduct("working", "Оборотный кредит", 100_000, 5_000_000, 3, 24, 24),
        CreditProduct("equipment", "На оборудование", 300_000, 15_000_000, 6, 60, 21),
        CreditProduct("overdraft", "Овердрафт", 50_000, 2_000_000, 1, 12, 26),
    )
}


def validate_product_terms(product_id: str, amount: int, months: int) -> None:
    product = PRODUCTS.get(product_id)
    if product is None:
        raise ValueError("Unknown credit product")
    if not product.min_amount <= amount <= product.max_amount:
        raise ValueError(f"Amount must be between {product.min_amount} and {product.max_amount}")
    if not product.min_months <= months <= product.max_months:
        raise ValueError(f"Term must be between {product.min_months} and {product.max_months} months")
