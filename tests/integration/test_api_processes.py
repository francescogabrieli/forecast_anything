"""HTTP service recovery and generated contract checks."""

import contextlib
from pathlib import Path

import pytest
from api_fixtures import AUTH, source


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
            with contextlib.suppress(BrokenPipeError):
                self.wfile.write(body)

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
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "fixtures/library_cli.py"),
                *args,
                "--db",
                str(db),
            ],
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
