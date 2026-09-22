# SkillSprout backend agreement

Use Python 3.12/FastAPI/PostgreSQL and preserve data, IDs and migration history.
Authoritative v2.3 specification/checklist live in suraka/skillsprout/docs; see IMPLEMENTATION_HANDOFF.md.
Build saved-data features with frontend, API, additive migration, authoritative authorization and tests together.
Guest demo features intentionally make no backend/auth/persistence calls.
Existing completion is self-reported: preserve it, never fabricate verified evidence.
Test fixtures DROP ALL TABLES in TEST_DATABASE_URL. Only use a disposable isolated test database.
No production resets, child records or credentials in source/logs. Record actual test and deployment evidence.
