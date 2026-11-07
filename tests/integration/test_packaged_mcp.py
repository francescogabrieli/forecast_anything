"""The wheel extra and executable work without any checkout imports."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile

import pytest

pytest.importorskip("mcp", reason="install the optional mcp extra")

from mcp_evidence_journey import evidence_journey
from mcp_processes import ISSUED, ROOT, LocalWorkspace, baseline_journey


def run(command, cwd, env):
    result = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, timeout=90
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_installed_wheel_mcp_baseline_outside_checkout(tmp_path):
    dist = tmp_path / "dist"
    env = os.environ.copy()
    for variable in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        env.pop(variable, None)
    run(["uv", "build", "--wheel", "--out-dir", str(dist)], ROOT, env)
    wheel = next(dist.glob("forecast_anything-*.whl"))
    inspector = run_path(str(ROOT / "scripts/check_release.py"))
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "forecast_anything/mcp_adapter/server.py" in names
        for name in names:
            assert not inspector["SECRET_NAME"].search(name), name
            assert Path(name).suffix.lower() not in inspector["WEIGHT_SUFFIXES"], name
            if not name.endswith("/"):
                assert not inspector["SECRET_VALUE"].search(archive.read(name)), name
    # Resolve the exact baseline + optional MCP set from uv.lock, never latest PyPI.
    requirements = tmp_path / "locked-mcp.txt"
    run(
        [
            "uv",
            "export",
            "--locked",
            "--extra",
            "mcp",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--format",
            "requirements-txt",
            "--output-file",
            str(requirements),
        ],
        ROOT,
        env,
    )
    with tempfile.TemporaryDirectory(prefix="forecast-installed-mcp-") as temporary:
        outside = Path(temporary).resolve()
        assert not outside.is_relative_to(ROOT)
        venv = outside / "venv"
        run(["uv", "venv", str(venv), "--python", sys.executable], outside, env)
        python = venv / "bin/python"
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "-r",
                str(requirements),
                f"{wheel}[mcp]",
            ],
            outside,
            env,
        )
        imported = json.loads(
            run(
                [
                    str(python),
                    "-I",
                    "-c",
                    "import forecast_anything, forecast_anything.mcp_adapter.server as server, mcp, importlib.metadata, json; print(json.dumps({'paths': [forecast_anything.__file__, server.__file__, mcp.__file__], 'mcp': importlib.metadata.version('mcp')}))",
                ],
                outside,
                env,
            )
        )
        assert imported["mcp"] == "2.3.0"
        for location in imported["paths"]:
            assert Path(location).resolve().is_relative_to(venv)
            assert not Path(location).resolve().is_relative_to(ROOT)
        executable = venv / "bin/forecast-anything"
        assert executable.is_file()
        with LocalWorkspace(
            outside / "workspace", python=python, executable=executable
        ) as workspace:
            issued = asyncio.run(
                asyncio.wait_for(baseline_journey(workspace), timeout=45)
            )
            assert issued["run"]["results"]["forecast"]["point"] == [[2.0]]

        with LocalWorkspace(
            outside / "evidence-workspace", python=python, executable=executable
        ) as workspace:
            report = asyncio.run(
                asyncio.wait_for(evidence_journey(workspace), timeout=60)
            )
            assert report["partitions"][2]["matched_count"] == 4

        with LocalWorkspace(
            outside / "liveness-workspace", python=python, executable=executable
        ) as workspace:
            workspace.wait_for_worker()
            workspace.crash_worker()
            stale_time = datetime.fromisoformat(ISSUED) + timedelta(seconds=11)
            workspace.set_clock(stale_time.isoformat())
            assert workspace.get("/health")["worker"] == "stale"
            workspace.start_worker()
            workspace.wait_for_worker()
            assert workspace.get("/health")["worker"] == "running"
