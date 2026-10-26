"""Inspect and smoke-test a wheel as an installed release, outside this checkout."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from email.parser import Parser
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "forecast_anything/cli.py",
    "forecast_anything/contracts.py",
    "forecast_anything/examples/minimal/graph.json",
    "forecast_anything/examples/minimal/observations.csv",
    "forecast_anything/contracts/v1/openapi.json",
    "forecast_anything/contracts/v1/schemas.json",
)
WEIGHT_SUFFIXES = frozenset(
    {".safetensors", ".pt", ".pth", ".ckpt", ".onnx", ".gguf", ".h5", ".hdf5"}
)
SECRET_NAME = re.compile(
    r"(^|/)(?:\.env(?:\.[^/]*)?|id_rsa|id_ed25519|[^/]*credential[^/]*|"
    r"[^/]*secret[^/]*|[^/]*private[_-]?key[^/]*)$|\.(?:pem|p12|pfx|key)$",
    re.IGNORECASE,
)
SECRET_VALUE = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    rb"(?:AKIA|ASIA)[A-Z0-9]{16}|"
    rb"(?:ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9]{30,}|"
    rb"sk-[A-Za-z0-9_-]{32,}"
)


def _run(
    command: list[str], cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)


def _outside(path: Path) -> bool:
    return not path.resolve().is_relative_to(ROOT.resolve())


def check_release(dist_dir: Path) -> dict:
    """Return a machine-readable report; never publish or mutate the checkout."""
    report = {
        "wheel": None,
        "version": None,
        "schema_version": None,
        "installed_outside_checkout": False,
        "minimal_example_passed": False,
        "included_files": [],
        "missing_files": [],
        "embedded_credentials": [],
        "model_weights": [],
        "errors": [],
        "passed": False,
    }
    wheels = sorted(Path(dist_dir).glob("forecast_anything-*.whl"))
    if len(wheels) != 1:
        report["errors"].append(
            f"expected exactly one forecast_anything wheel, found {len(wheels)}"
        )
        return report
    wheel = wheels[0].resolve()
    report["wheel"] = str(wheel)
    try:
        with ZipFile(wheel) as archive:
            names = set(archive.namelist())
            report["included_files"] = sorted(names)
            report["missing_files"] = [name for name in REQUIRED if name not in names]
            if not any(
                name.endswith("/LICENSE") or name == "LICENSE" for name in names
            ):
                report["missing_files"].append("LICENSE")
            if not any(name.endswith("/NOTICE") or name == "NOTICE" for name in names):
                report["missing_files"].append("NOTICE")
            for name in sorted(names):
                if name.endswith("/"):
                    continue
                if Path(name).suffix.lower() in WEIGHT_SUFFIXES:
                    report["model_weights"].append(name)
                if SECRET_NAME.search(name):
                    report["embedded_credentials"].append(name)
                elif archive.getinfo(
                    name
                ).file_size <= 2_000_000 and SECRET_VALUE.search(archive.read(name)):
                    report["embedded_credentials"].append(name)
            metadata = next(
                (name for name in names if name.endswith(".dist-info/METADATA")), None
            )
            if metadata:
                report["version"] = (
                    Parser()
                    .parsestr(archive.read(metadata).decode("utf-8"))
                    .get("Version")
                )
            else:
                report["errors"].append("wheel metadata missing")
            if "forecast_anything/contracts/v1/openapi.json" in names:
                schema = json.loads(
                    archive.read("forecast_anything/contracts/v1/openapi.json")
                )
                report["schema_version"] = schema.get("info", {}).get("version")
                if not schema.get("paths"):
                    report["errors"].append("OpenAPI schema has no paths")
            if (
                "forecast_anything/contracts/v1/schemas.json" in names
                and not json.loads(
                    archive.read("forecast_anything/contracts/v1/schemas.json")
                )
            ):
                report["errors"].append("contract schemas are empty")
    except (BadZipFile, ValueError, UnicodeError, OSError) as error:
        report["errors"].append(f"invalid wheel contents: {error}")
        return report

    if (
        report["embedded_credentials"]
        or report["model_weights"]
        or not report["version"]
    ):
        return report

    with tempfile.TemporaryDirectory(prefix="forecast-release-") as temporary:
        workspace = Path(temporary).resolve()
        if not _outside(workspace):
            report["errors"].append("temporary test workspace is inside checkout")
            return report
        env = os.environ.copy()
        for variable in ("PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
            env.pop(variable, None)
        venv = workspace / "venv"
        created = _run(
            ["uv", "venv", str(venv), "--python", sys.executable], workspace, env
        )
        if created.returncode:
            report["errors"].append(f"venv creation failed: {created.stderr.strip()}")
            return report
        python = venv / "bin" / "python"
        installed = _run(
            ["uv", "pip", "install", "--python", str(python), str(wheel)],
            workspace,
            env,
        )
        if installed.returncode:
            report["errors"].append(
                f"wheel installation failed: {installed.stderr.strip()}"
            )
            return report
        location = _run(
            [
                str(python),
                "-I",
                "-c",
                "import forecast_anything, importlib.metadata, json; "
                "print(json.dumps({'path': forecast_anything.__file__, "
                "'version': importlib.metadata.version('forecast-anything')}))",
            ],
            workspace,
            env,
        )
        if location.returncode:
            report["errors"].append(
                f"installed package import failed: {location.stderr.strip()}"
            )
            return report
        imported = json.loads(location.stdout)
        report["installed_outside_checkout"] = (
            _outside(Path(imported["path"]))
            and Path(imported["path"]).is_relative_to(venv)
            and imported["version"] == report["version"]
        )
        if not report["installed_outside_checkout"]:
            report["errors"].append(
                "import did not resolve to the wheel in the fresh venv"
            )
            return report

        required_example = (
            "forecast_anything/examples/minimal/graph.json",
            "forecast_anything/examples/minimal/observations.csv",
        )
        if all(name in report["included_files"] for name in required_example):
            with ZipFile(wheel) as archive:
                for name in required_example:
                    target = workspace / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(name))
            run = _run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "forecast_anything.cli",
                    "run",
                    str(workspace / required_example[0]),
                    "--data",
                    str(workspace / required_example[1]),
                    "--as-of",
                    "2026-10-24T00:00:00+00:00",
                    "--db",
                    str(workspace / "smoke.db"),
                ],
                workspace,
                env,
            )
            if run.returncode:
                report["errors"].append(f"minimal example failed: {run.stderr.strip()}")
            else:
                try:
                    result = json.loads(run.stdout)
                    forecast = result["results"]["forecast"]
                    report["minimal_example_passed"] = (
                        result["state"] == "completed"
                        and forecast["provider_id"] == "seasonal_naive"
                        and forecast["point"] == [[20.0, 30.0, 20.0]]
                        and forecast["quantiles"] is None
                        and forecast["paths"] is None
                    )
                except (KeyError, TypeError, ValueError):
                    report["errors"].append(
                        "minimal example emitted invalid JSON record"
                    )
        report["passed"] = (
            report["installed_outside_checkout"]
            and report["minimal_example_passed"]
            and report["schema_version"] == "1.0.0"
            and not report["missing_files"]
            and not report["embedded_credentials"]
            and not report["model_weights"]
            and not report["errors"]
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    report = check_release(args.dist)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
