import os
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


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
            except URLError:
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
    import json

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
        assert json.loads(result.stdout) == {"api": "available", "worker": "unknown"}
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
