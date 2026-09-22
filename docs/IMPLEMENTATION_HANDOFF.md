# v2.3 backend audit and guest-demo handoff — 2026-09-22

Canonical master instruction, requirement matrix and checklist: [suraka/skillsprout PR 1](https://github.com/suraka/skillsprout/pull/1), branch `codex/sorting-garden-foundation`, `docs/MASTER_BLUEPRINT.md`, `docs/ROADMAP_AND_FEATURE_STATUS.md` and `docs/TEST_PLAN_AND_RESULTS.md`.
First restored frontend checkpoint: `f0ed7af6f03b9de2ff3879a7a4ab662181c683d4`; fetch the latest PR head for subsequent test/evidence commits. Backend audited at `1c6e8339ba9973c1da3b559ef5bd66cb4e892159`.

This backend branch adds documentation only. Phase 1 Sorting Garden is intentionally browser-local guest play per §§10/12/15. No database/auth/backend component is required or appropriate; no private learner row, enrollment, score or remote AI request is created. No application code, migration, environment or production data changed.

Verified again after workspace recovery: Python 3.12.14; `uv sync --frozen --group dev`; `uv run pytest -q`: 4 passed with SQLite and mocked Firebase; `uv run ruff check app tests`: passed. Existing [PostgreSQL CI 35455581581](https://github.com/suraka/skillsprout-backend/actions/runs/35455581581) passed at baseline. Live read-only health/readiness/catalog previously verified 200, six courses / 18 lessons. No real Firebase journey, production migration revision or backup restore verified.

Before saved-family milestones:
1. Preserve client-claimed legacy completion provenance; add actual versioned rubric/evidence checks.
2. Add reviewed server consent, retention/data-rights and child-session boundaries to existing parent relationships.
3. Add immutable course review/runtime/asset gates; current text-only publishing checks are insufficient for v2.3.
4. Deliver private project revisions, save/reopen, optimistic concurrency, authorization and parent Invention Cards as one UI/API/database/test slice.
5. Reuse existing lesson/course IDs for subject curriculum references. No second incompatible progress database.

Never run tests against production: fixtures drop tables. No migrations or seeds executed on production. Initial revision 675e3ce72cc5 is unchanged. Reverting this documentation-only branch requires no data rollback.
