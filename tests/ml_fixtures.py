"""Explicitly marked, deterministic fixtures. No training CSVs or bank reports."""
import asyncio
from dataclasses import dataclass
from io import BytesIO
import os
os.environ.setdefault("DB_PASSWORD", "unit-test-only")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from app.api import auth, applications, scoring, documents
from app.db.base import Base
from app.db.session import get_db
from app.settings import Settings, get_settings
from app.models.auth import BusinessType
from app.services.scoring_service import ScoringInputs, get_scoring_inputs, get_scoring_predictors
from pyhanko.pdf_utils.writer import PdfFileWriter
from pyhanko.pdf_utils.generic import DictionaryObject, ArrayObject, NumberObject, pdf_name


def pdf_bytes():
    writer = PdfFileWriter()
    page = DictionaryObject({
        pdf_name('/Type'): pdf_name('/Page'),
        pdf_name('/MediaBox'): ArrayObject([NumberObject(n) for n in (0, 0, 200, 200)]),
        pdf_name('/Resources'): DictionaryObject(),
    })
    writer.insert_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class MockSources:
    def __init__(self, registry_scenario="available", bureau_scenario="clean"):
        self.registry_scenario = registry_scenario
        self.bureau_scenario = bureau_scenario

    def registry(self, inn):
        base = {"source": "mock", "inn": inn}
        if self.registry_scenario == "unavailable":
            return {**base, "status": "unavailable"}
        kind = {"9900000017": "legal", "990000000115": "ie"}.get(inn)
        if kind is None:
            return {**base, "status": "not_found"}
        return {**base, "business_type": kind, "status": "active", "registered_at": "2020-01-01"}

    def bureau(self):
        scenario = self.bureau_scenario
        if scenario in {"unavailable", "error"}:
            return {"source": "mock", "status": scenario, "report": None}
        return {"source": "mock", "status": "available", "has_overdue": scenario == "overdue",
                "description": "Test scenario, not an actual credit bureau report"}

    async def collect(self, business, application):
        registry, bureau = self.registry(business.inn), self.bureau()
        if registry["status"] in {"unavailable", "not_found"} or bureau["status"] in {"unavailable", "error"}:
            from ml.train_legal import ScoringError
            raise ScoringError(f"mock source unavailable: registry={registry['status']}; bureau={bureau['status']}")
        return ScoringInputs(features={}, provenance={"registry": "mock", "bureau": "mock", "financials": "mock"},
                             context={"registry": registry, "bureau": bureau,
                                      "financials": {"source": "mock", "revenue": 1000000,
                                                     "expenses": 500000, "debt_payment": 0}})


class ModelInputs(MockSources):
    """Only for the mocked predictor contract; never usable as real 2022 ratios."""
    async def collect(self, business, application):
        result = await super().collect(business, application)
        result.features = {"fixture_feature": 1.0}
        result.provenance["inference"] = "mock"
        return result


def mock_predictor(model_type):
    def predict(path, features):
        assert features == {"fixture_feature": 1.0}
        return {"scores": [0.2], "threshold": 0.5, "classifications": [0],
                "model_type": model_type, "artifact_version": 1, "artifact_id": "mock",
                "target": "bankrupt"}
    return predict


@dataclass
class ApiEnvironment:
    app: FastAPI
    factory: object
    url: str

    def client(self):
        return TestClient(self.app)


def run_db(factory, operation):
    async def run():
        async with factory() as session:
            return await operation(session)
    return asyncio.run(run())


@pytest.fixture
def scoring_env(tmp_path):
    # Use only a disposable test DB: each fixture drops its own schema.
    url = os.environ.get("TEST_SCORING_DATABASE_URL", "sqlite+aiosqlite:///" + str(tmp_path / "scoring.sqlite"))
    engine = create_async_engine(url, poolclass=NullPool,
                                 connect_args={"prepare_threshold": None} if url.startswith("postgresql") else {})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
    asyncio.run(setup())
    app = FastAPI()
    for router in (auth.router, applications.router, scoring.router, documents.router):
        app.include_router(router)
    async def db_override():
        async with factory() as session:
            try:
                yield session
            except BaseException:
                await session.rollback()
                raise
    settings = Settings(_env_file=None, db_password="test-only", auth_requests_per_minute=1000)
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_settings] = lambda: settings
    yield ApiEnvironment(app, factory, url)
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def signup(client, *, kind="llc", email="scoring@example.com"):
    response = client.post("/api/auth/register", json={
        "type": kind, "inn": "9900000017" if kind == "llc" else "990000000115",
        "name": "Макет тестового клиента", "email": email, "password": "Test-Password-123",
    })
    assert response.status_code == 201, response.text


def csrf(client):
    return {"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"]}


def application(client):
    response = client.post("/api/applications", json={
        "productId": "working", "amount": 1000000, "months": 12,
    }, headers=csrf(client))
    assert response.status_code == 201, response.text
    return response.json()["id"]
