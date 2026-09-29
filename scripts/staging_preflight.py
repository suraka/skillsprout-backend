"""Read-only staging database identity and Alembic revision preflight."""

import asyncio
import json
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.staging_target import ExpectedStagingTarget, validate_staging_target


EXPECTED_ENV = {
    "database_host": "STAGING_EXPECTED_DB_HOST",
    "database_name": "STAGING_EXPECTED_DB_NAME",
    "frontend_url": "STAGING_EXPECTED_FRONTEND_URL",
    "firebase_project_id": "STAGING_EXPECTED_FIREBASE_PROJECT_ID",
}


def expected_target_from_env(env: dict[str, str]) -> ExpectedStagingTarget:
    missing = [variable for variable in EXPECTED_ENV.values() if not env.get(variable, "").strip()]
    if missing:
        raise ValueError("Missing required target identifiers: " + ", ".join(missing))
    values = {field: env[variable].strip() for field, variable in EXPECTED_ENV.items()}
    return ExpectedStagingTarget(**values)


async def inspect_database(settings: Settings, target: dict[str, str]) -> dict[str, object]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            database_row = (await connection.execute(text("SELECT current_database()"))).one()
            revisions = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).all()
    finally:
        await engine.dispose()

    if len(revisions) != 1:
        raise ValueError("Expected exactly one Alembic migration revision")
    current_database = str(database_row[0])
    if current_database != target["database_name"]:
        raise ValueError("Connected database name does not match the expected staging target")
    return {
        "status": "ok",
        "target": target,
        "current_database": current_database,
        "migration_revision_count": 1,
    }


async def run(env: dict[str, str]) -> dict[str, object]:
    expected = expected_target_from_env(env)
    settings = Settings()
    target = validate_staging_target(settings, expected)
    return await inspect_database(settings, target)


def main() -> int:
    try:
        summary = asyncio.run(run(dict(os.environ)))
    except Exception as exc:
        # Driver errors may include the full connection URL; expose only local validation errors.
        safe_error = str(exc) if isinstance(exc, ValueError) else "Database preflight failed"
        print(json.dumps({"status": "failed", "error": safe_error}, sort_keys=True))
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
