# Bank analyst cabinet (hackathon MVP)

The existing Auth module already supports bank staff: role `admin`, `require_admin` on server endpoints, and an HttpOnly PostgreSQL-backed session.

**Why the employee button redirects to a login form:** `DEMO_AUTH_ENABLED=false` is the default. To use the one-click synthetic admin in local development, set `DEMO_AUTH_ENABLED=true` in `.env` and restart FastAPI. The button then calls `POST /api/auth/demo` with `{"account":"admin"}`. Do not enable it on shared deployments with real users or data. Alternatively, create a password-based admin using `python -m app.admin --email admin@example.com`.

## API

All endpoints require a bank admin session; POST decisions additionally require `X-CSRF-Token`.

- `GET /api/analyst/organizations` — organizations with submitted applications, their IDs/INNs, submitting users and counts.
- `GET /api/analyst/applications` — submitted loans, default `status=pending`. Filters: `business_id`, `created_by_user_id`, `query` (company/INN/email), `status` (`pending`, `approved`, `rejected`, `completed`, `all`), `sort` (`newest`, `oldest`, `amount_desc`, `amount_asc`, `organization`). Up to 500 records for the hackathon demo.
- `GET /api/analyst/applications/{id}` — financial information, business and creator (not draft).
- `POST /api/analyst/applications/{id}/decision` — `{"status":"approved","comment":"...","alternativeAmount":900000}` or `{"status":"rejected","comment":"Required explanation"}`.

The decision is persisted to PostgreSQL as `status`, `decision_comment`, `alternative_amount`, `decided_at` and `decided_by_user_id`. A row lock protects the decision transition from concurrent overwrites in PostgreSQL. A submitted application can be decided only once; a repeated attempt returns 409. Clients see the new status and comment after refreshing their cabinet. Analyst endpoints never reveal drafts.

The UI reuses `app/static/js/analyst.mjs`; filters, organization/user selection and decisions read/write the API instead of browser `localStorage`.

**Integrated scope:** Documents, assessments, decisions, offer acceptance, demo contracts and
simulated issuance are persisted in PostgreSQL. The workflow endpoint supplies the audit trail
and checks to the analyst. A decision may also be `needs_info` (comment required), allowing
client clarification and resubmission. Approval is blocked for missing/negative/failed checks.
Alternative amounts must meet product limits and the demo affordability rule. For complete
states and API payloads see README.md and docs/design.md.

## Local test

```bash
git branch --show-current  # feat/integrated-credit-pipeline
python -m pytest tests/test_auth.py tests/test_credit.py tests/test_migrations.py -q
node --test tests/frontend.test.mjs tests/frontend-auth.test.mjs
python -m alembic upgrade head
python -m alembic check
```

Use a disposable test DB for the Auth test fixture: it drops tables during setup; never set `TEST_AUTH_DATABASE_URL` to the local database containing data you want to retain.

Test browser flow: (1) submit a synthetic client application, (2) in a separate browser profile log in with the demo or password-based admin, (3) filter by organization/email and approve or reject, (4) refresh the client cabinet to see the result, (5) verify a client gets 403 on analyst endpoints and an unauthorized decision gets 403 without CSRF.
