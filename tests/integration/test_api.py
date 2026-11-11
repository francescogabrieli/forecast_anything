"""HTTP authentication, browser sessions, and public errors."""

from datetime import UTC, datetime, timedelta

import pytest
from api_fixtures import T, base_run, setup
from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.jobs import JobQueue
from forecast_anything.operators import register_builtin_operators
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.worker import Worker


def test_workspace_token_is_required(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    runtime = Runtime(ledger, {}, {}, lambda: datetime.now(UTC))
    client = TestClient(create_app(ledger, runtime, workspace_token="test-token"))
    assert client.get("/v1/sources").status_code == 401


def test_console_cors_allows_only_configured_origins(tmp_path):
    ledger = Ledger(tmp_path / "cors.db", clock=lambda: T)
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        register_builtin_operators(),
        lambda: T,
    )
    client = TestClient(
        create_app(
            ledger,
            runtime,
            "test-token",
            console_origins=("http://127.0.0.1:4173",),
        )
    )
    allowed = client.options(
        "/v1/events/stream",
        headers={
            "Origin": "http://127.0.0.1:4173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:4173"
    denied = client.options(
        "/v1/events/stream",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.parametrize(
    "path",
    [
        "/v1/events",
        "/v1/events/stream",
        "/v1/capabilities",
        "/v1/sources/s/profile",
        "/v1/sources/preview",
        "/openapi.json",
        "/docs",
    ],
)
def test_request_without_token_is_401(tmp_path, path):
    _, _, client = setup(tmp_path)
    assert TestClient(client.app).get(path).status_code == 401
    assert TestClient(client.app).get("/health").status_code == 200


def test_domain_error_has_stable_code(tmp_path):
    _, _, client = setup(tmp_path)
    response = client.get("/v1/runs/missing")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert "details" in response.json()


def test_domain_validation_errors_never_echo_submitted_credentials(tmp_path):
    _, _, client = setup(tmp_path)
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "credential-error",
            "graph": {
                "graph_id": "invalid-secret-config",
                "version": 1,
                "nodes": [
                    {
                        "node_id": "source",
                        "kind": "source",
                        "inputs": [],
                        "config": {
                            "source_id": "sales",
                            "series_ids": ["sales"],
                            "units": ["count"],
                            "frequency": "1d",
                            "secret_ref": "private-ref",
                            "extra": {"Authorization": "Bearer private-token"},
                        },
                    }
                ],
            },
            "snapshot_ids": {},
            "as_of": T.isoformat(),
        },
    )
    assert response.status_code == 422
    payload = response.json()
    assert set(payload) == {"code", "details"}
    assert payload["code"] == "invalid_config"
    assert payload["details"]["errors"]
    assert "private-ref" not in response.text
    assert "private-token" not in response.text
    assert all(set(error) == {"loc", "type"} for error in payload["details"]["errors"])


def test_persisted_job_validation_errors_are_sanitized_on_read(tmp_path):
    ledger, runtime, client = setup(tmp_path)
    job = JobQueue(ledger).enqueue(
        "legacy-invalid-plan",
        {
            "kind": "run",
            "graph": {
                "graph_id": "bad",
                "version": 1,
                "nodes": [
                    {
                        "node_id": "s",
                        "kind": "source",
                        "inputs": [],
                        "config": {"secret_ref": "private-ref"},
                    }
                ],
            },
            "snapshots": {},
            "as_of": T.isoformat(),
        },
    )
    for seconds in (0, 31, 62):
        now = T + timedelta(seconds=seconds)
        runtime.clock = ledger.clock = lambda now=now: now
        Worker(runtime, JobQueue(ledger)).run_due(now)
    response = client.get("/v1/jobs/" + job.job_id)
    assert response.status_code == 200
    assert response.json()["state"] == "failed"
    assert response.json()["error"]["code"] == "invalid_config"
    assert "private-ref" not in response.text


def test_workspace_identity_is_authenticated_stable_and_distinct(tmp_path):
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    ledger, _, client = setup(first_dir)
    _, _, other = setup(second_dir)
    first = client.get("/v1/workspace")
    assert first.status_code == 200
    workspace_id = first.json()["workspace_id"]
    assert len(workspace_id) == 32
    assert client.get("/v1/workspace").json()["workspace_id"] == workspace_id
    assert Ledger(ledger.path).workspace_id() == workspace_id
    assert other.get("/v1/workspace").json()["workspace_id"] != workspace_id
    assert (
        client.get(
            "/v1/workspace", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )


def test_browser_session_is_scoped_expires_and_is_revocable(tmp_path, monkeypatch):
    import forecast_anything.api.app as app_module

    ledger = Ledger(tmp_path / "browser-session.db", clock=lambda: T)
    runtime = Runtime(ledger, {}, {}, lambda: T)
    origin = "http://127.0.0.1:4173"
    client = TestClient(
        create_app(ledger, runtime, "test-token", console_origins=(origin,)),
        base_url="http://localhost",
    )
    now = [1000.0]
    monkeypatch.setattr(app_module, "_session_now", lambda: now[0])
    assert (
        client.post(
            "/v1/browser-session",
            headers={
                "Authorization": "Bearer test-token",
                "Origin": "http://evil.example",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/browser-session",
            headers={"Authorization": "Bearer wrong", "Origin": origin},
        ).status_code
        == 401
    )
    linked = client.post(
        "/v1/browser-session",
        headers={"Authorization": "Bearer test-token", "Origin": origin},
    )
    assert linked.status_code == 201
    assert "test-token" not in linked.text
    assert "httponly" in linked.headers["set-cookie"].lower()
    saved_cookie = linked.headers["set-cookie"].split(";", 1)[0]
    assert client.get("/v1/workspace", headers={"Origin": origin}).status_code == 200
    restarted = TestClient(
        create_app(ledger, runtime, "test-token", console_origins=(origin,)),
        base_url="http://localhost",
    )
    assert (
        restarted.get(
            "/v1/workspace", headers={"Origin": origin, "Cookie": saved_cookie}
        ).status_code
        == 401
    )
    assert client.get("/v1/workspace").status_code == 401
    assert (
        client.get(
            "/v1/workspace", headers={"Origin": "http://evil.example"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/browser-session/revoke", headers={"Origin": origin}
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/v1/workspace", headers={"Origin": origin, "Cookie": saved_cookie}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/browser-session",
            headers={"Authorization": "Bearer test-token", "Origin": origin},
        ).status_code
        == 201
    )
    assert client.get("/v1/workspace", headers={"Origin": origin}).status_code == 200
    now[0] += 8 * 60 * 60 + 1
    assert client.get("/v1/workspace", headers={"Origin": origin}).status_code == 401


def test_resource_identity_is_small_authenticated_and_rejects_missing(tmp_path):
    _, _, client, run = base_run(tmp_path)
    question = client.post(
        "/v1/questions",
        json={
            "key": "identity-question",
            "title": "Sales",
            "meaning": "Forecast sales",
            "source_ids": ["sales"],
            "selection": {"provider": "seasonal_naive", "horizon": 1},
        },
    ).json()
    for kind, identifier in [
        ("run", run["run_id"]),
        ("question", question["question_id"]),
    ]:
        url = f"/v1/resource-identities/{kind}/{identifier}"
        assert client.get(url).json() == {"kind": kind, "resource_id": identifier}
        assert client.get(url, headers={"Authorization": ""}).status_code == 401
    for kind in ("run", "question", "report"):
        assert client.get(f"/v1/resource-identities/{kind}/missing").status_code == 404
