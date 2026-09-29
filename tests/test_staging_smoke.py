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


def synthetic_handler(state):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identitytoolkit.googleapis.com":
            state["tokens"] = state.get("tokens", 0) + 1
            return httpx.Response(
                200,
                json={"idToken": f"memory-only-token-{state['tokens']}", "expiresIn": "60"},
            )
        if request.url.path.endswith("/ready"):
            return httpx.Response(200, json={})
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if request.url.path.endswith("/me"):
            if token == "memory-only-token-4":
                return httpx.Response(state.get("mismatch_status", 401))
            if token == "memory-only-token-3":
                state["fresh_calls"] = state.get("fresh_calls", 0) + 1
                if state.get("fresh_token_denied") or state.get("denied"):
                    return httpx.Response(401)
            number = 2 if token == "memory-only-token-2" else 1
            identity = {
                "id": f"synthetic-parent-{number}",
                "email": f"parent-{'b' if number == 2 else 'a'}@example.test",
                "role": "parent",
                "is_active": True,
            }
            identity.update(state.get(f"identity_{number}", {}))
            return httpx.Response(200, json=identity)
        if request.method == "GET":
            if token == "memory-only-token-2":
                return httpx.Response(403)
            return httpx.Response(
                200, json={"id": state.get("student_id", smoke_env()["STAGING_PARENT_A_STUDENT_ID"])}
            )
        if request.method == "PATCH":
            return httpx.Response(403)
        return httpx.Response(500)

    return handler


def test_authentication_failure_does_not_print_password_or_token(capsys):
    password = "parent-a-password-secret"
    token = "sensitive-token-from-error-body"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/ready"):
            return httpx.Response(200, json={"status": "ready"})
        return httpx.Response(400, json={"error": {"message": token, "password": password}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SmokeError) as raised:
            run_smoke(smoke_env(), client)
    safe_output = str(raised.value)
    print(json.dumps({"status": "failed", "error": safe_output}))
    output = capsys.readouterr().out + safe_output
    assert password not in output
    assert token not in output
    assert "HTTP 400" in output


def test_failed_cross_family_status_fails_command():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "identitytoolkit.googleapis.com":
            email = json.loads(request.content)["email"]
            token = "parent-b" if email.startswith("parent-b") else "parent-a"
            return httpx.Response(200, json={"idToken": token, "expiresIn": "3600"})
        if request.url.path.endswith("/ready"):
            return httpx.Response(200, json={})
        if request.url.path.endswith("/me"):
            is_b = request.headers.get("Authorization") == "Bearer parent-b"
            return httpx.Response(
                200,
                json={
                    "id": "b" if is_b else "a",
                    "email": "parent-b@example.test" if is_b else "parent-a@example.test",
                    "role": "parent",
                    "is_active": True,
                },
            )
        return httpx.Response(200, json={"id": smoke_env()["STAGING_PARENT_A_STUDENT_ID"]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SmokeError, match="parent_b_cross_family_get: expected HTTP 403, 404"):
            run_smoke(smoke_env(), client)


@pytest.mark.parametrize(
    ("identity_override", "message"),
    [
        ({"role": "admin"}, "expected active synthetic parent"),
        ({"email": "other@example.test"}, "expected active synthetic parent"),
        ({"is_active": False}, "expected active synthetic parent"),
        ({"id": "synthetic-parent-1"}, "distinct user IDs"),
    ],
)
def test_rejects_wrong_guardian_identity(identity_override, message):
    state = {"identity_2": identity_override}
    with httpx.Client(transport=httpx.MockTransport(synthetic_handler(state))) as client:
        with pytest.raises(SmokeError, match=message):
            run_smoke(smoke_env(), client)


def test_rejects_wrong_known_learner_id():
    state = {"student_id": "00000000-0000-4000-8000-000000000002"}
    with httpx.Client(transport=httpx.MockTransport(synthetic_handler(state))) as client:
        with pytest.raises(SmokeError, match="expected known synthetic learner ID"):
            run_smoke(smoke_env(), client)


def test_revocation_requires_fresh_token_acceptance_before_prompt(capsys):
    state = {}
    prompts = []
    with httpx.Client(transport=httpx.MockTransport(synthetic_handler(state))) as client:
        results = run_smoke(
            smoke_env(),
            client,
            selected_checks={"revocation"},
            input_fn=lambda prompt: prompts.append(prompt) or state.update(denied=True) or "",
        )
    print(json.dumps({"status": "ok", "checks": results}))
    output = capsys.readouterr().out + repr(results) + repr(prompts)
    assert results["revocation"] == "PASS"
    assert state["tokens"] == 3
    assert state["fresh_calls"] == 2
    assert len(prompts) == 1
    assert "memory-only-token-3" not in output


def test_expiry_requires_fresh_token_acceptance_before_wait():
    state = {}
    waited = []
    with httpx.Client(transport=httpx.MockTransport(synthetic_handler(state))) as client:
        results = run_smoke(
            smoke_env(),
            client,
            selected_checks={"expiry"},
            sleeper=lambda seconds: waited.append(seconds) or state.update(denied=True),
        )
    assert results["expiry"] == "PASS"
    assert state["tokens"] == 3
    assert state["fresh_calls"] == 2
    assert waited == [70]


@pytest.mark.parametrize("check", ["revocation", "expiry"])
def test_fresh_token_denied_before_action_fails(check):
    state = {"fresh_token_denied": True}
    actions = []
    with httpx.Client(transport=httpx.MockTransport(synthetic_handler(state))) as client:
        with pytest.raises(SmokeError, match=f"{check}_baseline: expected HTTP 200"):
            run_smoke(
                smoke_env(),
                client,
                selected_checks={check},
                input_fn=lambda prompt: actions.append("revoke") or "",
                sleeper=lambda seconds: actions.append("sleep"),
            )
    assert actions == []


def test_wrong_project_requires_authentication_denial():
    env = smoke_env()
    env.update(
        STAGING_MISMATCH_FIREBASE_WEB_API_KEY="different-public-key",
        STAGING_MISMATCH_PARENT_EMAIL="synthetic-other@example.test",
        STAGING_MISMATCH_PARENT_PASSWORD="synthetic-other-password",
    )
    with httpx.Client(
        transport=httpx.MockTransport(synthetic_handler({"mismatch_status": 403}))
    ) as client:
        with pytest.raises(SmokeError, match="project_mismatch_denial: expected HTTP 401"):
            run_smoke(env, client, selected_checks={"project_mismatch"})


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
