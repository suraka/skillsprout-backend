import pytest

from app.config import Settings
from app.staging_target import ExpectedStagingTarget, validate_staging_target


def target() -> ExpectedStagingTarget:
    return ExpectedStagingTarget(
        database_host="staging-db.internal",
        database_name="skillsprout_staging",
        frontend_url="https://staging.skillsprout.example",
        firebase_project_id="skillsprout-staging",
    )


def settings(**overrides: str) -> Settings:
    values = {
        "app_env": "staging",
        "database_url": "postgresql+asyncpg://dbuser:secret-password@staging-db.internal:5432/skillsprout_staging?sslmode=require",
        "frontend_url": "https://staging.skillsprout.example",
        "firebase_project_id": "skillsprout-staging",
    }
    values.update(overrides)
    return Settings(**values)


def test_rejects_non_staging_app_env():
    try:
        validate_staging_target(settings(app_env="production"), target())
    except ValueError as exc:
        assert "APP_ENV must be staging" in str(exc)
    else:
        raise AssertionError("non-staging APP_ENV should be rejected")


def test_rejects_database_host_or_name_mismatch():
    for database_url in (
        "postgresql+asyncpg://dbuser:secret-password@unexpected.internal/db",
        "postgresql+asyncpg://dbuser:secret-password@staging-db.internal/other",
    ):
        try:
            validate_staging_target(settings(database_url=database_url), target())
        except ValueError as exc:
            assert "Staging target mismatch" in str(exc)
            assert "secret-password" not in str(exc)
        else:
            raise AssertionError("database identity mismatch should be rejected")


def test_requires_all_expected_target_values():
    incomplete = ExpectedStagingTarget(
        database_host="staging-db.internal",
        database_name="skillsprout_staging",
        frontend_url="https://staging.skillsprout.example",
        firebase_project_id="",
    )
    try:
        validate_staging_target(settings(), incomplete)
    except ValueError as exc:
        assert "firebase_project_id" in str(exc)
    else:
        raise AssertionError("missing expected project ID should be rejected")


def test_safe_summary_excludes_database_password():
    summary = validate_staging_target(settings(), target())
    serialized = repr(summary)
    assert "secret-password" not in serialized
    assert "sslmode" not in serialized
    assert "database_url" not in summary
    assert summary["database_host"] == "staging-db.internal"
    assert summary["database_name"] == "skillsprout_staging"


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://dbuser:secret-password@staging-db.internal/skillsprout_staging?host=production.internal",
        "postgresql+asyncpg://dbuser:secret-password@staging-db.internal/skillsprout_staging?%68ost=production.internal",
        "postgresql+asyncpg://dbuser:secret-password@staging-db.internal/skillsprout_staging?sslmode=require&host=production.internal",
        "postgresql+asyncpg://dbuser:secret-password@staging-db.internal/skillsprout_staging?host=staging-db.internal&host=production.internal",
        "postgresql+asyncpg://dbuser:secret-password@staging-db.internal/skillsprout_staging?database=production",
        "postgresql+asyncpg://dbuser:secret-password@staging-db.internal/skillsprout_staging?port=5433",
        "postgresql+asyncpg://dbuser:secret-password@staging-db.internal/skillsprout_staging?dsn=production",
        "postgresql+asyncpg://dbuser:secret-password@staging-db.internal/skillsprout_staging",
        "mysql+asyncmy://dbuser:secret-password@staging-db.internal/skillsprout_staging",
    ],
)
def test_rejects_routing_overrides_and_unsupported_urls(database_url):
    with pytest.raises(ValueError, match="supported staging PostgreSQL URL") as error:
        validate_staging_target(settings(database_url=database_url), target())
    assert "secret-password" not in str(error.value)
    assert "production.internal" not in str(error.value)
