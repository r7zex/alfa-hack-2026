"""Tests ported from feat/analyst-cabinet, with server documents and consent."""
from fastapi.testclient import TestClient
from app.main import app
from test_auth import auth_env, signup, csrf
from test_pipeline import upload

def test_analyst_can_filter_by_business_and_decide_once(auth_env):
    factory, settings = auth_env
    settings.demo_auth_enabled = True
    with TestClient(app) as first, TestClient(app) as second, TestClient(app) as admin:
        assert signup(first).status_code == 201
        assert signup(second, type_="ip", email="other@example.com").status_code == 201
        assert admin.post("/api/auth/demo", json={"account": "admin"}).status_code == 200
        assert first.get("/api/analyst/applications").status_code == 403
        assert first.get("/api/analyst/organizations").status_code == 403
        assert TestClient(app).get("/api/analyst/applications").status_code == 401
        def submit(client, amount):
            resp = client.post(
                "/api/applications",
                json={"productId": "working", "amount": amount, "months": 12,
                      "purpose": "Закупка товаров", "revenue": 1500000,
                      "expenses": 700000, "debtPayment": 10000},
                headers=csrf(client),
            )
            assert resp.status_code == 201, resp.text
            aid = resp.json()["id"]
            upload(client, aid, "statement")
            upload(client, aid, "tax" if client.get("/api/auth/me").json()["business"]["type"] == "ip" else "accounts")
            resp = client.post("/api/applications/" + aid + "/submit", headers=csrf(client), json={"demo_data": True, "demo_checks": True})
            assert resp.status_code == 200
            return aid
        first_id = submit(first, 1000000)
        second_id = submit(second, 2000000)
        orgs = admin.get("/api/analyst/organizations")
        assert orgs.status_code == 200
        assert len(orgs.json()) == 2
        org = next(x for x in orgs.json() if x["name"] == "ООО Тест")
        user_id = org["users"][0]["id"]
        listing = admin.get("/api/analyst/applications", params={
            "business_id": org["id"], "created_by_user_id": user_id,
            "sort": "amount_desc",
        })
        assert listing.status_code == 200, listing.text
        assert [x["id"] for x in listing.json()] == [first_id]
        assert listing.json()[0]["creator"]["email"] == "client@example.com"
        assert admin.post("/api/analyst/applications/" + first_id + "/decision",
                          json={"status": "approved"}, headers={}).status_code == 403
        decision = admin.post(
            "/api/analyst/applications/" + first_id + "/decision",
            json={"status": "approved", "comment": "Демо-одобрение", "alternativeAmount": 900000},
            headers=csrf(admin),
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["status"] == "approved"
        assert decision.json()["comment"] == "Демо-одобрение"
        assert decision.json()["decidedByUserId"] is not None
        assert admin.post(
            "/api/analyst/applications/" + first_id + "/decision",
            json={"status": "rejected", "comment": "Повторно"},
            headers=csrf(admin),
        ).status_code == 409
        my_row = first.get("/api/applications/" + first_id).json()
        assert my_row["status"] == "approved"
        assert my_row["comment"] == "Демо-одобрение"
        assert first.get("/api/analyst/applications").status_code == 403
        assert admin.post(
            "/api/analyst/applications/" + second_id + "/decision",
            json={"status": "rejected"},
            headers=csrf(admin),
        ).status_code == 422
        assert admin.post(
            "/api/analyst/applications/" + second_id + "/decision",
            json={"status": "rejected", "comment": "Недостаточно данных"},
            headers=csrf(admin),
        ).status_code == 200


def test_analyst_does_not_read_drafts(auth_env):
    factory, settings = auth_env
    settings.demo_auth_enabled = True
    with TestClient(app) as client, TestClient(app) as admin:
        signup(client)
        admin.post("/api/auth/demo", json={"account": "admin"})
        row = client.post("/api/applications", json={
            "productId": "working", "amount": 1000000, "months": 12,
        }, headers=csrf(client))
        assert row.status_code == 201
        aid = row.json()["id"]
        assert admin.get("/api/analyst/applications", params={"status": "all"}).json() == []
        assert admin.get("/api/analyst/applications/" + aid).status_code == 404
        assert admin.post("/api/analyst/applications/" + aid + "/decision",
                          json={"status": "approved"}, headers=csrf(admin)).status_code == 404
