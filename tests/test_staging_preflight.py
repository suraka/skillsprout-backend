import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


import pytest

from app.staging_target import StagingValidationError
from scripts import staging_preflight as preflight


@pytest.mark.asyncio
async def test_preflight_summary_includes_single_migration_revision(monkeypatch):
    class Result:
        def __init__(self, rows):
            self.rows = rows

        def one(self):
            return self.rows[0]

        def all(self):
            return self.rows

    class Connection:
        async def execute(self, statement):
            if "current_database" in str(statement):
                return Result([("skillsprout_staging",)])
            return Result([("revision-123",)])

    class ConnectionContext:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    class Engine:
        def connect(self):
            return ConnectionContext()

        async def dispose(self):
            return None

    monkeypatch.setattr(preflight, "create_async_engine", lambda url: Engine())
    summary = await preflight.inspect_database(
        SimpleNamespace(database_url="safe"), {"database_name": "skillsprout_staging"}
    )
    assert summary["migration_revision"] == "revision-123"


def test_main_redacts_arbitrary_value_error(monkeypatch, capsys):
    def raise_value_error(coroutine):
        coroutine.close()
        raise ValueError("postgresql://user:database-password@production.example/private")

    monkeypatch.setattr(preflight.asyncio, "run", raise_value_error)

    assert preflight.main() == 1
    output = capsys.readouterr().out
    assert "Database preflight failed" in output
    assert "database-password" not in output


def test_main_prints_safe_validation_error(monkeypatch, capsys):
    def raise_safe_error(coroutine):
        coroutine.close()
        raise StagingValidationError("Expected exactly one Alembic migration revision")

    monkeypatch.setattr(preflight.asyncio, "run", raise_safe_error)

    assert preflight.main() == 1
    assert "Expected exactly one Alembic migration revision" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_routing_override_fails_before_engine_creation(monkeypatch):
    fake_config = ModuleType("app.config")
    fake_config.Settings = lambda: SimpleNamespace(
        app_env="staging",
        database_url="postgresql+asyncpg://user:secret@staging-db.internal/skillsprout_staging?host=production.internal",
        frontend_url="https://staging.skillsprout.example",
        firebase_project_id="skillsprout-staging",
    )
    monkeypatch.setitem(sys.modules, "app.config", fake_config)
    monkeypatch.setattr(
        preflight, "create_async_engine", lambda url: pytest.fail("engine must not be created")
    )
    env = {
        "STAGING_EXPECTED_DB_HOST": "staging-db.internal",
        "STAGING_EXPECTED_DB_NAME": "skillsprout_staging",
        "STAGING_EXPECTED_FRONTEND_URL": "https://staging.skillsprout.example",
        "STAGING_EXPECTED_FIREBASE_PROJECT_ID": "skillsprout-staging",
    }
    with pytest.raises(StagingValidationError, match="supported staging PostgreSQL URL"):
        await preflight.run(env)


def test_module_cli_redacts_config_validation_failure():
    secret = "sensitive-staging-config-marker"
    env = dict(os.environ)
    env.update(
        APP_ENV="staging",
        MAX_STUDENTS_PER_PARENT=secret,
        STAGING_EXPECTED_DB_HOST="staging-db.internal",
        STAGING_EXPECTED_DB_NAME="skillsprout_staging",
        STAGING_EXPECTED_FRONTEND_URL="https://staging.skillsprout.example",
        STAGING_EXPECTED_FIREBASE_PROJECT_ID="skillsprout-staging",
    )
    result = subprocess.run(
        [sys.executable, "-m", "scripts.staging_preflight"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "status": "failed", "error": "Database preflight failed"
    }
    assert secret not in result.stdout + result.stderr
