"""Real installed entrypoint, point-in-time emissions and strict CSV boundary."""

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from forecast_anything.cli import configured_providers
from forecast_anything.connectors.csv import load_csv
from forecast_anything.contracts import DomainError, GraphSpec
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ["series_id", "event_time", "available_at", "revision", "value", "unit"]


def cli(*args):
    return subprocess.run(
        ["forecast-anything", *map(str, args)], capture_output=True, text=True
    )


def test_required_timestral_provider_registers_lazily_by_default(monkeypatch):
    monkeypatch.delenv("FORECAST_ANYTHING_TIMESTRAL_ENABLED", raising=False)
    assert set(configured_providers()) == {"seasonal_naive", "timestral"}


def test_required_timestral_provider_rejects_unpinned_configuration(monkeypatch):
    monkeypatch.setenv("FORECAST_ANYTHING_TIMESTRAL_ENABLED", "1")
    monkeypatch.setenv("FORECAST_ANYTHING_TIMESTRAL_REVISION", "weights-revision")
    with pytest.raises(DomainError, match="invalid_provider_configuration"):
        configured_providers()


def test_cli_exposes_run_command():
    result = cli("run", "--help")
    assert result.returncode == 0
    assert "--as-of" in result.stdout and "--db" in result.stdout
    assert "--primary-node-id" in result.stdout


def test_cli_preserves_legacy_baseline_emissions_and_refuses_new_baseline(tmp_path):
    graph = tmp_path / "legacy-baseline.json"
    legacy = json.loads((ROOT / "examples/minimal/graph.json").read_text())
    legacy["nodes"][1]["config"].update(
        provider="seasonal_naive", options={"period": 2}
    )
    graph.write_text(json.dumps(legacy))
    data = tmp_path / "data.csv"
    data.write_text(
        "series_id,event_time,available_at,revision,value,unit\n"
        "demand,2026-10-21T00:00:00Z,2026-10-21T00:00:00Z,1,10,kWh\n"
        "demand,2026-10-22T00:00:00Z,2026-10-22T00:00:00Z,1,20,kWh\n"
        "demand,2026-10-23T00:00:00Z,2026-10-23T00:00:00Z,1,30,kWh\n"
        "demand,2026-10-23T00:00:00Z,2026-10-25T00:00:00Z,2,99,kWh\n"
    )
    db = tmp_path / "runs.db"

    # Historical baseline evidence is created through the generic library runtime.
    # These values establish read compatibility, not current product acceptance.
    runtime = Runtime(
        Ledger(db),
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        {},
        lambda: datetime(2026, 10, 24, tzinfo=timezone.utc),
    )
    spec = GraphSpec.model_validate_json(graph.read_text())

    def run(origin):
        as_of = datetime.fromisoformat(origin).astimezone(timezone.utc)
        return runtime.run(
            spec,
            {"csv_observations": freeze(load_csv(data), as_of)},
            as_of,
            as_of.isoformat(),
        ).model_dump(mode="json")

    first = run("2026-10-24T00:00:00Z")
    assert first["state"] == "completed"
    assert first["actual_provider"] == {"forecast": "seasonal_naive"}
    assert first["results"]["forecast"]["point"] == [[20, 30, 20]]
    assert len(first["snapshot_ids"]) == 1
    assert run("2026-10-24T02:00:00+02:00") == first
    second = run("2026-10-25T00:00:00Z")
    assert second["run_id"] != first["run_id"]
    assert second["snapshot_ids"] != first["snapshot_ids"]
    assert second["results"]["forecast"]["point"] == [[20, 99, 20]]
    shown = cli("show", first["run_id"], "--db", db)
    assert shown.returncode == 0
    assert json.loads(shown.stdout) == first
    refused = cli(
        "run", graph, "--data", data, "--as-of", "2026-10-26T00:00:00Z", "--db", db
    )
    assert refused.returncode == 2
    assert json.loads(refused.stderr)["code"] == "required_forecast_provider"


@pytest.mark.parametrize(
    ("field", "missing_header"),
    [
        (field, missing_header)
        for field in FIELDS
        for missing_header in [False, True]
        if field != "value" or missing_header
    ],
)
def test_csv_missing_semantics(tmp_path, field, missing_header):
    from forecast_anything.connectors.csv import load_csv
    from forecast_anything.contracts import DomainError

    row = dict(
        zip(
            FIELDS,
            ["demand", "2026-10-23T00:00:00Z", "2026-10-23T00:00:00Z", "1", "1", "kWh"],
        )
    )
    names = [name for name in FIELDS if name != field] if missing_header else FIELDS
    row[field] = ""
    path = tmp_path / "bad.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        writer.writerow(row)
    with pytest.raises(DomainError):
        load_csv(path)


@pytest.mark.parametrize("replacement", ["NaN", "Infinity", "abc"])
def test_csv_rejects_invalid_values(tmp_path, replacement):
    from forecast_anything.connectors.csv import load_csv
    from forecast_anything.contracts import DomainError

    path = tmp_path / "bad.csv"
    path.write_text(
        ",".join(FIELDS)
        + "\ndemand,2026-10-23T00:00:00Z,2026-10-23T00:00:00Z,1,"
        + replacement
        + ",kWh\n"
    )
    with pytest.raises(DomainError):
        load_csv(path)


def test_cli_errors_and_failed_run(tmp_path):
    def library_cli(*arguments):
        import sys

        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/fixtures/library_cli.py"),
                *map(str, arguments),
            ],
            capture_output=True,
            text=True,
        )

    graph = tmp_path / "timestral.json"
    specification = json.loads((ROOT / "examples/minimal/graph.json").read_text())
    specification["nodes"][1]["config"]["provider"] = "seasonal_naive"
    specification["nodes"][1]["config"]["options"] = {"period": 1}
    graph.write_text(json.dumps(specification))
    data = tmp_path / "data.csv"
    data.write_text(
        ",".join(FIELDS) + "\ndemand,2026-10-23T00:00:00Z,2026-10-23T00:00:00Z,1,,kWh\n"
    )
    args = ("run", graph, "--data", data, "--db", tmp_path / "runs.db")
    invalid = library_cli(*args, "--as-of", "2026-10-24")
    assert invalid.returncode != 0
    assert json.loads(invalid.stderr)["code"] == "naive_timestamp"
    failed = library_cli(*args, "--as-of", "2026-10-24T00:00:00Z")
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["state"] == "failed"
    missing = cli("show", "absent", "--db", tmp_path / "runs.db")
    assert missing.returncode != 0
    assert json.loads(missing.stderr)["code"] == "not_found"


def test_cli_malformed_csv_header_is_structured_error(tmp_path):
    data = tmp_path / "malformed.csv"
    data.write_text('"series_id,event_time,available_at,revision,value,unit\n')
    result = cli(
        "run",
        ROOT / "examples/minimal/graph.json",
        "--data",
        data,
        "--as-of",
        "2026-10-24T00:00:00Z",
        "--db",
        tmp_path / "runs.db",
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert json.loads(result.stderr)["code"] == "invalid_csv"


def test_cli_requires_prepared_model_without_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty-cache"))
    result = cli(
        "run",
        ROOT / "examples/minimal/graph.json",
        "--data",
        ROOT / "examples/minimal/observations.csv",
        "--as-of",
        "2026-10-26T00:00:00Z",
        "--db",
        tmp_path / "missing-model.db",
    )
    assert result.returncode == 2
    assert json.loads(result.stderr)["code"] == "model_not_prepared"
    assert not result.stdout
