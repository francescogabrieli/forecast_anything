"""Acceptance checks for the installable release artifact."""

from __future__ import annotations

import os
import subprocess
from importlib.metadata import version
from pathlib import Path
from runpy import run_path
from shutil import copy2, copytree
from tarfile import open as open_tar
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_source_distribution_excludes_local_work_materials(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE", "NOTICE", ".gitignore"):
        copy2(ROOT / name, project / name)
    for name in ("src", "examples/minimal", "contracts/v1"):
        copytree(ROOT / name, project / name)
    private_files = (
        ".local/recovery/.env.example",
        ".superpowers/sdd/plan/progress.md",
        ".codex/session.md",
        "work/private.txt",
        "outputs/run.json",
        "apps/console/node_modules/dependency/index.js",
        "apps/console/test-results/trace.zip",
        "apps/console/playwright-report/index.html",
        ".local/project-history/eve/apps/agent/package.json",
        ".local/project-history/eve/compose.agent.yaml",
    )
    for name in private_files:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("local work material")
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(dist)],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    with open_tar(next(dist.glob("*.tar.gz"))) as archive:
        names = {name.split("/", 1)[1] for name in archive.getnames()}
    assert not names.intersection(private_files)
    assert "src/forecast_anything/cli.py" in names
    assert "examples/minimal/graph.json" in names
    assert "contracts/v1/openapi.json" in names
    assert "LICENSE" in names


@pytest.mark.skipif(
    os.environ.get("FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED") != "1",
    reason="Real installed Timestral smoke requires explicit local weights approval and prepared cache",
)
def test_installed_release_has_passed_smoke(tmp_path: Path):
    dist = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    check_release = run_path(str(ROOT / "scripts" / "check_release.py"))[
        "check_release"
    ]

    report = check_release(dist)

    assert report["installed_outside_checkout"] is True, report
    assert report["minimal_example_passed"] is True, report
    assert report["model_prepared"] is True, report
    assert report["timestral_smoke_passed"] is True, report
    assert report["timestral_provider_revision"] == (
        "mistralai/Timestral-28M@49b26409ac87b5935539a5d8ffe7f397b720db47;"
        "code=a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff"
    ), report
    assert report["version"] == version("forecast-anything"), report
    assert report["schema_version"] == "1.0.0", report
    assert report["missing_files"] == [], report
    assert report["embedded_credentials"] == [], report
    assert report["model_weights"] == [], report
    assert report["passed"] is True, report


def test_release_flags_embedded_credentials_and_weights(tmp_path: Path):
    check_release = run_path(str(ROOT / "scripts" / "check_release.py"))[
        "check_release"
    ]
    dist = tmp_path / "dist"
    dist.mkdir()
    with ZipFile(dist / "forecast_anything-0.1.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr("forecast_anything/secrets/provider.txt", "sk-" + "a" * 48)
        wheel.writestr("forecast_anything/models/example.safetensors", b"weights")

    report = check_release(dist)

    assert report["passed"] is False
    assert report["embedded_credentials"] == ["forecast_anything/secrets/provider.txt"]
    assert report["model_weights"] == ["forecast_anything/models/example.safetensors"]


@pytest.mark.parametrize("artifact_only", [False, True])
def test_release_missing_weights_reports_preparation_without_running_forecast(
    tmp_path, artifact_only
):
    """Subprocess boundary double; not installed model acceptance."""
    namespace = run_path(str(ROOT / "scripts" / "check_release.py"))
    check_release = namespace["check_release"]
    dist = tmp_path / "dist"
    dist.mkdir()
    with ZipFile(dist / "forecast_anything-0.1.0-py3-none-any.whl", "w") as wheel:
        for name in namespace["REQUIRED"]:
            relative = name.removeprefix("forecast_anything/")
            source = (
                ROOT / relative
                if relative.startswith(("examples/", "contracts/v1/"))
                else ROOT / "src" / name
            )
            wheel.write(source, name)
        wheel.writestr("forecast_anything-0.1.0.dist-info/METADATA", "Version: 0.1.0\n")
        wheel.writestr("forecast_anything/LICENSE", "fixture")
        wheel.writestr("forecast_anything/NOTICE", "fixture")

    commands = []

    def run(command, cwd, env):
        import json

        commands.append(command)
        if "import forecast_anything, importlib.metadata, json; " in command[-1]:
            venv = Path(command[0]).parents[1]
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "path": str(venv / "lib" / "forecast_anything" / "__init__.py"),
                        "version": "0.1.0",
                    }
                ),
                "",
            )
        if command[-2:] == ["model", "status"]:
            return subprocess.CompletedProcess(
                command,
                1,
                json.dumps(
                    {
                        "status": "weights_missing",
                        "cached": False,
                        "ready": False,
                        "prepare_command": "forecast-anything model prepare",
                    }
                ),
                "",
            )
        if "run" in command or command[-2:] == ["model", "prepare"]:
            pytest.fail("missing weights must remain an explicit setup requirement")
        return subprocess.CompletedProcess(command, 0, "", "")

    check_release.__globals__["_run"] = run
    report = check_release(dist, artifact_only=artifact_only)
    if artifact_only:
        assert report["passed"] is True
        assert report["model_validation"] == "not_executed_artifact_only"
        assert report["timestral_smoke_passed"] is False
        assert report["minimal_example_passed"] is False
        assert not any(command[-2:] == ["model", "status"] for command in commands)
        return
    assert report["passed"] is False
    assert report["model_prepared"] is False
    assert any("forecast-anything model prepare" in error for error in report["errors"])
    assert any(command[-2:] == ["model", "status"] for command in commands)


def test_release_rejects_direct_dependency_in_metadata(tmp_path: Path):
    check_release = run_path(str(ROOT / "scripts" / "check_release.py"))[
        "check_release"
    ]
    with ZipFile(tmp_path / "forecast_anything-0.1.0-py3-none-any.whl", "w") as wheel:
        wheel.writestr(
            "forecast_anything-0.1.0.dist-info/METADATA",
            "Version: 0.1.0\n"
            'Requires-Dist: timestral @ git+https://example.invalid/model.git; extra == "timestral"\n',
        )
    report = check_release(tmp_path, artifact_only=True)
    assert not report["passed"]
    assert not report["installed_outside_checkout"]
    assert "wheel declares a direct URL dependency: timestral" in report["errors"]
