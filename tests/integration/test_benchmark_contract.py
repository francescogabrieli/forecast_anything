"""Cross-domain recipes and frozen, complete-window benchmark evidence."""

import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.prepare import prepare_suite
from benchmarks.run import run_suite

MANIFEST = Path("tests/fixtures/benchmarks/manifest.yaml")


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def test_same_contract_three_domains(tmp_path):
    prepared = prepare_suite(MANIFEST, tmp_path / "data")
    assert set(prepared) == {"retail", "energy", "activity"}
    for path in prepared.values():
        rows = read_csv(path)
        assert len(rows) == 32
        assert set(rows[0]) == {
            "series_id",
            "event_time",
            "available_at",
            "revision",
            "value",
            "unit",
        }
    report_path = run_suite(MANIFEST, tmp_path / "run", ("baseline",))
    report = json.loads(report_path.read_text())
    assert report["status"] == "baseline_only"
    assert report["model_comparison"]["status"] == "not_requested"
    assert set(report["datasets"]) == {"retail", "energy", "activity"}
    for dataset in report["datasets"].values():
        baseline = dataset["providers"]["baseline"]
        assert baseline["status"] == "evaluated"
        assert baseline["splits"]["final"]["origin_count"] == 4
        assert baseline["splits"]["final"]["mae"] == 2.0
    assert (tmp_path / "run" / "environment.json").exists()
    assert (tmp_path / "run" / "origins.csv").exists()


def test_returned_goods_and_missing_meter_reading(tmp_path):
    prepared = prepare_suite(MANIFEST, tmp_path)
    retail = read_csv(prepared["retail"])
    assert float(retail[1]["value"]) == 11
    returns = read_csv(tmp_path / "retail.returns.csv")
    assert float(returns[1]["value"]) == 5
    energy = read_csv(prepared["energy"])
    assert energy[7]["value"] == ""
    assert float(energy[8]["value"]) == 9
    quality = json.loads((tmp_path / "energy.quality.json").read_text())
    assert quality[7]["valid_samples"] == 59
    assert quality[7]["expected_samples"] == 60


def test_no_vintage_claim_without_vintages(tmp_path):
    run_suite(MANIFEST, tmp_path, ("baseline",))
    assumptions = json.loads((tmp_path / "assumptions.json").read_text())
    for entry in assumptions["datasets"].values():
        assert entry["vintage_status"] == "assumed_not_observed"
        assert entry["assumed_available_at"] == "period_end_UTC"
    metadata = json.loads((tmp_path / "data" / "preparation.json").read_text())
    actual = hashlib.sha256(MANIFEST.with_name("retail.csv").read_bytes()).hexdigest()
    assert metadata["datasets"]["retail"]["download_sha256"] == actual


def test_synthetic_deliveries_are_labelled(tmp_path):
    report = json.loads(run_suite(MANIFEST, tmp_path, ("baseline",)).read_text())
    assert report["scenarios"][0]["kind"] == "synthetic_scenario"
    assert report["scenarios"][0]["included_in_scores"] is False
    assert "synthetic_deliveries" not in report["datasets"]


def test_residuals_exclude_final_and_incomplete_windows(tmp_path):
    run_suite(MANIFEST, tmp_path, ("baseline",))
    panels = [
        json.loads(line)
        for line in (tmp_path / "residuals.baseline.jsonl").read_text().splitlines()
    ]
    assert panels
    assert all(p["split"] in {"exploration", "selection"} for p in panels)
    first = next(p for p in panels if p["dataset"] == "activity")
    assert first["origin"] == "2020-01-06T00:00:00+00:00"
    assert first["errors"] == [[2.0, 2.0]]
    assert first["horizon"] == 2
    assert first["series_ids"] == ["activity"]
    assert first["available_at"] == "2020-01-08T00:00:00+00:00"
    assert first["availability_basis"] == "assumed_not_observed"
    assert first["snapshot_id"]
    origins = read_csv(tmp_path / "origins.csv")
    assert any(
        row["split"] == "final" and row["origin"] == "2020-01-25T00:00:00+00:00"
        for row in origins
    )
    assert any(
        row["dataset"] == "energy" and row["reason"] == "incomplete_targets"
        for row in origins
    )
    for panel in panels:
        assert datetime.fromisoformat(
            panel["target_timestamps"][-1]
        ) <= datetime.fromisoformat(panel["available_at"])


def test_model_gate_does_not_require_or_load_timestral(tmp_path, monkeypatch):
    monkeypatch.delenv("FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED", raising=False)
    report = json.loads(
        run_suite(MANIFEST, tmp_path, ("baseline", "timestral")).read_text()
    )
    assert report["status"] == "pending_model_comparison"
    for dataset in report["datasets"].values():
        assert dataset["providers"]["timestral"]["status"] == "pending_license"
        assert (
            dataset["providers"]["baseline"]["splits"]["selection"]["origin_count"] > 0
        )


def test_approved_timestral_comparison_uses_same_final_origins(tmp_path, monkeypatch):
    from forecast_anything.contracts import Capabilities
    from forecast_anything.providers.baseline import SeasonalNaiveProvider

    class FixtureTimestralProvider:
        def __init__(self, checkpoint, revision, code_revision):
            self.delegate = SeasonalNaiveProvider(period=1)
            self.revision = f"{checkpoint}@{revision};code={code_revision}"

        def capabilities(self):
            return Capabilities(
                provider_id="timestral",
                provider_revision=self.revision,
                representations=("point",),
                supports_known_future=True,
            )

        def forecast(self, request):
            result = self.delegate.forecast(request)
            return result.model_copy(
                update={"provider_id": "timestral", "provider_revision": self.revision}
            )

    monkeypatch.setenv("FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED", "1")
    monkeypatch.setattr(
        "benchmarks.run.TimestralProvider", FixtureTimestralProvider, raising=False
    )
    report = json.loads(
        run_suite(MANIFEST, tmp_path, ("baseline", "timestral")).read_text()
    )

    assert report["status"] == "evaluated"
    assert report["model_comparison"]["status"] == "evaluated"
    for dataset in report["datasets"].values():
        baseline = dataset["providers"]["baseline"]
        timestral = dataset["providers"]["timestral"]
        assert timestral["status"] == "evaluated"
        baseline_final = baseline["splits"]["final"]
        timestral_final = timestral["splits"]["final"]
        assert timestral_final["origin_count"] == baseline_final["origin_count"] == 4
        assert timestral_final["matched_origin_count"] == 4
        assert timestral_final["relative_mae"] is not None
        assert timestral["provider_revision"].startswith("mistralai/Timestral-28M@")


def test_prepared_input_tamper_is_rejected(tmp_path):
    prepare_suite(MANIFEST, tmp_path / "data")
    (tmp_path / "data" / "activity.csv").write_text("tampered")
    with pytest.raises(ValueError, match="prepared checksum"):
        run_suite(MANIFEST, tmp_path, ("baseline",))


def test_download_checksum_pin_rejects_changed_bytes(tmp_path):
    specification = json.loads(MANIFEST.read_text())
    for config in specification["datasets"].values():
        config["source"]["path"] = str(
            MANIFEST.parent.resolve() / config["source"]["path"]
        )
    specification["datasets"]["retail"]["source"]["sha256"] = "0" * 64
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(json.dumps(specification))
    with pytest.raises(ValueError, match="download checksum mismatch: retail"):
        prepare_suite(manifest, tmp_path / "data")


def test_final_values_never_enter_exploration_or_selection_residuals(tmp_path):
    import shutil

    fixture = tmp_path / "fixture"
    shutil.copytree(MANIFEST.parent, fixture)
    manifest = fixture / "manifest.yaml"
    run_suite(manifest, tmp_path / "before", ("baseline",))
    activity = fixture / "activity.csv"
    rows = read_csv(activity)
    for row in rows[24:]:
        row["views"] = "999999"
    with activity.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("timestamp", "views"))
        writer.writeheader()
        writer.writerows(rows)
    run_suite(manifest, tmp_path / "after", ("baseline",))
    panels = []
    for directory in ("before", "after"):
        panels.append(
            [
                (p["origin"], p["errors"], p["snapshot_id"])
                for line in (tmp_path / directory / "residuals.baseline.jsonl")
                .read_text()
                .splitlines()
                if (p := json.loads(line))["dataset"] == "activity"
            ]
        )
    assert panels[0] == panels[1]
    before = json.loads((tmp_path / "before" / "report.json").read_text())
    after = json.loads((tmp_path / "after" / "report.json").read_text())
    assert (
        before["datasets"]["activity"]["providers"]["baseline"]["splits"]["final"][
            "mae"
        ]
        != after["datasets"]["activity"]["providers"]["baseline"]["splits"]["final"][
            "mae"
        ]
    )


def test_official_xlsx_recipe_reads_shared_strings_and_excel_dates(tmp_path):
    import io
    from zipfile import ZipFile

    specification = json.loads(MANIFEST.read_text())
    for config in specification["datasets"].values():
        config["source"]["path"] = str(
            MANIFEST.parent.resolve() / config["source"]["path"]
        )
    workbook = io.BytesIO()
    namespace = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            f"<sst {namespace}><si><t>Invoice</t></si><si><t>Quantity</t></si><si><t>InvoiceDate</t></si><si><t>Creturn</t></si></sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet {namespace}><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row><row><c r="A2"><v>1</v></c><c r="B2"><v>12</v></c><c r="C2"><v>43831</v></c></row><row><c r="A3" t="s"><v>3</v></c><c r="B3"><v>-4</v></c><c r="C3"><v>43831.5</v></c></row></sheetData></worksheet>',
        )
    raw = tmp_path / "retail.zip"
    with ZipFile(raw, "w") as archive:
        archive.writestr("online_retail_II.xlsx", workbook.getvalue())
    specification["datasets"]["retail"]["source"].update(
        path=str(raw), format="zip_xlsx"
    )
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(json.dumps(specification))
    prepared = prepare_suite(manifest, tmp_path / "data")
    assert float(read_csv(prepared["retail"])[0]["value"]) == 12.0
    assert float(read_csv(tmp_path / "data" / "retail.returns.csv")[0]["value"]) == 4.0


def test_download_cache_is_bound_to_source_url(tmp_path, monkeypatch):
    import io

    specification = json.loads(MANIFEST.read_text())
    config = specification["datasets"]["activity"]
    config["source"].pop("path")
    config["source"].update(url="https://example.invalid/one", format="json")
    specification["datasets"] = {"activity": config}
    manifest = tmp_path / "manifest.yaml"

    def response(request, timeout):
        value = 1 if request.full_url.endswith("/one") else 9
        return io.BytesIO(
            json.dumps(
                {"items": [{"timestamp": "2020010100", "views": value}]}
            ).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", response)
    manifest.write_text(json.dumps(specification))
    prepared = prepare_suite(manifest, tmp_path / "data")
    assert float(read_csv(prepared["activity"])[0]["value"]) == 1
    config["source"]["url"] = "https://example.invalid/two"
    manifest.write_text(json.dumps(specification))
    prepared = prepare_suite(manifest, tmp_path / "data")
    assert float(read_csv(prepared["activity"])[0]["value"]) == 9


def test_replay_preserves_issued_residuals_and_origin_assignments(tmp_path):
    run_suite(MANIFEST, tmp_path, ("baseline",))
    first = {
        name: (tmp_path / name).read_bytes()
        for name in ("origins.csv", "frozen_calendar.json", "residuals.baseline.jsonl")
    }
    run_suite(MANIFEST, tmp_path, ("baseline",))
    assert all((tmp_path / name).read_bytes() == value for name, value in first.items())


@pytest.mark.parametrize("providers", [(), ("timestral",)])
def test_missing_baseline_is_rejected_before_preparation(tmp_path, providers):
    from forecast_anything.contracts import DomainError

    output = tmp_path / "uncreated"
    with pytest.raises(DomainError) as raised:
        run_suite(MANIFEST, output, providers)
    assert raised.value.model_dump() == {
        "code": "baseline_required",
        "details": {"providers": list(providers)},
    }
    assert not output.exists()


def test_cli_reports_structured_error_without_baseline(tmp_path):
    import subprocess

    output = tmp_path / "uncreated"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.run",
            "--manifest",
            str(MANIFEST),
            "--output",
            str(output),
            "--providers",
            "timestral",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 2
    assert completed.stdout == ""
    assert json.loads(completed.stderr) == {
        "code": "baseline_required",
        "details": {"providers": ["timestral"]},
    }
    assert not output.exists()


def test_energy_rejects_sixty_timestamps_with_a_shifted_minute_slot(tmp_path):
    source = tmp_path / "energy.csv"
    source.write_text(
        MANIFEST.with_name("energy.csv")
        .read_text()
        .replace("01/01/2020;00:00:00;1", "01/01/2020;00:00:30;1", 1)
    )
    specification = json.loads(MANIFEST.read_text())
    config = specification["datasets"]["energy"]
    config["source"]["path"] = str(source)
    specification["datasets"] = {"energy": config}
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(json.dumps(specification))
    with pytest.raises(ValueError, match="misaligned meter minute"):
        prepare_suite(manifest, tmp_path / "data")
