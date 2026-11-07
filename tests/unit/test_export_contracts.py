import json
import subprocess
import sys


def test_openapi_422_descriptions_are_stable_across_python_versions(tmp_path):
    subprocess.run(
        [sys.executable, "scripts/export_contracts.py", str(tmp_path)], check=True
    )
    openapi = json.loads((tmp_path / "openapi.json").read_text(encoding="utf-8"))
    descriptions = {
        operation["responses"]["422"]["description"]
        for path in openapi["paths"].values()
        for operation in path.values()
        if "422" in operation.get("responses", {})
    }

    assert descriptions == {"Unprocessable Content"}


def test_exports_public_backtest_contracts_without_private_raw_archive(tmp_path):
    subprocess.run(
        [sys.executable, "scripts/export_contracts.py", str(tmp_path)], check=True
    )
    schemas = json.loads((tmp_path / "schemas.json").read_text(encoding="utf-8"))
    assert {
        "ForecastSelection",
        "BacktestSettings",
        "BacktestReport",
        "OriginOutcome",
        "OriginPage",
        "PartitionScore",
        "QuestionView",
        "QuestionRevision",
        "QuestionReference",
        "OperationView",
        "OperationSubmitRequest",
        "SnapshotSummary",
        "SnapshotSeriesSummary",
        "ForecastPresentation",
        "BacktestPresentation",
        "BacktestSummary",
        "QuestionPresentation",
    } <= schemas.keys()
    assert "ObservationArchive" not in schemas
    assert "BacktestPlan" not in schemas
    assert "observations" not in schemas["BacktestReport"]["properties"]
