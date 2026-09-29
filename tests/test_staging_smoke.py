import json

import httpx
import pytest

from scripts.staging_smoke import SmokeError, run_smoke


def smoke_env() -> dict[str, str]:
    return {
        "STAGING_API_ORIGIN": "https://api.staging.skillsprout.example",
        "STAGING_EXPECTED_API_ORIGIN": "https://api.staging.skillsprout.example",
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
            return httpx.Response(200, json={"idToken": "memory-only-token", "expiresIn": "3600"})
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


def test_revocation_uses_an_in_memory_token_and_reports_no_token(capsys):
    token_calls = 0
    prompts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.host == "identitytoolkit.googleapis.com":
            token_calls += 1
            return httpx.Response(
                200, json={"idToken": f"memory-only-token-{token_calls}", "expiresIn": "60"}
            )
        if request.url.path.endswith("/ready"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/me"):
            if request.headers.get("Authorization") == "Bearer memory-only-token-3":
                return httpx.Response(401, json={"detail": "denied"})
            return httpx.Response(200, json={})
        if request.method == "GET":
            if request.headers.get("Authorization") == "Bearer memory-only-token-2":
                return httpx.Response(403, json={"detail": "denied"})
            return httpx.Response(200, json={})
        return httpx.Response(403, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results = run_smoke(
            smoke_env(),
            client,
            selected_checks={"revocation"},
            input_fn=lambda prompt: prompts.append(prompt) or "",
        )

    print(json.dumps({"status": "ok", "checks": results}))
    output = capsys.readouterr().out + repr(results) + repr(prompts)
    assert results["revocation"] == "PASS"
    assert token_calls == 3
    assert prompts == ["Revoke sessions for synthetic guardian A, then press Enter to verify denial: "]
    assert "memory-only-token-3" not in output


def test_expiry_waits_through_session_expiry_before_verifying_denial():
    token_calls = 0
    waited: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.host == "identitytoolkit.googleapis.com":
            token_calls += 1
            return httpx.Response(
                200, json={"idToken": f"memory-only-token-{token_calls}", "expiresIn": "60"}
            )
        if request.url.path.endswith("/ready"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/me"):
            if request.headers.get("Authorization") == "Bearer memory-only-token-3":
                return httpx.Response(401, json={"detail": "expired"})
            return httpx.Response(200, json={})
        if request.method == "GET":
            if request.headers.get("Authorization") == "Bearer memory-only-token-2":
                return httpx.Response(403, json={"detail": "denied"})
            return httpx.Response(200, json={})
        return httpx.Response(403, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results = run_smoke(
            smoke_env(), client, selected_checks={"expiry"}, sleeper=waited.append
        )

    assert results["expiry"] == "PASS"
    assert token_calls == 3
    assert waited == [70]


def test_requires_expected_api_origin_before_requests():
    calls = 0
    env = smoke_env()
    env.pop("STAGING_EXPECTED_API_ORIGIN")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SmokeError, match="STAGING_EXPECTED_API_ORIGIN"):
            run_smoke(env, client)

    assert calls == 0


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("STAGING_API_ORIGIN", "http://api.staging.skillsprout.example"),
        ("STAGING_EXPECTED_API_ORIGIN", "https://api.staging.skillsprout.example/path"),
    ],
)
def test_rejects_malformed_api_origin_before_requests(variable, value):
    calls = 0
    env = smoke_env()
    env[variable] = value

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SmokeError, match=variable):
            run_smoke(env, client)

    assert calls == 0


@pytest.mark.parametrize(
    "actual_origin",
    [
        "https://other-staging.skillsprout.example",
        "https://api.skillsprout.example",
    ],
)
def test_rejects_mismatched_or_production_api_origin_before_requests(actual_origin):
    calls = 0
    env = smoke_env()
    env["STAGING_API_ORIGIN"] = actual_origin

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SmokeError, match="must match"):
            run_smoke(env, client)

    assert calls == 0
