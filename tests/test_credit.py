"""Smoke tests independent of PostgreSQL."""
import asyncio
import os
from uuid import uuid4
from datetime import datetime, timezone
from types import SimpleNamespace

from pydantic import ValidationError
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("DB_PASSWORD", "unit-test-only")

from app.credit_products import PRODUCTS, validate_product_terms  # noqa: E402
from app.main import app  # noqa: E402
from app.services.application_service import ApplicationService  # noqa: E402
from app.schemas.loan_application import ApplicationCreate, ApplicationRead, ApplicationUpdate  # noqa: E402


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


def test_applications_require_authenticated_session() -> None:
    # A user-controlled header must never substitute for the new cookie auth.
    with TestClient(app) as client:
        assert client.get("/api/applications").status_code == 401
        assert client.get(
            "/api/applications", headers={"X-Demo-User-Id": "demo-llc"}
        ).status_code == 401

def test_loan_routes_are_registered_in_openapi() -> None:
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "/api/products" in paths
    assert "/api/applications" in paths
    assert "/api/applications/{application_id}/submit" in paths


def test_only_draft_can_be_updated() -> None:
    fake = type("Application", (), {"status": "pending"})()
    service = ApplicationService(AsyncMock())
    service.get = AsyncMock(return_value=fake)

    async def check() -> None:
        with pytest.raises(HTTPException) as exc:
            await service.update(uuid4(), "demo-llc", ApplicationUpdate(amount=150_000))
        assert exc.value.status_code == 409

    asyncio.run(check())


def test_draft_step_accepts_camel_case_and_has_valid_bounds() -> None:
    data = ApplicationCreate.model_validate({
        "productId": "working", "amount": 1_000_000, "months": 12,
        "currentStep": 2,
    })
    assert data.current_step == 2
    assert ApplicationCreate(productId="working", amount=1_000_000, months=12).current_step == 0
    with pytest.raises(ValidationError):
        ApplicationCreate(productId="working", amount=1_000_000, months=12, currentStep=4)
    with pytest.raises(ValidationError):
        ApplicationUpdate(currentStep=-1)


def test_response_serializes_current_step() -> None:
    application = SimpleNamespace(
        id=uuid4(), product_id="working", amount=1_000_000, months=12,
        purpose=None, revenue=None, expenses=None, debt_payment=None,
        current_step=2, status="draft",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    data = ApplicationRead.model_validate(application).model_dump(by_alias=True)
    assert data["currentStep"] == 2
    assert data["productId"] == "working"


def test_can_save_step_and_refuses_null_step() -> None:
    fake = SimpleNamespace(
        status="draft", product_id="working", amount=1_000_000,
        months=12, current_step=0,
    )
    service = ApplicationService(AsyncMock())
    service.get = AsyncMock(return_value=fake)
    service.repo.save = AsyncMock(side_effect=lambda application: application)

    async def check() -> None:
        result = await service.update(uuid4(), "demo-llc", ApplicationUpdate(currentStep=2))
        assert result.current_step == 2
        with pytest.raises(HTTPException) as exc:
            await service.update(uuid4(), "demo-llc", ApplicationUpdate(currentStep=None))
        assert exc.value.status_code == 422

    asyncio.run(check())


def test_incomplete_application_cannot_be_submitted() -> None:
    incomplete = SimpleNamespace(
        status="draft", product_id="working", amount=1_000_000,
        months=12, purpose="Закупка товаров", revenue=None,
        expenses=None, debt_payment=None,
    )
    service = ApplicationService(AsyncMock())
    service.get = AsyncMock(return_value=incomplete)

    async def check() -> None:
        with pytest.raises(HTTPException) as exc:
            await service.submit(uuid4(), "user-1")
        assert exc.value.status_code == 422

    asyncio.run(check())
