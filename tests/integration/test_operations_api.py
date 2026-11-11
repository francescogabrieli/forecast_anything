"""Durable operation reservation, namespaced queueing, and replay behavior."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.jobs import JobQueue
from forecast_anything.operators import register_builtin_operators
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.worker import Worker

T = datetime(2026, 11, 7, tzinfo=UTC)
AUTH = {"Authorization": "Bearer operations-token"}


def _setup(tmp_path):
    ledger = Ledger(tmp_path / "operations.db", clock=lambda: T)
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        register_builtin_operators(),
        lambda: T,
    )
    client = TestClient(create_app(ledger, runtime, "operations-token"), headers=AUTH)
    source_path = tmp_path / "source.csv"
    source_path.write_text("time,value\n2026-11-04,4\n2026-11-05,5\n2026-11-06,6\n")
    registration = client.post(
        "/v1/sources",
        json={
            "source_id": "sales",
            "kind": "csv",
            "location": str(source_path),
            "refresh_seconds": 60,
            "mapping": {
                "event_time": "time",
                "value": "value",
                "available_at": {"constant": "2026-11-06"},
                "revision": {"constant": "1"},
                "series_id": {"constant": "sales"},
                "unit": {"constant": "count"},
                "frequency": {"constant": "1d"},
                "timezone": {"constant": "UTC"},
                "calendar": {"constant": "gregorian"},
                "missing_values": {"constant": [""]},
            },
        },
    )
    assert registration.status_code == 201, registration.text
    Worker(runtime, JobQueue(ledger)).run_due(T)
    discovery = client.get("/v1/jobs/" + registration.json()["job_id"]).json()
    candidate = client.get(
        "/v1/candidates/" + discovery["result"]["candidate_ids"][0]
    ).json()
    snapshot_id = discovery["result"]["source_snapshot_ids"][0]
    forecast = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "prepare-operation-run",
            "graph": candidate["graph"],
            "snapshot_ids": {"sales": snapshot_id},
            "as_of": T.isoformat(),
        },
    )
    assert forecast.status_code == 202, forecast.text
    Worker(runtime, JobQueue(ledger)).run_due(T)
    forecast_job = client.get("/v1/jobs/" + forecast.json()["job_id"]).json()
    run_id = forecast_job["result"]["run_id"]
    return ledger, client, run_id, snapshot_id


def _operation(key="operation-key"):
    return {
        "key": key,
        "phase": "ready",
        "missing_data": [],
    }


def test_concurrent_operation_submission_is_replayable_and_namespaced(tmp_path):
    ledger, client, run_id, snapshot_id = _setup(tmp_path)
    created = client.post("/v1/operations", json=_operation())
    assert created.status_code == 201, created.text
    operation_id = created.json()["operation_id"]
    submission = {
        "expected_version": 1,
        "request": {
            "kind": "evaluation",
            "key": "shared-client-key",
            "run_id": run_id,
            "actuals_snapshot_id": snapshot_id,
        },
    }

    def submit(_):
        response = TestClient(client.app, headers=AUTH).post(
            f"/v1/operations/{operation_id}/submit", json=submission
        )
        assert response.status_code == 200, response.text
        return response.json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        views = list(pool.map(submit, range(16)))
    job_ids = {view["job_id"] for view in views}
    assert len(job_ids) == 1
    assert all(view["request_digest"] == views[0]["request_digest"] for view in views)

    legacy = client.post("/v1/jobs", json=submission["request"])
    assert legacy.status_code == 202, legacy.text
    legacy_job_id = legacy.json()["job_id"]
    assert legacy_job_id != views[0]["job_id"]
    assert ledger.get_operation(operation_id).job_id == views[0]["job_id"]

    conflict = client.post(
        f"/v1/operations/{operation_id}/submit",
        json={
            **submission,
            "request": {**submission["request"], "key": "different-client-key"},
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"


def test_operation_update_is_versioned_and_idempotent(tmp_path):
    _, client, _, _ = _setup(tmp_path)
    created = client.post(
        "/v1/operations",
        json={
            "key": "collect-operation",
            "phase": "collecting",
            "missing_data": ["horizon"],
        },
    )
    assert created.status_code == 201, created.text
    operation_id = created.json()["operation_id"]
    update = {
        "key": "supply-horizon",
        "expected_version": 1,
        "phase": "ready",
        "missing_data": [],
    }
    first = client.patch(f"/v1/operations/{operation_id}", json=update)
    retry = client.patch(f"/v1/operations/{operation_id}", json=update)
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert first.json()["version"] == 2

    stale = client.patch(
        f"/v1/operations/{operation_id}",
        json={**update, "key": "stale-update", "expected_version": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_operation_version"


@pytest.mark.parametrize("failure_point", ["before_enqueue", "after_enqueue"])
def test_resume_recovers_each_reserved_enqueue_interruption(
    tmp_path, monkeypatch, failure_point
):
    ledger, client, run_id, snapshot_id = _setup(tmp_path)
    operation = client.post("/v1/operations", json=_operation()).json()
    operation_id = operation["operation_id"]
    submission = {
        "expected_version": 1,
        "request": {
            "kind": "evaluation",
            "key": f"interrupted-{failure_point}",
            "run_id": run_id,
            "actuals_snapshot_id": snapshot_id,
        },
    }
    service = client.app.state.observatory
    if failure_point == "before_enqueue":
        enqueue = service.queue.enqueue
        calls = 0

        def fail_enqueue_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected before queue commit")
            return enqueue(*args, **kwargs)

        monkeypatch.setattr(service.queue, "enqueue", fail_enqueue_once)
    else:
        mark = ledger.mark_operation_enqueued
        calls = 0

        def fail_mark_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("injected after queue commit")
            return mark(*args, **kwargs)

        monkeypatch.setattr(ledger, "mark_operation_enqueued", fail_mark_once)

    non_raising = TestClient(client.app, headers=AUTH, raise_server_exceptions=False)
    interrupted = non_raising.post(
        f"/v1/operations/{operation_id}/submit", json=submission
    )
    assert interrupted.status_code == 500
    reserved = client.get(f"/v1/operations/{operation_id}").json()
    assert reserved["state"] in {"reserved", "submitted"}
    recovered = client.post(f"/v1/operations/{operation_id}/resume")
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["state"] == "submitted"
    assert recovered.json()["job_id"] == reserved["job_id"]
    replayed = client.post(f"/v1/operations/{operation_id}/resume")
    assert replayed.json()["job_id"] == recovered.json()["job_id"]


def test_guided_confirmation_rolls_back_source_when_enqueue_fails(
    tmp_path, monkeypatch
):
    _ledger, client, _, _ = _setup(tmp_path)
    service = client.app.state.observatory
    original = service.catalog.get("sales").revision
    spec = service.catalog.get("sales").spec.model_dump(mode="json")
    spec["mapping"]["unit"] = {"constant": "different"}
    as_of = T.isoformat()
    preview = client.post(
        "/v1/sources/csv-preview", json={"spec": spec, "as_of": as_of}
    ).json()

    def fail(*args, **kwargs):
        raise RuntimeError("injected enqueue failure")

    monkeypatch.setattr(service.queue, "enqueue", fail)
    with pytest.raises(RuntimeError, match="injected enqueue failure"):
        client.post(
            "/v1/sources/csv-confirm",
            json={
                "spec": spec,
                "as_of": as_of,
                "proposal_version": preview["proposal_version"],
                "key": "atomic-capture",
            },
        )
    assert service.catalog.get("sales").revision == original


def test_guided_confirmation_concurrent_conflict_cannot_supersede_winner(
    tmp_path, monkeypatch
):
    from threading import Barrier

    from forecast_anything.api import service as service_module

    _, client, _, _ = _setup(tmp_path)
    service = client.app.state.observatory
    original = service.catalog.get("sales").spec.model_dump(mode="json")
    requests = []
    for unit in ("one", "two"):
        spec = {
            **original,
            "mapping": {**original["mapping"], "unit": {"constant": unit}},
        }
        as_of = T.isoformat()
        preview = client.post(
            "/v1/sources/csv-preview", json={"spec": spec, "as_of": as_of}
        ).json()
        requests.append(
            {
                "spec": spec,
                "as_of": as_of,
                "proposal_version": preview["proposal_version"],
                "key": "concurrent-capture",
            }
        )
    gate = Barrier(2)
    capture = service_module.capture_confirmed_csv

    def synchronized(*args, **kwargs):
        result = capture(*args, **kwargs)
        gate.wait(timeout=10)
        return result

    monkeypatch.setattr(service_module, "capture_confirmed_csv", synchronized)

    def submit(body):
        return TestClient(client.app, headers=AUTH).post(
            "/v1/sources/csv-confirm", json=body
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, requests))
    assert sorted(response.status_code for response in responses) == [201, 409]
    winner = next(
        response.json() for response in responses if response.status_code == 201
    )
    assert service.catalog.get("sales").revision == winner["revision"]
    Worker(service.runtime, service.queue).run_due(T)
    assert client.get("/v1/jobs/" + winner["job_id"]).json()["state"] == "completed"


def test_guided_replay_grant_is_bound_to_original_adapter_session(tmp_path):
    _, client, _, _ = _setup(tmp_path)
    spec = client.app.state.observatory.catalog.get("sales").spec.model_dump(
        mode="json"
    )
    as_of = T.isoformat()
    preview = client.post(
        "/v1/sources/csv-preview", json={"spec": spec, "as_of": as_of}
    ).json()
    request = {
        "spec": spec,
        "as_of": as_of,
        "proposal_version": preview["proposal_version"],
        "key": "session-capture",
        "adapter_session": "a" * 32,
    }
    first = client.post("/v1/sources/csv-confirm", json=request).json()
    same = client.post("/v1/sources/csv-confirm", json=request).json()
    other = client.post(
        "/v1/sources/csv-confirm", json={**request, "adapter_session": "b" * 32}
    ).json()
    assert not first["replayed"]
    assert same["replayed"] and same["session_grant"]
    assert other["replayed"] and not other["session_grant"]
    assert first["job_id"] == same["job_id"] == other["job_id"]


def test_guided_commit_with_lost_http_response_keeps_session_grant(
    tmp_path, monkeypatch
):
    import asyncio

    import httpx
    from mcp import Client

    from forecast_anything.mcp_adapter import server as server_module
    from forecast_anything.mcp_adapter.client import CoreClient
    from forecast_anything.mcp_adapter.config import McpConfig

    _, client, _, _ = _setup(tmp_path)
    spec = client.app.state.observatory.catalog.get("sales").spec.model_dump(
        mode="json"
    )
    dropped = False

    class DropFirstConfirmation(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = httpx.ASGITransport(app=client.app)

        async def handle_async_request(self, request):
            nonlocal dropped
            response = await self.inner.handle_async_request(request)
            if request.url.path == "/v1/sources/csv-confirm" and not dropped:
                dropped = True
                await response.aclose()
                raise httpx.ReadError("simulated lost response", request=request)
            return response

    monkeypatch.setattr(
        server_module,
        "CoreClient",
        lambda cfg: CoreClient(cfg, transport=DropFirstConfirmation()),
    )
    config = McpConfig(workspace_token="operations-token", csv_roots=(tmp_path,))

    async def journey():
        async with Client(server_module.create_server(config)) as mcp:
            preview = (
                await mcp.call_tool(
                    "preview_csv_source", {"spec": spec, "as_of": T.isoformat()}
                )
            ).structured_content["data"]
            args = {
                "spec": spec,
                "as_of": T.isoformat(),
                "proposal_version": preview["proposal_version"],
                "key": "lost-after-commit",
            }
            failed = await mcp.call_tool("confirm_csv_source", args)
            assert failed.structured_content["code"] == "network_error"
            replay = await mcp.call_tool("confirm_csv_source", args)
            assert replay.structured_content["data"]["replayed"]
            assert (
                await mcp.call_tool("get_source_profile", {"source_id": "sales"})
            ).structured_content["ok"]
        async with Client(server_module.create_server(config)) as mcp:
            replay = await mcp.call_tool("confirm_csv_source", args)
            assert replay.structured_content["data"]["replayed"]
            assert (
                await mcp.call_tool("get_source_profile", {"source_id": "sales"})
            ).structured_content["code"] == "source_forbidden"

    asyncio.run(journey())
