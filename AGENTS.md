# SkillSprout backend agent instructions

These instructions apply to this backend repository. The owner-provided SkillSprout v2.3 specification is the product authority. Record a concrete conflict with repository documents or a task request and ask the owner to resolve it before implementing the disputed product decision.

Follow the shared [agent operating model](https://github.com/suraka/skillsprout/blob/main/docs/development/agent-operating-model.md) and [release gates](https://github.com/suraka/skillsprout/blob/main/docs/development/release-gates.md). These canonical `main` links remain unavailable until the documents reach frontend `main` through PR #1 and its stacked documentation PR #2, or equivalent integration. PR #2 targets PR #1's branch, so merging PR #2 into that branch alone does not make the links available on `main`. Until then, the files are on `suraka/skillsprout` branch `codex/agent-control-frontend`; keep this backend PR draft. Do not treat their presence on that branch as a merged policy or an approved release.

## Backend boundaries

- Use Python `>=3.12,<3.13` as required by `pyproject.toml`. Work on an isolated feature branch and open a draft PR against `main`; record the exact backend and frontend SHAs for a cross-repository contract.
- Verify Firebase ID tokens server-side, including revocation where applicable. Never trust a client-supplied identity, role, learner ownership, or completion claim as authorization. Enforce active-account and administrator checks on protected actions; there is no development authentication bypass. Keep Firebase service credentials and other secrets out of Git, prompts, fixtures, logs, and reports.
- Enforce guardian/parent ownership on every learner, enrollment, lesson-progress, and other family-scoped resource query or mutation. Deny cross-family access even when a caller knows an object ID. Preserve the distinction between client-claimed completion and verified mastery.
- Preserve existing learner rows, identifiers, migration history, and evidence provenance. Make schema changes additive and backward-compatible where possible; review current and candidate Alembic revisions, data transformations, rollback impact, and recovery before a release decision. Use disposable databases for destructive test fixtures, never a production database.
- Use synthetic learner and family data in tests, fixtures, staging, screenshots, and reports. Real child or learner data must not enter development artifacts.

## Checks and evidence

The current README and `.github/workflows/ci.yml` use `uv sync --locked`, `uv run pytest -q`, and `uv run ruff check app tests`. CI also uses a PostgreSQL 16 service and runs `uv run alembic upgrade head`, `uv run python -m app.seed` twice, and `uv run alembic check`. Run relevant checks on the exact proposed SHA and report their commands, environment, results, and limitations. Test-only Firebase identity overrides and SQLite tests do not verify real Firebase sign-in or integrated staging authorization.

Report status truthfully: distinguish BUILT, VERIFIED with precise scope, PARTIAL, NOT TESTED, BLOCKED, and NOT VERIFIED. Do not claim staging, real sign-in, production deployment, backups, restore, or live migration validation without direct evidence. Keep failed and blocked gates visible.

Production environment changes, production database migrations, merges, and deployments each require a separately approved action by the owner or designated authorized maintainer after the relevant evidence is reviewed. A draft PR, CI pass, staging decision, or agent role never grants standing production access or release authorization. Do not mark a draft PR ready, merge, deploy, change live configuration, or run a production migration on the strength of these instructions.
