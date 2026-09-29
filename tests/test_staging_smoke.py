import json

import httpx
import pytest

from scripts.staging_smoke import SmokeError, run_smoke


def smoke_env() -> dict[str, str]:
    return {
        "STAGING_API_ORIGIN": "https://api.staging.skillsprout.example",
        "STAGING_FIREBASE_WEB_API_KEY": "public-web-key",
        "STAGING_PARENT_A_EMAIL": "parent-a@example.test",
        "STAGING_PARENT_A_PASSWORD": "parent-a-password-secret",
        "STAGING_PARENT_B_EMAIL": "parent-b@example.test",
        "STAGING_PARENT_B_PASSWORD": "parent-b-password-secret",
        "STAGING_PARENT_A_STUDENT_ID": "00000000-0000-4000-8000-000000000001",
    }


def test_authentication_failure_does_not_print_password_or_token(capsys):
    password = "parent-a-password-secret"
    token = "sensitive-token-from-error-body"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ready"):
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(400, json={"error": {"message": token, "password": password}})

    try:
        run_smoke(smoke_env(), httpx.Client(transport=httpx.MockTransport(handler)))
    except SmokeError as exc:
        safe_output = str(exc)
    else:
        raise AssertionError("failed Firebase authentication should fail the smoke command")
    print(json.dumps({"status": "failed", "error": safe_output}))
    output = capsys.readouterr().out + safe_output
    assert password not in output
    assert token not in output
    assert "HTTP 400" in output


def test_failed_cross_family_status_fails_command():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identitytoolkit.googleapis.com":
            return httpx.Response(200, json={"idToken": "memory-only-token"})
        path = request.url.path
        if path.endswith("/ready") or path.endswith("/me"):
            return httpx.Response(200, json={})
        if request.method == "GET":
            return httpx.Response(200, json={"id": "synthetic-student"})
        if request.method == "PATCH":
            return httpx.Response(200, json={"status": "updated"})
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SmokeError, match="parent_b_cross_family_get: expected HTTP 403, 404"):
            run_smoke(smoke_env(), client)
