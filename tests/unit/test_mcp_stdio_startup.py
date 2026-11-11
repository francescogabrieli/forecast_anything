"""MCP command-line setup and stdio transport."""

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest
from mcp_tool_fixtures import NAMES

ROOT = Path(__file__).resolve().parents[2]


def test_cli_mcp_missing_extra_is_safe_and_baseline_does_not_import_sdk(tmp_path):
    blocker = tmp_path / "sitecustomize.py"
    blocker.write_text(
        "import sys\nclass Block:\n def find_spec(self, fullname, path=None, target=None):\n  if fullname == 'mcp' or fullname.startswith('mcp.'):\n   raise ModuleNotFoundError('blocked optional mcp', name='mcp')\nsys.meta_path.insert(0, Block())\n"
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT / "src")]),
    }
    baseline = subprocess.run(
        [sys.executable, "-m", "forecast_anything.cli", "run", "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert baseline.returncode == 0
    assert "--as-of" in baseline.stdout
    result = subprocess.run(
        [sys.executable, "-m", "forecast_anything.cli", "mcp"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "forecast-anything[mcp]" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_invalid_configuration_never_writes_to_protocol_stdout():
    pytest.importorskip("mcp")
    env = {
        **os.environ,
        "FORECAST_ANYTHING_WORKSPACE_TOKEN": "",
        "FORECAST_ANYTHING_MCP_API_URL": "https://private:SECRET-TOKEN@example.com/path",
    }
    result = subprocess.run(
        [sys.executable, "-m", "forecast_anything.cli", "mcp"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"ok": False, "code": "configuration_error"}
    assert "SECRET-TOKEN" not in result.stderr


def test_stdio_catalog_stdout_contains_only_jsonrpc_and_no_private_config():
    pytest.importorskip("mcp")
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "clientInfo": {"name": "wire-test", "version": "1"},
                "capabilities": {},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_job",
                "arguments": {"job_id": {"secret": "/private/SECRET-TOKEN"}},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_job", "arguments": "/private/SECRET-TOKEN"},
        },
    ]
    process = subprocess.Popen(
        [sys.executable, "-m", "forecast_anything.cli", "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "FORECAST_ANYTHING_WORKSPACE_TOKEN": "SECRET-TOKEN"},
    )
    output = bytearray()
    try:
        process.stdin.write(
            "".join(json.dumps(message) + "\n" for message in messages).encode()
        )
        process.stdin.flush()
        deadline = time.monotonic() + 10
        while output.count(b"\n") < 4:
            ready, _, _ = select.select(
                [process.stdout], [], [], max(0, deadline - time.monotonic())
            )
            assert ready, "MCP subprocess response timed out"
            chunk = os.read(process.stdout.fileno(), 65536)
            assert chunk, "MCP subprocess exited before all replies"
            output.extend(chunk)
        process.stdin.close()
        process.stdin = None
        tail, stderr = process.communicate(timeout=5)
        output.extend(tail)
        assert process.returncode == 0, stderr.decode()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    replies = {item["id"]: item for item in map(json.loads, output.splitlines())}
    assert set(replies) == {1, 2, 3, 4}
    assert set(item["name"] for item in replies[2]["result"]["tools"]) == NAMES
    assert replies[3]["result"]["isError"] is True
    assert replies[4]["error"]["code"] == -32602
    assert b"SECRET-TOKEN" not in output + stderr
    assert b"Traceback" not in stderr
