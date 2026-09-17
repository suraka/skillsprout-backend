# SkillSprout V0.1 — Database Schema and FastAPI Backend Design

**Domain:** skillsprout.academy  
**Backend runtime:** Python 3.12  
**API framework:** FastAPI  
**Database:** PostgreSQL  
**ORM:** SQLAlchemy 2.x (async)  
**Migrations:** Alembic  
**Authentication:** Firebase Authentication, verified by FastAPI  
**Payments:** Stripe  
**AI layer:** OpenAI API, model configured through environment variables  
**Deployment target:** Railway initially  
**Frontend:** Next.js / TypeScript on Firebase Hosting or App Hosting

---

## 1. Goal of V0.1

The first working SkillSprout release should support this journey:

1. A parent creates an account.
2. The parent creates one or more child profiles.
3. The parent browses courses.
4. The parent enrolls a child in a course.
5. The child opens lessons.
6. Lesson completion is recorded.
7. The parent can see the child's progress.
8. An administrator can create and publish courses and lessons.

Do not build every future feature at once. Payments, quizzes, certificates, AI tutors, AI course-generation agents, schools, and teacher accounts can be added in later milestones without redesigning the core database.

---

# 2. High-Level Architecture

```text
skillsprout.academy
        |
        v
Next.js / TypeScript
Firebase Hosting
        |
        +--------------------------+
        |                          |
        v                          v
Firebase Authentication       FastAPI
                              Python 3.12
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
               PostgreSQL                 External APIs
                                           |       |
                                           v       v
                                        Stripe   OpenAI
```

### Authentication flow

```text
User signs in with Firebase
        |
        v
Frontend receives Firebase ID token
        |
        v
Frontend sends:
Authorization: Bearer <firebase-id-token>
        |
        v
FastAPI verifies token using Firebase Admin SDK
        |
        v
FastAPI loads the matching SkillSprout user
        |
        v
Request continues
```

The backend, not the browser, decides whether the user is a parent, student, or administrator.

---

# 3. Database Design Principles

Use:

- UUID primary keys.
- `created_at` and `updated_at` timestamps on important tables.
- Foreign keys for relationships.
- Unique constraints to prevent duplicate records.
- PostgreSQL indexes on frequently searched columns.
- `JSONB` only when the data is genuinely flexible.
- Normal relational columns for important business data.
- Soft deletion only where it has a clear business purpose.

For children's privacy, avoid collecting unnecessary personal data. Prefer age bands or birth year over full birth dates unless a real business/legal need requires a complete date of birth.

---

# 4. Core Database Schema

## 4.1 `users`

Represents every authenticated SkillSprout account.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| firebase_uid | VARCHAR(128) | Unique, not null |
| email | CITEXT | Unique, nullable for future child-only accounts |
| display_name | VARCHAR(150) | Nullable |
| role | VARCHAR(30) | `parent`, `student`, `admin` |
| is_active | BOOLEAN | Default true |
| created_at | TIMESTAMPTZ | Not null |
| updated_at | TIMESTAMPTZ | Not null |

Indexes:

- unique index on `firebase_uid`
- unique index on `email`
- index on `role`

For V0.1, children do not need their own Firebase login. Their parent owns the authenticated account.

---

## 4.2 `parent_profiles`

Additional information specifically for parent/guardian accounts.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | FK -> users.id, unique |
| phone | VARCHAR(40) | Nullable |
| country_code | VARCHAR(2) | Nullable |
| timezone | VARCHAR(60) | Nullable |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

---

## 4.3 `student_profiles`

Represents a learner/child.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| first_name | VARCHAR(100) | Not null |
| preferred_name | VARCHAR(100) | Nullable |
| birth_year | SMALLINT | Nullable |
| age_band | VARCHAR(30) | Example: `5-7`, `8-10`, `11-13`, `14-17`, `adult` |
| avatar_key | VARCHAR(100) | Nullable |
| status | VARCHAR(30) | Default `active` |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

Do not expose internal IDs unnecessarily in the UI.

---

## 4.4 `parent_student_links`

Connects parents/guardians to children.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| parent_user_id | UUID | FK -> users.id |
| student_id | UUID | FK -> student_profiles.id |
| relationship | VARCHAR(30) | `parent`, `guardian` |
| is_primary | BOOLEAN | Default false |
| created_at | TIMESTAMPTZ | |

Constraint:

```text
UNIQUE(parent_user_id, student_id)
```

This design allows a child to have more than one authorized guardian later.

---

## 4.5 `courses`

The main course record.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| slug | VARCHAR(160) | Unique |
| title | VARCHAR(200) | Not null |
| short_description | VARCHAR(500) | |
| description | TEXT | |
| age_band | VARCHAR(30) | |
| difficulty | VARCHAR(30) | `beginner`, `intermediate`, `advanced` |
| category | VARCHAR(80) | Example: AI, coding, digital art |
| thumbnail_url | TEXT | Nullable |
| status | VARCHAR(30) | `draft`, `review`, `published`, `archived` |
| is_free | BOOLEAN | Default false |
| created_by | UUID | FK -> users.id |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |
| published_at | TIMESTAMPTZ | Nullable |

Indexes:

- unique `slug`
- `(status, age_band)`
- `category`

---

## 4.6 `course_modules`

Groups lessons into sections.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| course_id | UUID | FK -> courses.id |
| title | VARCHAR(200) | |
| description | TEXT | Nullable |
| position | INTEGER | Not null |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

Constraint:

```text
UNIQUE(course_id, position)
```

---

## 4.7 `lessons`

Individual learning units.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| module_id | UUID | FK -> course_modules.id |
| title | VARCHAR(200) | |
| slug | VARCHAR(160) | |
| lesson_type | VARCHAR(30) | `video`, `text`, `activity`, `project` |
| content | JSONB | Structured lesson content |
| estimated_minutes | INTEGER | Nullable |
| position | INTEGER | |
| status | VARCHAR(30) | `draft`, `review`, `published` |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

Constraints:

```text
UNIQUE(module_id, position)
UNIQUE(module_id, slug)
```

Example `content`:

```json
{
  "blocks": [
    {
      "type": "heading",
      "text": "What is Artificial Intelligence?"
    },
    {
      "type": "paragraph",
      "text": "AI helps computers perform tasks that normally require human intelligence."
    }
  ]
}
```

---

## 4.8 `enrollments`

Links a student to a course.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| student_id | UUID | FK -> student_profiles.id |
| course_id | UUID | FK -> courses.id |
| enrolled_by | UUID | FK -> users.id |
| status | VARCHAR(30) | `active`, `completed`, `cancelled` |
| enrolled_at | TIMESTAMPTZ | |
| completed_at | TIMESTAMPTZ | Nullable |

Constraint:

```text
UNIQUE(student_id, course_id)
```

Indexes:

- `student_id`
- `course_id`
- `(student_id, status)`

---

## 4.9 `lesson_progress`

Stores a student's progress through lessons.

| Column | Type | Rules |
|---|---|---|
| id | UUID | Primary key |
| enrollment_id | UUID | FK -> enrollments.id |
| lesson_id | UUID | FK -> lessons.id |
| status | VARCHAR(30) | `not_started`, `in_progress`, `completed` |
| progress_percent | SMALLINT | 0-100 |
| started_at | TIMESTAMPTZ | Nullable |
| completed_at | TIMESTAMPTZ | Nullable |
| last_seen_at | TIMESTAMPTZ | Nullable |
| updated_at | TIMESTAMPTZ | |

Constraint:

```text
UNIQUE(enrollment_id, lesson_id)
CHECK(progress_percent BETWEEN 0 AND 100)
```

---

# 5. V0.2+ Tables Reserved for Later

These do not have to be implemented in the first milestone, but the architecture should make room for them.

## Payments

### `plans`
- id
- code
- name
- billing_interval
- price_amount
- currency
- stripe_price_id
- active

### `subscriptions`
- id
- parent_user_id
- plan_id
- stripe_customer_id
- stripe_subscription_id
- status
- current_period_start
- current_period_end
- cancel_at_period_end

### `payment_events`
Stores processed Stripe webhook event IDs so the same webhook cannot be handled twice.

---

## Quizzes

### `quizzes`
- id
- lesson_id
- title
- passing_score

### `quiz_questions`
- id
- quiz_id
- question_type
- prompt
- options JSONB
- answer_data JSONB
- position

### `quiz_attempts`
- id
- quiz_id
- student_id
- score
- started_at
- submitted_at

### `quiz_answers`
- id
- attempt_id
- question_id
- response JSONB
- is_correct

---

## AI

### `ai_sessions`
- id
- student_id
- course_id
- lesson_id
- session_type
- created_at

### `ai_messages`
- id
- session_id
- actor (`student`, `assistant`, `system`)
- content
- model_name
- moderation_status
- created_at

For children's AI interactions, add safety review, age-appropriate system instructions, rate limits, and parent/admin controls.

---

## Administration

### `audit_logs`
- id
- actor_user_id
- action
- entity_type
- entity_id
- metadata JSONB
- created_at

This is useful for important admin, payment, and content changes.

---

# 6. Entity Relationship Overview

```text
users
  |
  +---- parent_profiles
  |
  +---- parent_student_links ---- student_profiles
                                      |
                                      +---- enrollments ---- courses
                                             |                 |
                                             |                 +---- course_modules
                                             |                         |
                                             |                         +---- lessons
                                             |
                                             +---- lesson_progress
```

Future:

```text
users(parent)
   |
   +---- subscriptions ---- plans
   |
   +---- payment_events

student_profiles
   |
   +---- quiz_attempts
   |
   +---- ai_sessions ---- ai_messages
```

---

# 7. Recommended FastAPI Project Structure

```text
backend/
|
+-- app/
|   |
|   +-- main.py
|   |
|   +-- core/
|   |   +-- config.py
|   |   +-- security.py
|   |   +-- logging.py
|   |   +-- exceptions.py
|   |
|   +-- db/
|   |   +-- base.py
|   |   +-- session.py
|   |
|   +-- models/
|   |   +-- user.py
|   |   +-- parent.py
|   |   +-- student.py
|   |   +-- course.py
|   |   +-- enrollment.py
|   |   +-- progress.py
|   |
|   +-- schemas/
|   |   +-- user.py
|   |   +-- student.py
|   |   +-- course.py
|   |   +-- enrollment.py
|   |   +-- progress.py
|   |
|   +-- repositories/
|   |   +-- users.py
|   |   +-- students.py
|   |   +-- courses.py
|   |   +-- enrollments.py
|   |   +-- progress.py
|   |
|   +-- services/
|   |   +-- users.py
|   |   +-- students.py
|   |   +-- courses.py
|   |   +-- enrollments.py
|   |   +-- progress.py
|   |
|   +-- api/
|   |   +-- deps.py
|   |   +-- v1/
|   |       +-- router.py
|   |       +-- routes/
|   |           +-- health.py
|   |           +-- me.py
|   |           +-- students.py
|   |           +-- courses.py
|   |           +-- enrollments.py
|   |           +-- progress.py
|   |           +-- admin_courses.py
|   |
|   +-- integrations/
|   |   +-- firebase/
|   |   |   +-- auth.py
|   |   +-- stripe/
|   |   |   +-- client.py
|   |   |   +-- webhooks.py
|   |   +-- openai/
|   |       +-- client.py
|   |       +-- tutor.py
|   |       +-- safety.py
|   |
|   +-- middleware/
|       +-- request_id.py
|       +-- error_handler.py
|
+-- alembic/
+-- tests/
|   +-- api/
|   +-- services/
|   +-- repositories/
|
+-- alembic.ini
+-- pyproject.toml
+-- Dockerfile
+-- .env.example
+-- README.md
```

---

# 8. Why Repositories and Services Are Separate

Keep responsibilities simple.

### Route

Receives HTTP request and returns HTTP response.

```text
POST /students
```

### Service

Contains business rules.

Example:

- verify the current user is a parent
- check student limit
- create child
- write audit event

### Repository

Deals with PostgreSQL.

Example:

```text
INSERT student
SELECT student
UPDATE progress
```

This makes the system easier to test and maintain.

---

# 9. Core API Endpoints

All API routes should start with:

```text
/api/v1
```

## Health

```http
GET /api/v1/health
```

Response:

```json
{
  "status": "ok"
}
```

---

## Current user

```http
GET /api/v1/me
```

Returns the authenticated SkillSprout user.

---

## Parent / student profiles

```http
GET    /api/v1/students
POST   /api/v1/students
GET    /api/v1/students/{student_id}
PATCH  /api/v1/students/{student_id}
```

Only an authorized parent/guardian can access a child's profile.

---

## Courses

Public:

```http
GET /api/v1/courses
GET /api/v1/courses/{slug}
```

Authenticated:

```http
GET /api/v1/courses/{course_id}/modules
GET /api/v1/lessons/{lesson_id}
```

Admin:

```http
POST   /api/v1/admin/courses
PATCH  /api/v1/admin/courses/{course_id}
POST   /api/v1/admin/courses/{course_id}/modules
POST   /api/v1/admin/modules/{module_id}/lessons
POST   /api/v1/admin/courses/{course_id}/publish
```

---

## Enrollments

```http
POST /api/v1/students/{student_id}/enrollments
GET  /api/v1/students/{student_id}/enrollments
GET  /api/v1/enrollments/{enrollment_id}
```

Example request:

```json
{
  "course_id": "6f92a5c0-..."
}
```

---

## Progress

```http
GET /api/v1/enrollments/{enrollment_id}/progress

PUT /api/v1/enrollments/{enrollment_id}/lessons/{lesson_id}/progress
```

Example:

```json
{
  "status": "completed",
  "progress_percent": 100
}
```

---

# 10. Authorization Rules

Do not rely only on frontend controls.

FastAPI must enforce every permission.

### Parent

Can:

- manage own account
- create linked child profiles
- view linked children
- enroll linked children
- view linked children's progress

Cannot:

- access another parent's child
- create/publish courses
- see internal admin data

### Student

Future child login can:

- view assigned courses
- open lessons
- update own progress
- use approved AI tutor

### Admin

Can:

- manage courses
- manage lessons
- publish/unpublish content
- view platform administration data

---

# 11. Python 3.12 Dependencies

Recommended `pyproject.toml` runtime dependencies:

```toml
[project]
requires-python = ">=3.12,<3.13"

dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "sqlalchemy[asyncio]",
    "asyncpg",
    "alembic",
    "pydantic-settings",
    "firebase-admin",
    "stripe",
    "openai",
    "httpx"
]
```

Development dependencies:

```toml
[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "httpx",
    "ruff",
    "mypy"
]
```

Pin exact versions in the real repository after compatibility testing.

---

# 12. Configuration

`.env.example`

```env
APP_ENV=development
APP_NAME=SkillSprout API
API_V1_PREFIX=/api/v1

DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/skillsprout

FIREBASE_PROJECT_ID=
FIREBASE_CLIENT_EMAIL=
FIREBASE_PRIVATE_KEY=

STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

OPENAI_API_KEY=
OPENAI_MODEL=gpt-6-astra

FRONTEND_URL=http://localhost:3000
```

Never commit real secrets into GitHub.

---

# 13. Async PostgreSQL Session

Example:

```python
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

---

# 14. Example SQLAlchemy Model

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    firebase_uid: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )

    email: Mapped[str | None] = mapped_column(
        String(320),
        unique=True,
        nullable=True,
        index=True,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="parent",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
```

---

# 15. Firebase Authentication Dependency

Conceptual flow:

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

security = HTTPBearer()


async def get_firebase_identity(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    try:
        return auth.verify_id_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
        )
```

The real implementation should also:

1. Extract the Firebase UID.
2. Look up the SkillSprout user.
3. Create the database user on first login if appropriate.
4. Reject disabled users.
5. Return a typed current-user object.

---

# 16. FastAPI Entry Point

```python
from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(
    title="SkillSprout API",
    version="0.1.0",
)

app.include_router(
    api_router,
    prefix=settings.api_v1_prefix,
)


@app.get("/")
async def root():
    return {
        "name": "SkillSprout API",
        "version": "0.1.0",
    }
```

---

# 17. Dockerfile

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY . .

RUN pip install --upgrade pip \
    && pip install .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

For Railway, use the platform's `PORT` variable in the production command if required.

---

# 18. Local Development

Recommended local stack:

```text
Next.js             localhost:3000
FastAPI             localhost:8000
PostgreSQL          localhost:5432
```

Use Docker Compose for PostgreSQL during development.

Example:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: skillsprout
      POSTGRES_USER: skillsprout
      POSTGRES_PASSWORD: development_only
    ports:
      - "5432:5432"
    volumes:
      - skillsprout_pg:/var/lib/postgresql/data

volumes:
  skillsprout_pg:
```

---

# 19. Migrations

Never manually create production tables.

Use Alembic:

```bash
alembic revision --autogenerate -m "create core tables"
alembic upgrade head
```

Suggested first migrations:

1. users
2. parent_profiles
3. student_profiles
4. parent_student_links
5. courses
6. course_modules
7. lessons
8. enrollments
9. lesson_progress

---

# 20. Testing Strategy

Minimum backend tests:

### Authentication
- missing token -> 401
- invalid token -> 401
- valid parent -> succeeds

### Students
- parent can create child
- parent can read own linked child
- parent cannot read unrelated child

### Courses
- visitor sees published courses
- visitor cannot see drafts
- admin can create course
- parent cannot publish course

### Enrollment
- linked parent can enroll child
- unrelated parent cannot enroll child
- duplicate enrollment rejected

### Progress
- progress limited to enrolled course
- percent cannot exceed 100
- lesson must belong to enrolled course

---

# 21. Security Baseline

Implement from the beginning:

- HTTPS only in production.
- Secrets only in environment variables/secret manager.
- Verify Firebase tokens server-side.
- Validate ownership of every student resource.
- Rate-limit sensitive and AI endpoints.
- Use CORS only for approved frontend domains.
- Never trust role values sent by the browser.
- Stripe webhooks must verify Stripe signatures.
- Store processed Stripe event IDs for idempotency.
- Log admin and payment-sensitive changes.
- Do not log passwords, tokens, API keys, or child conversation content unnecessarily.
- Minimize children's personal data.
- Back up PostgreSQL before public launch.

---

# 22. V0.1 Build Order

## Phase 1 — Repository foundation
- Create GitHub repository.
- Add backend folder.
- Configure Python 3.12.
- Install FastAPI and PostgreSQL dependencies.
- Add linting and tests.

## Phase 2 — Database
- Start local PostgreSQL.
- Create SQLAlchemy models.
- Configure Alembic.
- Run first migration.

## Phase 3 — Authentication
- Configure Firebase project.
- Verify Firebase ID tokens in FastAPI.
- Add `/me`.

## Phase 4 — Parent and child profiles
- Parent creates student.
- Parent lists linked students.
- Add ownership tests.

## Phase 5 — Course catalog
- Admin creates courses/modules/lessons.
- Public can browse published courses.

## Phase 6 — Enrollment and progress
- Parent enrolls student.
- Student progress is stored.
- Parent progress dashboard API works.

## Phase 7 — Deployment
- Create Railway PostgreSQL.
- Deploy FastAPI.
- Add production environment variables.
- Run Alembic migrations.
- Test API.

Only after this core flow works should Stripe subscriptions and AI tutoring be added.

---

# 23. Recommended V0.1 Acceptance Test

V0.1 is successful when this exact story works:

```text
1. Parent signs in.
2. FastAPI recognizes the Firebase identity.
3. Parent creates "Ama" as a learner.
4. Parent sees published "AI Explorer" course.
5. Parent enrolls Ama.
6. Ama opens Lesson 1.
7. Lesson progress becomes 100%.
8. Parent refreshes dashboard.
9. Dashboard displays the updated course progress.
```

If these nine steps work reliably, the core SkillSprout learning platform exists.

---

# 24. Next Milestones

```text
V0.1
Core accounts + children + courses + lessons + enrollment + progress

V0.2
Stripe subscriptions + plans + billing portal + webhooks

V0.3
Quizzes + projects + achievements + certificates

V0.4
Age-aware AI tutor + parent AI controls

V0.5
AI course research + curriculum + content-generation pipeline

V0.6
Marketing/pricing agents + analytics

V1.0
Production launch at skillsprout.academy
```

---

# 25. Initial Engineering Decision Summary

Use these defaults unless testing reveals a reason to change:

```text
Language:            Python 3.12
API:                 FastAPI
Database:            PostgreSQL
ORM:                 SQLAlchemy 2.x async
Driver:              asyncpg
Migrations:          Alembic
Auth:                Firebase Authentication
Payments:            Stripe
AI:                  OpenAI API through a dedicated integration layer
Frontend:            Next.js + TypeScript
Backend hosting:     Railway
Frontend hosting:    Firebase
Domain registrar:    Squarespace
Domain:               skillsprout.academy
```

The architecture deliberately keeps authentication, payments, AI, database access, and business logic separate so any one provider can be replaced later without rewriting the entire platform.
