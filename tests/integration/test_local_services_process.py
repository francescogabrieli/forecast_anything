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
