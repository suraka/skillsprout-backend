"""Authentication and family authorization smoke checks for isolated staging."""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx


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


def load_config(env: dict[str, str]) -> SmokeConfig:
    names = (
        "STAGING_API_ORIGIN",
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
    origin = env["STAGING_API_ORIGIN"].strip().rstrip("/")
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
        raise SmokeError("STAGING_API_ORIGIN must be an HTTPS origin without credentials or path")
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


def sign_in(client: httpx.Client, api_key: str, email: str, password: str) -> str:
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
    token = _json(response).get("idToken")
    if not isinstance(token, str) or not token:
        raise SmokeError("Firebase sign-in response did not contain an ID token")
    return token


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


def run_smoke(
    env: dict[str, str],
    client: httpx.Client | None = None,
    selected_checks: set[str] | None = None,
) -> dict[str, str]:
    config = load_config(env)
    own_client = client is None
    client = client or httpx.Client(timeout=20)
    results: dict[str, str] = {}
    try:
        ready_status = api_request(client, config.api_origin, "GET", "/api/v1/ready")
        require_status("Readiness", ready_status, {200})
        results["ready"] = "PASS"

        token_a = sign_in(
            client, config.firebase_web_api_key, config.parent_a_email, config.parent_a_password
        )
        token_b = sign_in(
            client, config.firebase_web_api_key, config.parent_b_email, config.parent_b_password
        )
        for label, token in (("parent_a_me", token_a), ("parent_b_me", token_b)):
            status = api_request(client, config.api_origin, "GET", "/api/v1/me", token)
            require_status(label, status, {200})
            results[label] = "PASS"

        student_path = f"/api/v1/students/{config.parent_a_student_id}"
        student_status = api_request(client, config.api_origin, "GET", student_path, token_a)
        require_status("parent_a_student", student_status, {200})
        results["parent_a_student"] = "PASS"

        cross_get = api_request(client, config.api_origin, "GET", student_path, token_b)
        require_status("parent_b_cross_family_get", cross_get, {403, 404})
        results["parent_b_cross_family_get"] = "PASS"
        cross_patch = api_request(
            client,
            config.api_origin,
            "PATCH",
            student_path,
            token_b,
            {"preferred_name": "Unauthorized staging probe"},
        )
        require_status("parent_b_cross_family_patch", cross_patch, {403, 404})
        results["parent_b_cross_family_patch"] = "PASS"

        requested = selected_checks or set()
        for mode, env_name in (
            ("revocation", "STAGING_REVOKED_FIREBASE_ID_TOKEN"),
            ("expiry", "STAGING_EXPIRED_FIREBASE_ID_TOKEN"),
        ):
            if mode not in requested:
                continue
            test_token = env.get(env_name, "").strip()
            if not test_token:
                results[mode] = "NOT TESTED"
                continue
            status = api_request(client, config.api_origin, "GET", "/api/v1/me", test_token)
            require_status(f"{mode}_denial", status, {401, 403})
            results[mode] = "PASS"

        if "project_mismatch" in requested:
            mismatch_names = (
                "STAGING_MISMATCH_FIREBASE_WEB_API_KEY",
                "STAGING_MISMATCH_PARENT_EMAIL",
                "STAGING_MISMATCH_PARENT_PASSWORD",
            )
            if any(not env.get(name, "").strip() for name in mismatch_names):
                results["project_mismatch"] = "NOT TESTED"
            else:
                mismatch_token = sign_in(
                    client,
                    env[mismatch_names[0]],
                    env[mismatch_names[1]],
                    env[mismatch_names[2]],
                )
                status = api_request(client, config.api_origin, "GET", "/api/v1/me", mismatch_token)
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
