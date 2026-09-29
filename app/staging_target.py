"""Fail-closed validation for an explicitly identified staging backend."""

from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from app.config import Settings


class StagingValidationError(ValueError):
    """A validation failure whose message contains only safe identifiers."""


@dataclass(frozen=True)
class ExpectedStagingTarget:
    database_host: str
    database_name: str
    frontend_url: str
    firebase_project_id: str


def validate_staging_target(
    settings: Settings, expected: ExpectedStagingTarget
) -> dict[str, str]:
    """Return safe target identities after confirming every configured value matches."""
    expected_values = {
        "database_host": expected.database_host,
        "database_name": expected.database_name,
        "frontend_url": expected.frontend_url,
        "firebase_project_id": expected.firebase_project_id,
    }
    missing = [name for name, value in expected_values.items() if not value.strip()]
    if missing:
        raise StagingValidationError(
            "Expected staging target values are required: " + ", ".join(missing)
        )
    if settings.app_env != "staging":
        raise StagingValidationError("APP_ENV must be staging")

    try:
        parsed = urlsplit(settings.database_url)
        database_host = parsed.hostname
        database_name = unquote(parsed.path.lstrip("/"))
    except (TypeError, ValueError):
        database_host = None
        database_name = ""

    configured_values = {
        "database_host": database_host,
        "database_name": database_name,
        "frontend_url": settings.frontend_url,
        "firebase_project_id": settings.firebase_project_id,
    }
    mismatches = [
        name
        for name, expected_value in expected_values.items()
        if configured_values[name] != expected_value
    ]
    if mismatches:
        raise StagingValidationError("Staging target mismatch for: " + ", ".join(mismatches))

    return {
        "app_env": settings.app_env,
        "database_host": str(database_host),
        "database_name": database_name,
        "frontend_url": settings.frontend_url,
        "firebase_project_id": settings.firebase_project_id,
    }
