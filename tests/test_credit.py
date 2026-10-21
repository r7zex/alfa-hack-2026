"""Smoke tests independent of PostgreSQL."""
import asyncio
import os
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("DB_PASSWORD", "unit-test-only")

from app.credit_products import PRODUCTS, validate_product_terms  # noqa: E402
from app.main import app  # noqa: E402
from app.services.application_service import ApplicationService  # noqa: E402
from app.schemas.loan_application import ApplicationUpdate  # noqa: E402


def test_catalogue_matches_frontend() -> None:
    assert set(PRODUCTS) == {"working", "equipment", "overdraft"}
    with TestClient(app) as client:
        response = client.get("/api/products")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()} == set(PRODUCTS)


@pytest.mark.parametrize(
    "product, amount, months",
    [("working", 100_000, 3), ("equipment", 15_000_000, 60), ("overdraft", 50_000, 1)],
)
def test_valid_limits(product: str, amount: int, months: int) -> None:
    validate_product_terms(product, amount, months)


@pytest.mark.parametrize(
    "product, amount, months",
    [("missing", 100_000, 3), ("working", 99_999, 3), ("overdraft", 50_000, 13)],
)
def test_invalid_limits(product: str, amount: int, months: int) -> None:
    with pytest.raises(ValueError):
        validate_product_terms(product, amount, months)


def test_applications_require_demo_identity() -> None:
    with TestClient(app) as client:
        assert client.get("/api/applications").status_code == 401


def test_only_draft_can_be_updated() -> None:
    fake = type("Application", (), {"status": "pending"})()
    service = ApplicationService(AsyncMock())
    service.get = AsyncMock(return_value=fake)

    async def check() -> None:
        with pytest.raises(HTTPException) as exc:
            await service.update(uuid4(), "demo-llc", ApplicationUpdate(amount=150_000))
        assert exc.value.status_code == 409

    asyncio.run(check())
