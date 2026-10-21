# Credit applications backend — first increment

This is a **synthetic demonstration**, not a real credit underwriting system.

## What's included

- Three fixed products matching `app/static/js/domain.mjs`.
- Persisted `loan_applications` table (UUID primary key, synthetic owner key, product, amount, term, purpose, monthly financial inputs, status, timestamps).
- Owner-scoped create/list/get/update/submit operations.
- `draft -> pending` transition; only drafts are editable. Repeat submit of already pending application returns the existing result.
- FastAPI OpenAPI documentation under `/docs`.

## One-time database initialization

Start PostgreSQL as described in the root README, then run:

```bash
python -m app.db.init
```

For Docker-only deployment, after `docker compose up --build -d`, run:

```bash
docker compose exec app python -m app.db.init
```

This MVP uses explicit SQLAlchemy `create_all`; it **does not alter existing tables**. Before further schema changes, introduce Alembic migrations. No database schema is initialized implicitly when merely opening the demo frontend.

## API examples

```bash
curl http://127.0.0.1:8000/api/products
curl -X POST http://127.0.0.1:8000/api/applications \
  -H "X-Demo-User-Id: demo-llc" -H "Content-Type: application/json" \
  -d '{"productId":"working","amount":1000000,"months":12}'
curl http://127.0.0.1:8000/api/applications \
  -H "X-Demo-User-Id: demo-llc"
```

Continue with `PATCH /api/applications/{id}` to add `purpose`, `revenue`, `expenses` and `debtPayment`, then `POST /api/applications/{id}/submit`.

## Explicit scope limitations

- `X-Demo-User-Id` accepts only `demo-llc` or `demo-ip`; **it is NOT authentication**, can be forged, and must be replaced with authenticated identity **before exposing these endpoints publicly**. This is only for isolated synthetic development.
- The frontend still uses browser storage and does **not** call these API endpoints. Its integration is a separate task.
- Documents, consents, manual analyst decisions, scoring, BKI/FNS integrations, events and approvals are **not implemented** by this change. Therefore `pending` means accepted for demo processing, not fully verified.
- Rates, product limits and requirements are educational examples rather than bank terms.
- Ownership is checked on every data lookup, but the demo identity header provides no real access control. Do not treat this version as production-ready.
