"""HTTP trust boundaries, replay and hypothetical lineage."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.contracts import Observation
from forecast_anything.jobs import JobQueue
from forecast_anything.operators import register_builtin_operators
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze
from forecast_anything.worker import Worker

T = datetime(2026, 10, 24, tzinfo=timezone.utc)
AUTH = {"Authorization": "Bearer test-token"}


def setup(tmp_path):
    ledger = Ledger(tmp_path / "state.db", clock=lambda: T)
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        register_builtin_operators(),
        lambda: T,
    )
    return (
        ledger,
        runtime,
        TestClient(create_app(ledger, runtime, "test-token"), headers=AUTH),
    )


def source(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n")
    return {
        "source_id": "sales",
        "kind": "csv",
        "location": str(path),
        "refresh_seconds": 60,
        "mapping": {
            "event_time": "time",
            "value": "value",
            "available_at": {"constant": "2026-10-23"},
            "revision": {"constant": "1"},
            "series_id": {"constant": "sales"},
            "unit": {"constant": "count"},
            "frequency": {"constant": "1d"},
            "timezone": {"constant": "UTC"},
            "calendar": {"constant": "gregorian"},
            "missing_values": {"constant": [""]},
        },
    }


def base_run(tmp_path):
    ledger, runtime, client = setup(tmp_path)
    registration = client.post("/v1/sources", json=source(tmp_path))
    assert registration.status_code == 201, registration.text
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get("/v1/jobs/" + registration.json()["job_id"]).json()
    candidate = client.get("/v1/candidates/" + job["result"]["candidate_ids"][0]).json()
    epoch = ledger.get_discovery_epoch(candidate["epoch_id"])
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "base",
            "graph": candidate["graph"],
            "snapshot_ids": {"sales": epoch.source_snapshot_ids[0]},
            "as_of": T.isoformat(),
        },
    )
    assert response.status_code == 202, response.text
    Worker(runtime, JobQueue(ledger)).run_due(T)
    run_id = client.get("/v1/jobs/" + response.json()["job_id"]).json()["result"][
        "run_id"
    ]
    return ledger, runtime, client, client.get("/v1/runs/" + run_id).json()


def test_workspace_token_is_required(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    runtime = Runtime(ledger, {}, {}, lambda: datetime.now(timezone.utc))
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


def test_invalid_plan_does_not_enqueue(tmp_path):
    ledger, _, client = setup(tmp_path)
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "bad",
            "graph": {
                "graph_id": "bad",
                "version": 1,
                "nodes": [
                    {"node_id": "bad", "kind": "forecast", "inputs": [], "config": {}}
                ],
            },
            "snapshot_ids": {},
            "as_of": T.isoformat(),
        },
    )
    assert response.status_code == 422
    with ledger._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_domain_error_has_stable_code(tmp_path):
    _, _, client = setup(tmp_path)
    response = client.get("/v1/runs/missing")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert "details" in response.json()


def test_two_event_consumers_resume_independently(tmp_path):
    ledger, runtime, a, run = base_run(tmp_path)
    b = TestClient(
        create_app(Ledger(ledger.path, clock=lambda: T), runtime, "test-token"),
        headers=AUTH,
    )
    history = a.get("/v1/events").json()
    assert history and history[-1]["kind"] == "run_completed"
    cursor = history[1]["cursor"]
    assert a.get("/v1/events", params={"after": cursor}).json() == history[2:]
    assert b.get("/v1/events").json() == history
    assert (
        b.get("/v1/events", headers={"Last-Event-ID": str(cursor)}).json()
        == history[2:]
    )
    stream = a.get("/v1/events/stream", params={"after": cursor, "follow": False})
    assert f"id: {history[-1]['cursor']}\n" in stream.text
    assert history[0]["event_id"] not in stream.text
    assert a.get("/v1/runs/" + run["run_id"]).json()["evidence_ids"] == []


def test_sources_are_write_only_and_discovery_is_provisional(tmp_path):
    ledger, runtime, client = setup(tmp_path)
    spec = source(tmp_path)
    spec["secret_ref"] = "private-secret-reference"
    # Registering credentials must not disclose them, even when inspection fails.
    response = client.post("/v1/sources", json=spec)
    assert "private-secret-reference" not in response.text
    assert "private-secret-reference" not in client.get("/v1/sources").text
    spec["secret_ref"] = None
    response = client.post("/v1/sources", json=spec)
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get("/v1/jobs/" + response.json()["job_id"]).json()
    candidate_id = job["result"]["candidate_ids"][0]
    watch = client.post(
        "/v1/watches",
        json={
            "candidate_id": candidate_id,
            "next_due_at": (T + timedelta(hours=1)).isoformat(),
        },
    )
    assert watch.status_code == 201, watch.text
    assert watch.json()["quality"] == "provisional"
    assert not watch.json()["operational"]
    assert (
        client.patch(
            "/v1/watches/" + watch.json()["watch_id"], json={"kind": "resumed"}
        ).status_code
        == 422
    )


def test_watch_read_synchronizes_current_clock(tmp_path):
    ledger, runtime, client, _ = base_run(tmp_path)
    with ledger._connection() as connection:
        candidate_id = connection.execute(
            "SELECT candidate_id FROM discovery_candidates LIMIT 1"
        ).fetchone()[0]
    created = client.post(
        "/v1/watches",
        json={
            "candidate_id": candidate_id,
            "next_due_at": (T + timedelta(seconds=1)).isoformat(),
        },
    )
    assert created.status_code == 201
    runtime.clock = ledger.clock = lambda: T + timedelta(seconds=2)
    watches = client.get("/v1/watches").json()
    assert watches[0]["quality"] == "stale"
    assert not watches[0]["operational"]


def test_scenario_does_not_rewrite_base(tmp_path):
    ledger, runtime, client, base = base_run(tmp_path)
    snapshot_id = base["snapshot_ids"][0]
    original = client.get("/v1/snapshots/" + snapshot_id).json()
    override = {
        **original,
        "observations": [{**o, "value": 100} for o in original["observations"]],
    }
    request = {
        "base_graph_id": base["graph_id"],
        "base_version": 1,
        "label": "Higher sales",
        "source_overrides": {"sales": override},
    }
    response = client.post("/v1/scenarios", json=request)
    assert response.status_code == 201, response.text
    scenario = response.json()
    assert scenario["parent_run_id"] == base["run_id"]
    assert scenario["graph_id"] != base["graph_id"]
    assert client.post("/v1/scenarios", json=request).json() == scenario
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get("/v1/jobs/" + scenario["job_id"]).json()
    run = client.get("/v1/runs/" + job["result"]["run_id"]).json()
    assert run["scenario_id"] == scenario["scenario_id"]
    assert run["parent_run_id"] == base["run_id"]
    assert "assumed" in str(
        client.get("/v1/snapshots/" + run["snapshot_ids"][0]).json()["assumptions"]
    )
    assert client.get("/v1/snapshots/" + snapshot_id).json() == original
    assert client.get("/v1/runs/" + base["run_id"]).json() == base
    from forecast_anything.evaluation.records import evaluate_run

    actuals = freeze(
        (
            Observation(
                series_id="sales",
                event_time=T + timedelta(days=1),
                available_at=T + timedelta(days=1),
                revision="1",
                value=100,
                unit="count",
            ),
        ),
        T + timedelta(days=1),
    )
    result = evaluate_run(
        ledger.get_run(run["run_id"]),
        actuals,
        ledger.get_graph(scenario["graph_id"], 1),
    )
    assert result.status == "insufficient_evidence" and result.origin_count == 0


def test_contract_export_is_deterministic_and_drift_checked(tmp_path):
    import runpy
    from pathlib import Path

    export_contracts = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/export_contracts.py")
    )["export_contracts"]
    export_contracts(tmp_path)
    before = (tmp_path / "openapi.json").read_bytes()
    export_contracts(tmp_path)
    assert (tmp_path / "openapi.json").read_bytes() == before
    import json

    schemas = json.loads((tmp_path / "schemas.json").read_text())
    assert "ScenarioRequest" in schemas and "Snapshot" in schemas
    assert "operational" in schemas["WatchView"]["properties"]


def test_cli_serve_and_worker_commands():
    import subprocess

    serve = subprocess.run(
        ["forecast-anything", "serve", "--help"], capture_output=True, text=True
    )
    worker = subprocess.run(
        ["forecast-anything", "worker", "--help"], capture_output=True, text=True
    )
    assert serve.returncode == 0 and "--host" in serve.stdout
    assert worker.returncode == 0 and "--once" in worker.stdout


def test_source_profile_retry_is_idempotent_across_clock_changes(tmp_path):
    ledger, runtime, client = setup(tmp_path)
    created = client.post("/v1/sources", json=source(tmp_path))
    assert created.status_code == 201
    runtime.clock = ledger.clock = lambda: T + timedelta(minutes=1)
    assert client.get("/v1/sources/sales/profile").status_code == 200
    assert (
        client.post("/v1/sources", json=source(tmp_path)).json()["job_id"]
        == created.json()["job_id"]
    )


def test_existing_graph_cannot_be_rebound_before_enqueue(tmp_path):
    ledger, _, client, base = base_run(tmp_path)
    graph = ledger.get_graph(base["graph_id"], 1).model_dump(mode="json")
    graph["nodes"][1]["config"]["options"]["period"] = 1
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "overwrite",
            "graph": graph,
            "snapshot_ids": {"sales": base["snapshot_ids"][0]},
            "as_of": T.isoformat(),
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "immutable_identity"
    with ledger._connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE logical_key='api/overwrite'"
            ).fetchone()[0]
            == 0
        )


def test_api_current_clock_blocks_expired_qualified_watch_and_resume(tmp_path):
    from test_worker import qualify_watch

    ledger, runtime, client = setup(tmp_path)
    qualify_watch(tmp_path, ledger)
    assert ledger.get_watch("watch").operational
    ledger.advance_watch("watch", {"kind": "paused"}, T, event_id="pause")
    runtime.clock = ledger.clock = lambda: T + timedelta(days=2)
    response = client.post(
        "/v1/jobs", json={"kind": "watch_resume", "key": "resume", "watch_id": "watch"}
    )
    assert response.status_code == 202
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock(), limit=1)
    current = client.get("/v1/watches").json()[0]
    assert current["lifecycle"] == "evaluating"
    assert current["quality"] == "stale" and not current["operational"]
    # Patching controls also reloads current state after synchronization.
    assert (
        client.patch("/v1/watches/watch", json={"priority": 5, "muted": False}).json()[
            "operational"
        ]
        is False
    )


def test_unavailable_source_is_sanitized_domain_error(tmp_path):
    _, _, client = setup(tmp_path)
    spec = source(tmp_path)
    spec["location"] = str(tmp_path / "private-nonexistent-file.csv")
    response = client.post("/v1/sources", json=spec)
    assert response.status_code == 422
    assert response.json()["code"] == "source_unavailable"
    assert "private-nonexistent" not in response.text


def test_serve_and_worker_recover_killed_job_via_http(tmp_path):
    import json
    import os
    import socket
    import subprocess
    import sys
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Event, Thread

    import httpx

    blocked, release = Event(), Event()

    class SourceHandler(BaseHTTPRequestHandler):
        calls = 0

        def do_GET(self):
            type(self).calls += 1
            if type(self).calls == 3:
                blocked.set()
                release.wait(10)
            body = json.dumps(
                [{"time": f"2026-10-{day}", "value": day} for day in (21, 22, 23)]
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

        def log_message(self, *args):
            pass

    fixture = ThreadingHTTPServer(("127.0.0.1", 0), SourceHandler)
    thread = Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    db = tmp_path / "process.db"
    env = {**os.environ, "FORECAST_ANYTHING_WORKSPACE_TOKEN": "test-token"}
    processes = []
    log = (tmp_path / "process.log").open("w")

    def launch(*args):
        process = subprocess.Popen(
            [sys.executable, "-m", "forecast_anything.cli", *args, "--db", str(db)],
            env=env,
            stdout=log,
            stderr=log,
        )
        processes.append(process)
        return process

    def wait_for(predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if value := predicate():
                    return value
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        pytest.fail(
            "Process recovery timeout: " + (tmp_path / "process.log").read_text()
        )

    try:
        server = launch("serve", "--port", str(port))
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", headers=AUTH, timeout=2
        ) as http:
            wait_for(lambda: http.get("/health").status_code == 200)
            assert (
                http.get(
                    "/v1/events", headers={"Authorization": "Bearer wrong"}
                ).status_code
                == 401
            )
            spec = source(tmp_path)
            spec.update(
                kind="http_json",
                location=f"http://127.0.0.1:{fixture.server_port}/source",
            )
            registration = http.post("/v1/sources", json=spec)
            assert registration.status_code == 201, registration.text
            job_id = registration.json()["job_id"]
            worker = launch("worker", "--lease-seconds", "2", "--poll-seconds", "0.05")
            assert blocked.wait(8)
            assert http.get("/v1/jobs/" + job_id).json()["state"] == "running"
            worker.kill()
            worker.wait(timeout=5)
            release.set()
            launch("worker", "--lease-seconds", "2", "--poll-seconds", "0.05")
            discovery = wait_for(
                lambda: (
                    j
                    if (j := http.get("/v1/jobs/" + job_id).json())["state"]
                    == "completed"
                    else None
                )
            )
            assert discovery["attempt"] == 1
            candidate = http.get(
                "/v1/candidates/" + discovery["result"]["candidate_ids"][0]
            ).json()
            snap_id = discovery["result"]["source_snapshot_ids"][0]
            snapshot = http.get("/v1/snapshots/" + snap_id).json()
            queued = http.post(
                "/v1/jobs",
                json={
                    "kind": "run",
                    "key": "process-run",
                    "graph": candidate["graph"],
                    "snapshot_ids": {"sales": snap_id},
                    "as_of": snapshot["as_of"],
                },
            )
            assert queued.status_code == 202, queued.text
            run_job_id = queued.json()["job_id"]
            completed = wait_for(
                lambda: (
                    j
                    if (j := http.get("/v1/jobs/" + run_job_id).json())["state"]
                    == "completed"
                    else None
                )
            )
            run = http.get("/v1/runs/" + completed["result"]["run_id"]).json()
            assert run["state"] == "completed" and run["evidence_ids"] == []
            history = http.get("/v1/events").json()
            assert len([e for e in history if e["kind"] == "run_completed"]) == 1
            cursor = history[1]["cursor"]
            server.terminate()
            server.wait(timeout=5)
            launch("serve", "--port", str(port))
            wait_for(lambda: http.get("/health").status_code == 200)
            assert (
                http.get("/v1/events", params={"after": cursor}).json() == history[2:]
            )
            assert http.get("/v1/events").json() == history
    finally:
        release.set()
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        fixture.shutdown()
        fixture.server_close()
        thread.join(timeout=5)
        log.close()


def test_generated_contracts_fail_check_when_drifted(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts/export_contracts.py"
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    (tmp_path / "schemas.json").write_text("{}")
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1 and "Contract drift" in result.stderr


def test_untrusted_candidate_cannot_supply_evidence_or_execution_graph(tmp_path):
    _, _, client = setup(tmp_path)
    spec = source(tmp_path)
    assert client.post("/v1/sources", json=spec).status_code == 201
    proposal = {
        "template_id": "forecast_change",
        "source_ids": ["sales"],
        "reason": "See changes",
    }
    candidate = client.post("/v1/candidates", json=proposal)
    assert candidate.status_code == 201
    assert (
        client.post(
            "/v1/candidates", json={**proposal, "graph": candidate.json()["graph"]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/watches",
            json={
                "candidate_id": candidate.json()["candidate_id"],
                "next_due_at": T.isoformat(),
                "eligibility_decision": {"action": "activate"},
            },
        ).status_code
        == 422
    )


def test_scenario_rejects_unknown_sources_and_forged_base(tmp_path):
    _, _, client, base = base_run(tmp_path)
    original = client.get("/v1/snapshots/" + base["snapshot_ids"][0]).json()
    response = client.post(
        "/v1/scenarios",
        json={
            "base_graph_id": base["graph_id"],
            "base_version": 1,
            "label": "bad",
            "source_overrides": {"unknown": original},
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_scenario_overrides"
    response = client.post(
        "/v1/scenarios",
        json={
            "base_graph_id": "missing",
            "base_version": 1,
            "label": "bad",
            "source_overrides": {"sales": original},
        },
    )
    assert response.status_code == 404


def test_job_key_cannot_be_reused_with_different_plan(tmp_path):
    ledger, _, client, base = base_run(tmp_path)
    graph = ledger.get_graph(base["graph_id"], 1).model_dump(mode="json")
    request = {
        "kind": "run",
        "key": "repeated",
        "graph": graph,
        "snapshot_ids": {"sales": base["snapshot_ids"][0]},
        "as_of": T.isoformat(),
    }
    response = client.post("/v1/jobs", json=request)
    assert response.status_code == 202
    assert (
        client.post("/v1/jobs", json=request).json()["job_id"]
        == response.json()["job_id"]
    )
    graph["graph_id"] = "different-graph"
    assert client.post("/v1/jobs", json=request).status_code == 409


def test_run_snapshot_binding_must_belong_to_registered_source(tmp_path):
    ledger, runtime, client, base = base_run(tmp_path)
    other = source(tmp_path)
    other["source_id"] = "other"
    response = client.post("/v1/sources", json=other)
    assert response.status_code == 201
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get("/v1/jobs/" + response.json()["job_id"]).json()
    snapshot_id = job["result"]["source_snapshot_ids"][0]
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "wrong-source",
            "graph": ledger.get_graph(base["graph_id"], 1).model_dump(mode="json"),
            "snapshot_ids": {"sales": snapshot_id},
            "as_of": T.isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "source_snapshot_lineage_mismatch"


def test_evaluation_actuals_must_belong_to_run_sources(tmp_path):
    ledger, runtime, client, base = base_run(tmp_path)
    other = source(tmp_path)
    other["source_id"] = "other"
    response = client.post("/v1/sources", json=other)
    Worker(runtime, JobQueue(ledger)).run_due(T)
    discovery = client.get("/v1/jobs/" + response.json()["job_id"]).json()
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "evaluation",
            "key": "wrong-actuals",
            "run_id": base["run_id"],
            "actuals_snapshot_id": discovery["result"]["source_snapshot_ids"][0],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "source_snapshot_lineage_mismatch"


def test_evaluation_job_reads_real_later_source_actuals(tmp_path):
    ledger, runtime, client = setup(tmp_path)
    runtime.clock = ledger.clock = lambda: T - timedelta(hours=12)
    spec = source(tmp_path)
    registered = client.post("/v1/sources", json=spec).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    discovery = client.get("/v1/jobs/" + registered["job_id"]).json()["result"]
    candidate = client.get("/v1/candidates/" + discovery["candidate_ids"][0]).json()
    snapshot = client.get("/v1/snapshots/" + discovery["source_snapshot_ids"][0]).json()
    issued = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "evaluated-run",
            "graph": candidate["graph"],
            "snapshot_ids": {"sales": snapshot["snapshot_id"]},
            "as_of": snapshot["as_of"],
        },
    ).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    run_id = client.get("/v1/jobs/" + issued["job_id"]).json()["result"]["run_id"]
    from pathlib import Path

    Path(spec["location"]).write_text(
        "time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n2026-10-24,4\n"
    )
    runtime.clock = ledger.clock = lambda: T + timedelta(days=1)
    refreshed = client.post("/v1/sources", json=spec).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    actuals_id = client.get("/v1/jobs/" + refreshed["job_id"]).json()["result"][
        "source_snapshot_ids"
    ][0]
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "evaluation",
            "key": "evaluate-issued",
            "run_id": run_id,
            "actuals_snapshot_id": actuals_id,
        },
    )
    assert response.status_code == 202, response.text
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    job = client.get("/v1/jobs/" + response.json()["job_id"]).json()
    assert job["state"] == "completed", job
    evaluation = client.get("/v1/evaluations/" + job["result"]["evaluation_id"]).json()
    assert evaluation["status"] == "evaluated" and evaluation["origin_count"] == 1
    assert evaluation["discovery"] is None
    assert client.get(f"/v1/runs/{run_id}/evaluations").json() == [evaluation]
    assert client.get(f"/v1/runs/{run_id}").json()["evidence_ids"] == []


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


@pytest.mark.parametrize("forecast_other", [False, True])
def test_evaluation_uses_each_forecasts_history_source(tmp_path, forecast_other):
    from pathlib import Path

    ledger, runtime, client = setup(tmp_path)
    runtime.clock = ledger.clock = lambda: T - timedelta(hours=12)
    spec = source(tmp_path)
    other = {**spec, "source_id": "other"}
    registered = client.post("/v1/sources", json=spec).json()
    other_registered = client.post("/v1/sources", json=other).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    first = client.get("/v1/jobs/" + registered["job_id"]).json()["result"]
    second = client.get("/v1/jobs/" + other_registered["job_id"]).json()["result"]
    candidate = client.get("/v1/candidates/" + first["candidate_ids"][0]).json()
    graph = candidate["graph"]
    graph["graph_id"] = "colliding-series-two-sources"
    source_config = next(
        node["config"] for node in graph["nodes"] if node["kind"] == "source"
    )
    graph["nodes"].append(
        {
            "node_id": "other-source",
            "kind": "source",
            "inputs": [],
            "config": {**source_config, "source_id": "other"},
        }
    )
    if forecast_other:
        forecast = next(node for node in graph["nodes"] if node["kind"] == "forecast")
        graph["nodes"].append(
            {
                "node_id": "other-forecast",
                "kind": "forecast",
                "inputs": ["other-source"],
                "config": {
                    **forecast["config"],
                    "history": "other-source",
                    "relation_type": {"other-source": "statistical"},
                },
            }
        )
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "collision-run",
            "graph": graph,
            "snapshot_ids": {
                "sales": first["source_snapshot_ids"][0],
                "other": second["source_snapshot_ids"][0],
            },
            "as_of": runtime.clock().isoformat(),
        },
    )
    assert response.status_code == 202, response.text
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    run_id = client.get("/v1/jobs/" + response.json()["job_id"]).json()["result"][
        "run_id"
    ]
    Path(spec["location"]).write_text(
        "time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n2026-10-24,99\n"
    )
    runtime.clock = ledger.clock = lambda: T + timedelta(days=1)
    refreshed = client.post("/v1/sources", json=other).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    actuals_id = client.get("/v1/jobs/" + refreshed["job_id"]).json()["result"][
        "source_snapshot_ids"
    ][0]
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "evaluation",
            "key": "wrong-collision-actuals",
            "run_id": run_id,
            "actuals_snapshot_id": actuals_id,
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == (
        "ambiguous_actuals_bindings"
        if forecast_other
        else "source_snapshot_lineage_mismatch"
    )
    with ledger._connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE logical_key='api/wrong-collision-actuals'"
            ).fetchone()[0]
            == 0
        )
    refreshed_base = client.post("/v1/sources", json=spec).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    base_actuals = client.get("/v1/jobs/" + refreshed_base["job_id"]).json()["result"][
        "source_snapshot_ids"
    ][0]
    own_response = client.post(
        "/v1/jobs",
        json={
            "kind": "evaluation",
            "key": "own-collision-actuals",
            "run_id": run_id,
            "actuals_snapshot_id": base_actuals,
        },
    )
    assert own_response.status_code == (422 if forecast_other else 202)
    if forecast_other:
        assert own_response.json()["code"] == "ambiguous_actuals_bindings"


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
        runtime.clock = ledger.clock = lambda: now
        Worker(runtime, JobQueue(ledger)).run_due(now)
    response = client.get("/v1/jobs/" + job.job_id)
    assert response.status_code == 200
    assert response.json()["state"] == "failed"
    assert response.json()["error"]["code"] == "invalid_config"
    assert "private-ref" not in response.text


def test_source_preview_does_not_register_or_enqueue(tmp_path):
    ledger, _, client = setup(tmp_path)
    spec = source(tmp_path)
    spec["mapping"].pop("unit")

    response = client.post("/v1/sources/preview", json=spec)

    assert response.status_code == 200, response.text
    profile = response.json()
    assert "unit" in profile["unresolved"]
    assert profile["source_id"] == "sales"
    assert client.get("/v1/sources").json() == []
    with ledger._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_source_preview_mapping_is_saved_and_read_back(tmp_path):
    _, _, client = setup(tmp_path)
    spec = source(tmp_path)

    preview = client.post("/v1/sources/preview", json=spec)
    assert preview.status_code == 200, preview.text
    saved = client.post("/v1/sources", json=spec)
    assert saved.status_code == 201, saved.text
    reread = client.get("/v1/sources/sales/profile")

    assert reread.status_code == 200
    assert reread.json() == preview.json()
    assert saved.json()["profile"] == reread.json()


def test_run_evaluations_are_authenticated_scoped_ordered_and_non_mutating(tmp_path):
    from forecast_anything.contracts import EvaluationRecord

    ledger, _, client, base = base_run(tmp_path)
    other = ledger.get_run(base["run_id"]).model_copy(update={"run_id": "other-run"})
    ledger.append_run(other, (), "other-run")
    for evaluation_id, run_id in (
        ("z-evaluation", base["run_id"]),
        ("other-evaluation", "other-run"),
        ("a-evaluation", base["run_id"]),
    ):
        ledger.append_evaluation(
            EvaluationRecord(
                evaluation_id=evaluation_id,
                run_id=run_id,
                actuals_snapshot_id=base["snapshot_ids"][0],
                status="pending",
                metrics={},
                origin_count=0,
                assumptions=(),
            )
        )
    empty = other.model_copy(update={"run_id": "empty-run"})
    ledger.append_run(empty, (), "empty-run")
    assert client.get("/v1/runs/empty-run/evaluations").json() == []
    path = f"/v1/runs/{base['run_id']}/evaluations"
    assert client.get(path, headers={"Authorization": ""}).status_code == 401
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert [item["evaluation_id"] for item in response.json()] == [
        "a-evaluation",
        "z-evaluation",
    ]
    assert all(item["run_id"] == base["run_id"] for item in response.json())
    assert client.get("/v1/runs/missing/evaluations").status_code == 404
    assert client.get(f"/v1/runs/{base['run_id']}").json() == base
