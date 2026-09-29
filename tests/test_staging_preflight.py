from types import SimpleNamespace

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
