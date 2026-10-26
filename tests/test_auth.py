"""End-to-end auth requests with a real SQL database, cookies and CSRF."""

import asyncio
import os
from datetime import timedelta
from uuid import UUID

os.environ.setdefault("DB_PASSWORD", "unit-test-only")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session import get_db
from app.main import app
from app.models.auth import AuthSession, Base, Business, User
from app.security import digest, verify_password
from app.services.auth import utcnow
from app.settings import Settings, get_settings

PASSWORD = "Correct-Horse-123"


@pytest.fixture
def auth_env(tmp_path):
    # TEST_AUTH_DATABASE_URL can point at a disposable PostgreSQL database.
    url = os.environ.get(
        "TEST_AUTH_DATABASE_URL", "sqlite+aiosqlite:///" + str(tmp_path / "auth.sqlite")
    )
    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        poolclass=NullPool,
        connect_args={"prepare_threshold": None}
        if url.startswith("postgresql")
        else {},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(_env_file=None, db_password="test-only", pipeline_async_enabled=False, signing_require_code=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

    async def override_db():
        async with factory() as db:
            try:
                yield db
            except BaseException:
                await db.rollback()
                raise

    asyncio.run(setup())
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    yield factory, settings
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


def signup(client, type_="llc", email="client@example.com", **extra):
    return client.post(
        "/api/auth/register",
        json={
            "type": type_,
            "inn": "9900000017" if type_ == "llc" else "990000000115",
            "name": "ООО Тест" if type_ == "llc" else "Анна Соколова",
            "email": email,
            "password": PASSWORD,
            **extra,
        },
    )


def csrf(client):
    return {"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"]}


def run_db(factory, operation):
    async def run():
        async with factory() as db:
            return await operation(db)

    return asyncio.run(run())


@pytest.mark.parametrize("type_", ["ip", "llc"])
def test_register_login_restore_and_logout(auth_env, type_):
    factory, settings = auth_env
    with TestClient(app) as client:
        response = signup(client, type_, "Client@Example.com")
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["user"]["email"] == "client@example.com"
        assert body["user"]["role"] == "client"
        assert body["user"]["business"]["type"] == type_
        assert "password" not in response.text and "token_hash" not in response.text
        assert "HttpOnly" in response.headers.get_list("set-cookie")[0]
        assert "SameSite=lax" in response.headers.get_list("set-cookie")[0]
        raw_token = client.cookies[settings.session_cookie_name]

        async def inspect(db):
            user = await db.scalar(select(User))
            session = await db.scalar(select(AuthSession))
            assert user.password_hash.startswith("$argon2id$")
            assert verify_password(PASSWORD, user.password_hash)
            assert session.token_hash == digest(raw_token) != raw_token

        run_db(factory, inspect)
        assert client.get("/api/auth/me").status_code == 200
        old_cookies = dict(client.cookies)
        assert client.post("/api/auth/logout", headers=csrf(client)).status_code == 204
        assert client.get("/api/auth/me").status_code == 401
        with TestClient(app) as replay:
            replay.cookies.update(old_cookies)
            assert replay.get("/api/auth/me").status_code == 401
        response = client.post(
            "/api/auth/login",
            json={"email": "CLIENT@example.com", "password": PASSWORD},
        )
        assert response.status_code == 200, response.text
        assert client.cookies[settings.session_cookie_name] != raw_token
        assert client.get("/api/auth/me").headers["cache-control"] == "no-store"


def test_validation_conflicts_and_rollback(auth_env):
    factory, _ = auth_env
    with TestClient(app) as client:
        assert signup(client, password="short").status_code == 422
        assert signup(client, name="   ").status_code == 422
        assert signup(client, inn="9900000018").status_code == 422
        assert signup(client, type_="ip", inn="9900000017").status_code == 422
        assert signup(client, role="admin").status_code == 422
        assert signup(client).status_code == 201
        assert signup(client).status_code == 409
        assert signup(client, email="second@example.com").status_code == 409
        assert signup(client, type_="ip").status_code == 409

        async def count(db):
            assert await db.scalar(select(func.count()).select_from(User)) == 1
            assert await db.scalar(select(func.count()).select_from(Business)) == 1

        run_db(factory, count)


def test_login_failure_is_generic_and_does_not_create_session(auth_env):
    with TestClient(app) as client:
        signup(client)
        client.post("/api/auth/logout", headers=csrf(client))
        first = client.post(
            "/api/auth/login", json={"email": "client@example.com", "password": "wrong"}
        )
        second = client.post(
            "/api/auth/login",
            json={"email": "missing@example.com", "password": "wrong"},
        )
        assert first.status_code == second.status_code == 401
        assert first.json() == second.json()
        assert client.get("/api/auth/me").status_code == 401


def test_csrf_origin_and_cookie_expiry(auth_env):
    factory, settings = auth_env
    with TestClient(app) as client:
        assert client.post(
            "/api/auth/register",
            json={},
            headers={"Origin": "https://attacker.example"},
        ).status_code in (403, 422)
        signup(client)
        assert client.post("/api/auth/logout").status_code == 403
        assert (
            client.post(
                "/api/auth/logout", headers={"X-CSRF-Token": "fake"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/auth/logout",
                headers={**csrf(client), "Origin": "https://attacker.example"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/auth/logout",
                headers={**csrf(client), "Sec-Fetch-Site": "cross-site"},
            ).status_code
            == 403
        )
        assert client.get("/api/auth/me").status_code == 200
        client.cookies.delete(settings.csrf_cookie_name)
        assert client.get("/api/auth/csrf").status_code == 200
        assert client.post("/api/auth/logout", headers=csrf(client)).status_code == 204
        signup_result = client.post(
            "/api/auth/login",
            json={"email": "client@example.com", "password": PASSWORD},
        )
        assert signup_result.status_code == 200

        async def expire(db):
            await db.execute(
                update(AuthSession).values(expires_at=utcnow() - timedelta(seconds=1))
            )
            await db.commit()

        run_db(factory, expire)
        assert client.get("/api/auth/me").status_code == 401
        client.cookies.set(settings.session_cookie_name, "forged")
        assert client.get("/api/auth/me").status_code == 401


def test_multiple_sessions_revocation_and_ownership(auth_env):
    with TestClient(app) as first, TestClient(app) as second, TestClient(app) as third:
        signup(first)
        signup(third, type_="ip", email="other@example.com")
        second.post(
            "/api/auth/login",
            json={"email": "client@example.com", "password": PASSWORD},
        )
        sessions = first.get("/api/auth/sessions").json()
        assert len(sessions) == 2
        other = next(s for s in sessions if not s["current"])
        assert (
            third.delete(
                "/api/auth/sessions/" + other["id"], headers=csrf(third)
            ).status_code
            == 404
        )
        assert (
            first.delete(
                "/api/auth/sessions/" + other["id"], headers=csrf(first)
            ).status_code
            == 204
        )
        assert second.get("/api/auth/me").status_code == 401
        second.post(
            "/api/auth/login",
            json={"email": "client@example.com", "password": PASSWORD},
        )
        assert (
            first.post("/api/auth/logout-all", headers=csrf(first)).status_code == 204
        )
        assert second.get("/api/auth/me").status_code == 401
        assert third.get("/api/auth/me").status_code == 200


def test_login_rotates_existing_session(auth_env):
    with TestClient(app) as client:
        signup(client)
        old = dict(client.cookies)
        response = client.post(
            "/api/auth/login",
            json={"email": "client@example.com", "password": PASSWORD},
        )
        assert response.status_code == 200
        assert len(client.get("/api/auth/sessions").json()) == 1
        with TestClient(app) as replay:
            replay.cookies.update(old)
            assert replay.get("/api/auth/me").status_code == 401


def test_password_change_revokes_all_sessions(auth_env):
    with TestClient(app) as first, TestClient(app) as second:
        signup(first)
        second.post(
            "/api/auth/login",
            json={"email": "client@example.com", "password": PASSWORD},
        )
        assert (
            first.post(
                "/api/auth/password",
                json={"current_password": "wrong", "new_password": "new-secret-123"},
                headers=csrf(first),
            ).status_code
            == 400
        )
        assert (
            first.post(
                "/api/auth/password",
                json={"current_password": PASSWORD, "new_password": "new-secret-123"},
                headers=csrf(first),
            ).status_code
            == 204
        )
        assert first.get("/api/auth/me").status_code == 401
        assert second.get("/api/auth/me").status_code == 401
        assert (
            first.post(
                "/api/auth/login",
                json={"email": "client@example.com", "password": PASSWORD},
            ).status_code
            == 401
        )
        assert (
            first.post(
                "/api/auth/login",
                json={"email": "client@example.com", "password": "new-secret-123"},
            ).status_code
            == 200
        )


@pytest.mark.parametrize(
    "type_,ogrn,kpp",
    [("ip", "123456789012345", ""), ("llc", "1234567890123", "123456789")],
)
def test_profile_persists_and_cannot_change_identity(auth_env, type_, ogrn, kpp):
    with TestClient(app) as client:
        signup(client, type_)
        body = {
            "name": "Новое название",
            "contact": "Иван",
            "ogrn": ogrn,
            "kpp": kpp,
            "okved": "47.91",
            "registration": "2024-01-01",
            "address": "Тестовая улица",
            "phone": "+79990000000",
        }
        response = client.patch("/api/auth/profile", json=body, headers=csrf(client))
        assert response.status_code == 200, response.text
        profile = response.json()["business"]
        assert all(profile[key] == value for key, value in body.items())
        assert client.get("/api/auth/me").json()["business"] == profile
        assert (
            client.patch(
                "/api/auth/profile",
                json={**body, "role": "admin"},
                headers=csrf(client),
            ).status_code
            == 422
        )
        assert (
            client.patch(
                "/api/auth/profile",
                json={**body, "inn": "0000000000"},
                headers=csrf(client),
            ).status_code
            == 422
        )
        assert (
            client.patch(
                "/api/auth/profile",
                json={**body, "ogrn": "", "kpp": ""},
                headers=csrf(client),
            ).status_code
            == 200
        )


def test_demo_flag_and_real_role_protection(auth_env):
    _, settings = auth_env
    with TestClient(app) as client:
        signup(client)
        assert client.get("/api/auth/admin/me").status_code == 403
        assert (
            client.post("/api/auth/demo", json={"account": "admin"}).status_code == 404
        )
        settings.demo_auth_enabled = True
        response = client.post("/api/auth/demo", json={"account": "admin"})
        assert response.status_code == 200, response.text
        assert response.json()["user"]["role"] == "admin"
        assert client.get("/api/auth/admin/me").status_code == 200
        assert client.post("/api/auth/demo", json={"account": "ip"}).status_code == 200
        assert client.get("/api/auth/admin/me").status_code == 403
        assert client.post("/api/auth/demo", json={"account": "ip"}).status_code == 200


def test_demo_never_takes_over_a_normal_account(auth_env):
    _, settings = auth_env
    with TestClient(app) as client:
        signup(client, email="admin@demo.example.com")
        settings.demo_auth_enabled = True
        assert (
            client.post("/api/auth/demo", json={"account": "admin"}).status_code == 409
        )
        assert client.get("/api/auth/me").json()["role"] == "client"


def test_rate_limit_persists_across_clients(auth_env):
    _, settings = auth_env
    settings.auth_requests_per_minute = 2
    with TestClient(app) as first, TestClient(app) as second:
        data = {"email": "missing@example.com", "password": "wrong"}
        assert first.post("/api/auth/login", json=data).status_code == 401
        assert second.post("/api/auth/login", json=data).status_code == 401
        response = second.post("/api/auth/login", json=data)
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) >= 1


def test_secure_cookie_configuration(auth_env):
    _, settings = auth_env
    settings.cookie_secure = True
    with TestClient(app, base_url="https://testserver") as client:
        response = signup(client)
        assert response.status_code == 201
        assert all("Secure" in c for c in response.headers.get_list("set-cookie"))
        assert client.get("/api/auth/me").status_code == 200


def test_real_admin_uses_password_and_has_no_business(auth_env):
    factory, _ = auth_env
    from app.models.auth import UserRole
    from app.security import hash_password

    async def add_admin(db):
        db.add(
            User(
                email="admin@example.com",
                password_hash=hash_password(PASSWORD),
                role=UserRole.ADMIN,
            )
        )
        await db.commit()

    run_db(factory, add_admin)
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD}
        )
        assert response.status_code == 200
        assert response.json()["user"]["business"] is None
        assert response.json()["user"]["is_demo"] is False
        assert client.get("/api/auth/admin/me").status_code == 200


def test_cross_site_login_and_register_are_rejected(auth_env):
    with TestClient(app) as client:
        response = signup(client)
        assert response.status_code == 201
        credentials = {"email": "client@example.com", "password": PASSWORD}
        response = client.post(
            "/api/auth/login",
            json=credentials,
            headers={"Origin": "https://attacker.example"},
        )
        assert response.status_code == 403
        response = client.post(
            "/api/auth/register",
            json={
                "email": "other@example.com",
                "password": PASSWORD,
                "name": "Other",
                "type": "ip",
                "inn": "990000000115",
            },
            headers={"Origin": "https://attacker.example"},
        )
        assert response.status_code == 403


def test_simultaneous_registration_has_one_account_and_one_business(auth_env):
    from concurrent.futures import ThreadPoolExecutor

    factory, _ = auth_env

    def request():
        with TestClient(app) as client:
            return signup(client).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: request(), range(2)))
    assert sorted(results) == [201, 409]

    async def inspect(db):
        assert await db.scalar(select(func.count()).select_from(User)) == 1
        assert await db.scalar(select(func.count()).select_from(Business)) == 1

    run_db(factory, inspect)


def test_applications_use_the_authenticated_owner_and_csrf(auth_env):
    with TestClient(app) as first, TestClient(app) as second, TestClient(app) as guest:
        signup(first)
        signup(second, type_="ip", email="other@example.com")
        payload = {
            "productId": "working",
            "amount": 1000000,
            "months": 12,
            "currentStep": 1,
        }
        assert (
            guest.get(
                "/api/applications", headers={"X-Demo-User-Id": "demo-llc"}
            ).status_code
            == 401
        )
        assert first.post("/api/applications", json=payload).status_code == 403
        response = first.post("/api/applications", json=payload, headers=csrf(first))
        assert response.status_code == 201, response.text
        application_id = response.json()["id"]
        async def check_links(db):
            from app.models.loan_application import LoanApplication
            row = await db.get(LoanApplication, UUID(application_id))
            user = await db.scalar(select(User).where(User.email == "client@example.com"))
            assert row.business_id == user.business_id
            assert row.created_by_user_id == user.id
            assert row.owner_id is None
        run_db(auth_env[0], check_links)
        assert first.get("/api/applications").json()[0]["id"] == application_id
        assert (
            second.get(
                "/api/applications", headers={"X-Demo-User-Id": "demo-llc"}
            ).json()
            == []
        )
        assert second.get("/api/applications/" + application_id).status_code == 404
        assert (
            second.patch(
                "/api/applications/" + application_id,
                json={"amount": 2000000},
                headers=csrf(second),
            ).status_code
            == 404
        )
        response = first.patch(
            "/api/applications/" + application_id,
            json={
                "purpose": "Товары",
                "revenue": 1800000,
                "expenses": 900000,
                "debtPayment": 0,
                "currentStep": 3,
            },
            headers=csrf(first),
        )
        assert response.status_code == 200
        assert response.json()["currentStep"] == 3
        response = first.post(
            "/api/applications/" + application_id + "/submit", headers=csrf(first), json={"demo_data": True, "demo_checks": True}
        )
        assert response.status_code == 200 and response.json()["status"] == "pending"
        assert first.post("/api/auth/logout", headers=csrf(first)).status_code == 204
        assert first.get("/api/applications/" + application_id).status_code == 401


def test_demo_auth_keeps_legacy_application_ownership(auth_env):
    factory, settings = auth_env
    settings.demo_auth_enabled = True
    from app.models.loan_application import LoanApplication

    async def seed_legacy(db):
        row = LoanApplication(
            owner_id="demo-ip",
            product_id="working",
            amount=1000000,
            months=12,
            current_step=2,
        )
        db.add(row)
        await db.commit()
        return str(row.id)

    application_id = run_db(factory, seed_legacy)
    with TestClient(app) as client:
        assert client.post("/api/auth/demo", json={"account": "ip"}).status_code == 200
        response = client.get("/api/applications")
        assert response.status_code == 200
        assert response.json()[0]["id"] == application_id
        assert response.json()[0]["currentStep"] == 2

def test_same_business_colleague_can_access_loan(auth_env):
    factory, _ = auth_env
    from app.security import hash_password
    with TestClient(app) as first, TestClient(app) as colleague:
        assert signup(first).status_code == 201
        async def add_colleague(db):
            user = await db.scalar(select(User).where(User.email == "client@example.com"))
            db.add(User(email="colleague@example.com", password_hash=hash_password(PASSWORD), business_id=user.business_id))
            await db.commit()
        run_db(factory, add_colleague)
        response = first.post("/api/applications", json={"productId": "working", "amount": 1000000, "months": 12}, headers=csrf(first))
        assert response.status_code == 201
        loan_id = response.json()["id"]
        assert colleague.post("/api/auth/login", json={"email": "colleague@example.com", "password": PASSWORD}).status_code == 200
        assert colleague.get("/api/applications").json()[0]["id"] == loan_id
        assert colleague.patch("/api/applications/" + loan_id, json={"currentStep": 2}, headers=csrf(colleague)).status_code == 200
