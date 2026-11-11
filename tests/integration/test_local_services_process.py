import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from urllib.error import URLError
from urllib.request import Request, urlopen


def test_up_serves_health_and_stops_on_sigterm(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "FORECAST_ANYTHING_WORKSPACE_TOKEN": "test-private-token"}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "forecast_anything.cli",
            "up",
            "--db",
            str(tmp_path / "state.db"),
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/health"
    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                with urlopen(url, timeout=1) as response:
                    assert response.status == 200
                break
            except (URLError, TimeoutError):
                # The supervisor listens before its API child can answer.
                assert process.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.05)
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=10) == 0
        try:
            urlopen(url, timeout=1)
        except URLError:
            pass
        else:
            raise AssertionError("API remained available after shutdown")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_initialized_workspace_runs_and_reports_api_status(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    root = tmp_path / "sources"
    root.mkdir()
    config = tmp_path / "workspace" / "config.json"
    command = [sys.executable, "-m", "forecast_anything.cli"]
    created = subprocess.run(
        [
            *command,
            "init",
            "--workspace",
            str(config.parent),
            "--csv-root",
            str(root),
            "--port",
            str(port),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    token = json.loads(config.read_text())["token"]
    assert token not in created.stdout and token not in created.stderr
    assert (
        subprocess.run(
            [*command, "status", "--config", str(config)], capture_output=True
        ).returncode
        == 1
    )
    process = subprocess.Popen(
        [*command, "up", "--config", str(config)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while True:
            result = subprocess.run(
                [*command, "status", "--config", str(config)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                break
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(0.05)
        assert json.loads(result.stdout) == {"api": "available", "worker": "running"}
        assert token not in result.stdout and token not in result.stderr
        saved = config.read_text()
        altered = json.loads(saved)
        altered["token"] = "wrong-token"
        config.write_text(json.dumps(altered))
        denied = subprocess.run(
            [*command, "status", "--config", str(config)],
            capture_output=True,
            text=True,
        )
        assert denied.returncode == 1
        assert json.loads(denied.stdout)["api"] == "authentication_or_api_error"
        config.write_text(saved)
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=10) == 0
        assert (
            subprocess.run(
                [*command, "status", "--config", str(config)], capture_output=True
            ).returncode
            == 1
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_standalone_worker_sigterm_clears_heartbeat(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    root = tmp_path / "workspace"
    csv_root = tmp_path / "sources"
    csv_root.mkdir()
    config = root / "config.json"
    command = [sys.executable, "-m", "forecast_anything.cli"]
    subprocess.run(
        [
            *command,
            "init",
            "--workspace",
            str(root),
            "--csv-root",
            str(csv_root),
            "--port",
            str(port),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    token = json.loads(config.read_text())["token"]
    env = {**os.environ, "FORECAST_ANYTHING_WORKSPACE_TOKEN": token}
    api = subprocess.Popen(
        [*command, "serve", "--db", str(root / "state.db"), "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    worker = None
    try:
        deadline = time.monotonic() + 10
        while True:
            result = subprocess.run(
                [*command, "status", "--config", str(config)],
                capture_output=True,
                text=True,
            )
            if result.stdout and json.loads(result.stdout).get("api") == "available":
                break
            assert api.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.05)

        worker = subprocess.Popen(
            [
                *command,
                "worker",
                "--db",
                str(root / "state.db"),
                "--poll-seconds",
                "0.05",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        while True:
            result = subprocess.run(
                [*command, "status", "--config", str(config)],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                break
            assert api.poll() is None and worker.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.05)
        worker.send_signal(signal.SIGTERM)
        assert worker.wait(timeout=5) == 0
        result = subprocess.run(
            [*command, "status", "--config", str(config)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert json.loads(result.stdout) == {
            "api": "available",
            "worker": "not_running",
        }
        assert token not in result.stdout and token not in result.stderr
    finally:
        if worker is not None and worker.poll() is None:
            worker.kill()
            worker.wait()
        if api.poll() is None:
            api.send_signal(signal.SIGTERM)
            api.wait(timeout=10)


def test_up_worker_processes_a_durable_source_job(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    source = tmp_path / "sales.csv"
    today = datetime.now(UTC).date()
    rows = ["time,value,published"]
    for offset, value in enumerate((1, 2, 3), start=3):
        day = today - timedelta(days=offset)
        rows.append(f"{day.isoformat()},{value},{day.isoformat()}")
    source.write_text("\n".join(rows) + "\n")

    token = "test-private-token"
    env = {**os.environ, "FORECAST_ANYTHING_WORKSPACE_TOKEN": token}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "forecast_anything.cli",
            "up",
            "--db",
            str(tmp_path / "state.db"),
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"

    def request(path, *, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        http_request = Request(base_url + path, data=data, headers=headers)
        with urlopen(http_request, timeout=1) as response:
            return json.load(response)

    try:
        deadline = time.monotonic() + 10
        while True:
            try:
                if request("/health")["worker"] == "running":
                    break
            except (URLError, TimeoutError):
                # The supervisor listens before its API child can answer.
                assert process.poll() is None
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(0.05)

        registration = request(
            "/v1/sources",
            body={
                "source_id": "sales",
                "kind": "csv",
                "location": str(source),
                "refresh_seconds": 86400,
                "mapping": {
                    "event_time": "time",
                    "value": "value",
                    "available_at": "published",
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
        deadline = time.monotonic() + 10
        while True:
            job = request(f"/v1/jobs/{registration['job_id']}")
            if job["state"] in {"completed", "failed"}:
                break
            assert time.monotonic() < deadline, "worker left durable source job pending"
            time.sleep(0.05)
        assert job["state"] == "completed", job
        assert job["result"]["source_snapshot_ids"]
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=10)


def test_duplicate_worker_is_rejected_even_in_once_mode(tmp_path):
    from forecast_anything.local_services import worker_lock

    database = tmp_path / "state.db"
    with worker_lock(database):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "forecast_anything.cli",
                "worker",
                "--once",
                "--db",
                str(database),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "worker_already_running"


def test_up_on_occupied_port_does_not_start_worker(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "forecast_anything.cli",
                "up",
                "--db",
                str(tmp_path / "state.db"),
                "--port",
                str(sock.getsockname()[1]),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "port_in_use"
