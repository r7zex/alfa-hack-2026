# Credit applications — authenticated ownership

Application endpoints now use cookie-based authentication through `require_client`, including CSRF validation from Auth.

- `LoanApplication.id` remains UUID.
- New applications persist `business_id` (FK to `businesses.id`) and `created_by_user_id` (FK to `users.id`), both integer IDs derived from the authenticated session, never from client request bodies.
- Lists, reads, updates, and submission are scoped to the signed-in user's `business_id`. Multiple users belonging to a business can access that business's applications.
- Both foreign keys remain nullable at database level only for pre-migration rows. New records always populate them.
- The legacy `owner_id` is kept as a nullable transition column. The migration backfills records previously keyed `user-<id>` using the existing users table. Previously unclaimed `demo-ip`/`demo-llc` drafts are assigned to their matching demo business on authenticated access; they are not made accessible to ordinary accounts.
- There is no supported unauthenticated `X-Demo-User-Id` access.
- `python -m app.db.init` (or `python -m alembic upgrade head`) applies versioned migrations; do not use `create_all` for production schema changes.
- Documents, tasks, chat, notifications, decisions, model results, offers and schedules now persist in PostgreSQL. Submit enqueues a durable job and returns submitted; the worker runs asynchronously. See [product-operations.md](product-operations.md) and [design.md](design.md).

## Development verification

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests/test_credit.py tests/test_auth.py tests/test_migrations.py tests/test_db_models.py -q
node --test tests/frontend.test.mjs tests/frontend-auth.test.mjs
python -m alembic upgrade head
python -m alembic check
```

Use a disposable test database for Auth tests: its test fixture drops and recreates tables. Never point `TEST_AUTH_DATABASE_URL` at a database containing data you need.

Before merging this branch, test: registering a real business and creating a draft, reopening from a second session, a second authorized user in the same business reading it, another business receiving 404, existing `user-<id>` drafts after migration, and `demo-ip` legacy drafts after demo login.

---

# Integration with server authentication

After merging feat/auth, the routes below use the authenticated client session and
CSRF protection. Application ownership comes from the account in the database.
The previous X-Demo-User-Id header is no longer accepted as authentication.
Product rules, draft autosave, currentStep and submission behavior are preserved.
All schema setup now runs through Alembic at container startup; app.db.init remains
a compatible command for applying the same migrations. Existing drafts survive
migration. The descriptions of demo headers and browser-only accounts below
record the original increment. See [auth.md](auth.md) for the current login flow.

# Credit applications backend — first increment

This is a **synthetic demonstration**, not a real credit underwriting system.

## What's included

- Three fixed products matching `app/static/js/domain.mjs`.
- Persisted `loan_applications` table (UUID primary key, synthetic owner key, product, amount, term, purpose, monthly financial inputs, status, timestamps).
- Owner-scoped create/list/get/update/submit operations, including `currentStep` (0 to 3) for resumable drafts.
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

For local development only, `app.db.init` also adds `current_step` to an existing `loan_applications` table with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. For proper upgrades, use versioned Alembic migrations; do not run ad-hoc DDL in production. No database schema is initialized implicitly when merely opening the frontend.

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
- For the two synthetic accounts (`demo-llc`, `demo-ip`), the frontend now syncs draft fields and the current wizard step via the API, fetches server-side applications at login/reload, and calls `/submit` on final confirmation. Other browser-created demo identities still use local-only storage. Uploaded files and selected document IDs are **not** persisted in PostgreSQL; files are browser-only and may need to be selected again on another device. The admin/analyst demo still uses browser storage and is not a real backend workflow.
- Documents, consents, manual analyst decisions, scoring, BKI/FNS integrations, events and approvals are **not implemented** by this change. Therefore `pending` means accepted for demo processing, not fully verified.
- Rates, product limits and requirements are educational examples rather than bank terms.
- Ownership is checked on every data lookup, but the demo identity header provides no real access control. Do not treat this version as production-ready.

## Draft workflow

- `POST /api/applications` accepts product/amount/months and optionally `currentStep` (0–3, default 0); status is `draft`.
- `PATCH /api/applications/{id}` accepts partial fields and `currentStep`; only drafts are editable.
- Browser autosave (900 ms after changing fields) and Next/Back/Save draft save changes. A valid product/amount/term is required before the first server save; invalid initial terms are not persisted to the server.
- The frontend reopens drafts at their `currentStep` and populates existing values. Saving documents in the browser is not equivalent to uploading them to PostgreSQL.
- Final submission uses `POST /api/applications/{id}/submit` and switches the local view to `pending` only after backend confirmation. Server-side document/consent checks are not yet wired.
- Startup/server synchronization failures are surfaced to the user; existing browser demo records remain available locally.
