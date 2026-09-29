"""Authentication and family authorization smoke checks for isolated staging."""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx


EXPIRY_BUFFER_SECONDS = 10


class SmokeError(RuntimeError):
    """Safe-to-display staging smoke failure."""


@dataclass(frozen=True)
class SmokeConfig:
    api_origin: str
    firebase_web_api_key: str
    parent_a_email: str
    parent_a_password: str
    parent_b_email: str
    parent_b_password: str
    parent_a_student_id: str


@dataclass(frozen=True)
class FirebaseSession:
    id_token: str
    expires_in_seconds: int


def _validated_https_origin(env: dict[str, str], variable: str) -> str:
    origin = env.get(variable, "").strip()
    if not origin:
        raise SmokeError(f"{variable} is required")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise SmokeError(f"{variable} must be an HTTPS origin without credentials or path")
    return origin


def load_config(env: dict[str, str]) -> SmokeConfig:
    names = (
        "STAGING_API_ORIGIN",
        "STAGING_EXPECTED_API_ORIGIN",
        "STAGING_FIREBASE_WEB_API_KEY",
        "STAGING_PARENT_A_EMAIL",
        "STAGING_PARENT_A_PASSWORD",
        "STAGING_PARENT_B_EMAIL",
        "STAGING_PARENT_B_PASSWORD",
        "STAGING_PARENT_A_STUDENT_ID",
    )
    missing = [name for name in names if not env.get(name, "").strip()]
    if missing:
        raise SmokeError("Missing required staging smoke settings: " + ", ".join(missing))
    origin = _validated_https_origin(env, "STAGING_API_ORIGIN")
    expected_origin = _validated_https_origin(env, "STAGING_EXPECTED_API_ORIGIN")
    if origin != expected_origin:
        raise SmokeError("STAGING_API_ORIGIN must match STAGING_EXPECTED_API_ORIGIN")
    return SmokeConfig(
        api_origin=origin,
        firebase_web_api_key=env["STAGING_FIREBASE_WEB_API_KEY"],
        parent_a_email=env["STAGING_PARENT_A_EMAIL"],
        parent_a_password=env["STAGING_PARENT_A_PASSWORD"],
        parent_b_email=env["STAGING_PARENT_B_EMAIL"],
        parent_b_password=env["STAGING_PARENT_B_PASSWORD"],
        parent_a_student_id=env["STAGING_PARENT_A_STUDENT_ID"],
    )

def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        result = response.json()
    except ValueError:
        return {}
    return result if isinstance(result, dict) else {}


def sign_in(client: httpx.Client, api_key: str, email: str, password: str) -> FirebaseSession:
    url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    try:
        response = client.post(
            url,
            params={"key": api_key},
            json={"email": email, "password": password, "returnSecureToken": True},
        )
    except httpx.HTTPError:
        raise SmokeError("Firebase sign-in request failed") from None
    if response.status_code != 200:
        raise SmokeError(f"Firebase sign-in failed (HTTP {response.status_code})")
    result = _json(response)
    token = result.get("idToken")
    try:
        expires_in_seconds = int(result.get("expiresIn", ""))
    except (TypeError, ValueError):
        expires_in_seconds = 0
    if not isinstance(token, str) or not token or expires_in_seconds <= 0:
        raise SmokeError("Firebase sign-in response did not contain a usable session")
    return FirebaseSession(id_token=token, expires_in_seconds=expires_in_seconds)


def api_request(
    client: httpx.Client,
    origin: str,
    method: str,
    path: str,
    token: str | None = None,
    payload: dict[str, str] | None = None,
) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = client.request(method, origin + path, headers=headers, json=payload)
    except httpx.HTTPError:
        raise SmokeError(f"Staging API request failed for {method} {path}") from None
    return response.status_code


def require_status(label: str, status: int, expected: set[int]) -> None:
    if status not in expected:
        accepted = ", ".join(str(code) for code in sorted(expected))
        raise SmokeError(f"{label}: expected HTTP {accepted}, received HTTP {status}")


def verify_revocation(
    config: SmokeConfig,
    client: httpx.Client,
    input_fn: Callable[[str], str],
) -> None:
    session = sign_in(
        client, config.firebase_web_api_key, config.parent_a_email, config.parent_a_password
    )
    input_fn("Revoke sessions for synthetic guardian A, then press Enter to verify denial: ")
    status = api_request(client, config.api_origin, "GET", "/api/v1/me", session.id_token)
    require_status("revocation_denial", status, {401, 403})


def verify_expiry(
    config: SmokeConfig,
    client: httpx.Client,
    sleeper: Callable[[float], None],
) -> None:
    session = sign_in(
        client, config.firebase_web_api_key, config.parent_a_email, config.parent_a_password
    )
    sleeper(session.expires_in_seconds + EXPIRY_BUFFER_SECONDS)
    status = api_request(client, config.api_origin, "GET", "/api/v1/me", session.id_token)
    require_status("expiry_denial", status, {401, 403})


def run_smoke(
    env: dict[str, str],
    client: httpx.Client | None = None,
    selected_checks: set[str] | None = None,
    input_fn: Callable[[str], str] = input,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, str]:
    config = load_config(env)
    own_client = client is None
    client = client or httpx.Client(timeout=20)
    results: dict[str, str] = {}
    try:
        ready_status = api_request(client, config.api_origin, "GET", "/api/v1/ready")
        require_status("Readiness", ready_status, {200})
        results["ready"] = "PASS"

        session_a = sign_in(
            client, config.firebase_web_api_key, config.parent_a_email, config.parent_a_password
        )
        session_b = sign_in(
            client, config.firebase_web_api_key, config.parent_b_email, config.parent_b_password
        )
        for label, session in (("parent_a_me", session_a), ("parent_b_me", session_b)):
            status = api_request(client, config.api_origin, "GET", "/api/v1/me", session.id_token)
            require_status(label, status, {200})
            results[label] = "PASS"

        student_path = f"/api/v1/students/{config.parent_a_student_id}"
        student_status = api_request(
            client, config.api_origin, "GET", student_path, session_a.id_token
        )
        require_status("parent_a_student", student_status, {200})
        results["parent_a_student"] = "PASS"

        cross_get = api_request(client, config.api_origin, "GET", student_path, session_b.id_token)
        require_status("parent_b_cross_family_get", cross_get, {403, 404})
        results["parent_b_cross_family_get"] = "PASS"
        cross_patch = api_request(
            client,
            config.api_origin,
            "PATCH",
            student_path,
            session_b.id_token,
            {"preferred_name": "Unauthorized staging probe"},
        )
        require_status("parent_b_cross_family_patch", cross_patch, {403, 404})
        results["parent_b_cross_family_patch"] = "PASS"

        requested = selected_checks or set()
        if "revocation" in requested:
            verify_revocation(config, client, input_fn)
            results["revocation"] = "PASS"
        if "expiry" in requested:
            verify_expiry(config, client, sleeper)
            results["expiry"] = "PASS"
        if "project_mismatch" in requested:
            mismatch_names = (
                "STAGING_MISMATCH_FIREBASE_WEB_API_KEY",
                "STAGING_MISMATCH_PARENT_EMAIL",
                "STAGING_MISMATCH_PARENT_PASSWORD",
            )
            if any(not env.get(name, "").strip() for name in mismatch_names):
                results["project_mismatch"] = "NOT TESTED"
            else:
                mismatch_session = sign_in(
                    client,
                    env[mismatch_names[0]],
                    env[mismatch_names[1]],
                    env[mismatch_names[2]],
                )
                status = api_request(
                    client, config.api_origin, "GET", "/api/v1/me", mismatch_session.id_token
                )
                require_status("project_mismatch_denial", status, {401, 403})
                results["project_mismatch"] = "PASS"
        return results
    finally:
        if own_client:
            client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-revocation", action="store_true")
    parser.add_argument("--verify-expiry", action="store_true")
    parser.add_argument("--verify-project-mismatch", action="store_true")
    args = parser.parse_args()
    checks = {
        name
        for name, enabled in (
            ("revocation", args.verify_revocation),
            ("expiry", args.verify_expiry),
            ("project_mismatch", args.verify_project_mismatch),
        )
        if enabled
    }
    try:
        results = run_smoke(dict(os.environ), selected_checks=checks)
    except SmokeError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, sort_keys=True))
        return 1
    except Exception:
        print(json.dumps({"status": "failed", "error": "Staging smoke check failed"}, sort_keys=True))
        return 1
    print(json.dumps({"status": "ok", "checks": results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
