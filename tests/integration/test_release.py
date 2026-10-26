"""Acceptance checks for the installable release artifact."""

from __future__ import annotations

import subprocess
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]


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
    assert report["version"] == "0.1.0", report
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
