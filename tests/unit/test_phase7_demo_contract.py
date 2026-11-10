import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "examples" / "release-demo"


def test_release_demo_fixture_declares_only_synthetic_utc_observations():
    assumptions = json.loads((DEMO / "assumptions.json").read_text())
    with (DEMO / "observations.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert assumptions["synthetic"] is True
    assert assumptions["timezone"] == "UTC"
    assert assumptions["cadence"] == "daily"
    assert (
        assumptions["available_at_policy"]
        == "same_as_event_time_by_synthetic_assumption"
    )
    assert assumptions["unit"]
    assert len(rows) >= 32
    assert {"time", "value", "published"} <= rows[0].keys()
    assert rows[-1]["time"] == assumptions["initial_cutoff"]


def test_recorded_journey_has_full_mcp_worker_evidence_and_accuracy_limits():
    path = ROOT / "site" / "demo-data.json"
    raw = path.read_text()
    data = json.loads(raw)
    journey = data["journey"]

    assert journey["source"]["synthetic"] is True
    assert journey["source"]["snapshot_id"]
    fixture_bytes = (DEMO / "observations.csv").read_bytes()
    assert (
        journey["source"]["fixture_sha256"] == hashlib.sha256(fixture_bytes).hexdigest()
    )
    assert journey["source"]["observation_count"] >= 32
    assert journey["forecast"]["provider"] == "timestral"
    assert journey["forecast"]["provider_revision"]
    assert journey["forecast"]["baseline_provider"] == "seasonal_naive"
    assert journey["historical_comparison"]["origin_count"] >= 1
    assert journey["historical_comparison"]["interpretation_limit"]
    assert {
        part["partition"] for part in journey["historical_comparison"]["partitions"]
    } == {"exploration", "selection", "final"}
    assert journey["question"]["revision"] >= 1
    assert journey["question"]["recovered_after_mcp_reconnect"] is True
    assert "question/" in journey["question"]["exact_browser_link"]
    assert journey["worker_update"]["event_kind"] == "forecast_issued"
    assert journey["worker_update"]["run_id"]
    assert (
        journey["worker_update"]["source_update_state"]
        == "processed_by_independent_worker"
    )
    assert journey["worker_update"]["received_while_mcp_disconnected"] is True
    assert journey["worker_update"]["observation"]["value"] == 7
    assert journey["worker_update"]["quality"] in {"usable", "provisional"}
    if journey["worker_update"]["quality"] == "provisional":
        assert journey["worker_update"]["reason"]
        assert journey["worker_update"]["requalification_new_origins"] < 30
    assert journey["worker_update"]["webhook_state"] == "delivered"
    assert journey["timings"]["automation_seconds_to_first_forecast"] > 0
    assert journey["timings"]["automation_end_to_end_seconds"] > 0
    assert journey["timings"]["mcp_reconnect_recovery_seconds"] > 0
    assert "/Users/" not in raw
    assert "/private/tmp/" not in raw
    assert "phase-7-demo-test-secret" not in raw
    assert '"token"' not in raw
