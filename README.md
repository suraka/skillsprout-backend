# SkillSprout backend

Python 3.12 · FastAPI · async SQLAlchemy · PostgreSQL · Alembic · Firebase Authentication.

This implements the V0.1 parent-guided learning milestone from `skillsprout_backend_spec_v0.1.md`. The frontend is a separate repository. The API is runnable code; it is **not yet deployed to a live PostgreSQL/Firebase environment**.

## Implemented

- Firebase ID-token verification with revocation checks; local account creation on first login.
- Parent-owned learner profiles with minimal personal data and a ten-profile limit.
- Public published-course catalog, ordered modules and protected lesson content.
- Idempotent enrollment, per-lesson progress, automatic course completion.
- Administrator course/module/lesson authoring, editing, draft/review/publish lifecycle.
- UUID keys, foreign keys, uniqueness/check constraints, CITEXT email and JSONB lesson content.
- Audit records, request identifiers, CORS allowlist, explicit errors and transaction rollback.
- Six starter courses and 18 original activity lessons, loaded by an idempotent seed command.
- Docker, local PostgreSQL Compose, Railway configuration, locked dependencies and CI against PostgreSQL.

Payments/subscriptions, quizzes, certificates, AI tutors and course-generation agents are deliberately deferred by the attached V0.1 specification. Paid enrollment fails closed. `OPENAI_MODEL=gpt-6-astra` preserves the requested future configuration; no AI API call or claim of model availability is made in this release.

## Run locally

1. Copy `.env.example` to `.env` and configure your Firebase project credentials.
2. Enable Email/Password sign-in in that Firebase project. The frontend uses its public web API key.
3. Run `docker compose up --build -d`.
4. Run `docker compose exec api .venv/bin/python -m app.seed`.
5. Open `http://localhost:8000/docs` and `http://localhost:8000/api/v1/health`.

The example database password is for local development only. Docker commands were not executed in the build workspace because Docker is unavailable there.

Without Docker, install Python 3.12 and uv, run `uv sync --locked`, provide a PostgreSQL `DATABASE_URL`, then:

```bash
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload --port 8000
```

## Connect the frontend

Set the frontend's `SKILLSPROUT_API_URL` to the API origin, without `/api/v1`, and `FIREBASE_WEB_API_KEY` to the Firebase project's public Web API Key. Set backend `FRONTEND_URL` to the exact frontend origin. A comma-separated list is supported for multiple approved origins. Do not add `*`.

Use the same Firebase project on both sides. Supply backend service credentials through environment secrets or Application Default Credentials, never Git. `FIREBASE_PRIVATE_KEY` accepts escaped newlines.

The frontend retains Firebase tokens only in memory and refreshes them during the current visit. Reloading signs the parent out. Persistent sign-in is a future enhancement.

## Administrator setup

Sign in to the frontend once, then run in a trusted backend operator shell:

```bash
uv run python -m app.admin YOUR_FIREBASE_UID
```

The existing account must be active. There is no public role-assignment endpoint, default administrator password, or development authentication bypass. Sign in again and open `/admin` on the frontend. The seed catalog author is an inactive system account and cannot sign in.

## Railway deployment

Create a service from this repository and attach PostgreSQL. Set `DATABASE_URL`, `APP_ENV=production`, `FRONTEND_URL`, and the Firebase variables as secrets. The repository includes a Dockerfile and a pre-deploy Alembic migration command. Run the seed once after deployment. Do not run schema upgrades concurrently from every API worker. Enable database backups at the hosting provider.

Production activation also requires the operator's real Firebase project, a running PostgreSQL host, domain/DNS setup and appropriate parent-facing policies. The delivered preview has none of those secrets embedded.

## Tests

```bash
uv run pytest -q
uv run ruff check app tests
```

Local API integration tests use isolated SQLite with foreign keys enabled and **test-only dependency overrides** for Firebase identities. They cover cross-parent access, administrator restrictions, disabled users, published-only lessons, duplicate enrollments, cross-course progress, idempotent completion, progress validation, paid-course rejection and profile limits. They do not call real Firebase. GitHub CI runs the same tests and migrations on PostgreSQL 16. Use a disposable database for `TEST_DATABASE_URL`: the fixture drops its tables.

Local migration checks apply the full migration and seed twice, and compile the migration to PostgreSQL SQL. Live PostgreSQL and Firebase validation remain deployment gates.

## Layout

`app/routes.py` handles HTTP; `app/services.py` enforces business rules; `app/repositories.py` contains shared queries/serializers; `app/models.py` defines tables; `app/schemas.py` validates input; `app/security.py` verifies identity and roles. This keeps the small first release easy to navigate without empty abstraction folders.

See `/docs` for the generated API reference. All routes use `/api/v1`.
