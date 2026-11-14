import csv
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.frozen_splits import freeze_calendar, write_frozen_calendar
from benchmarks.leaderboard import (
    _assert_holdout_reserved,
    run_repeated_leaderboard,
)
from benchmarks.prepare import prepare_suite

MANIFEST = Path("tests/fixtures/benchmarks/manifest.yaml")


def test_repeated_runs_publish_stable_leaderboard_and_reference_table(tmp_path):
    prepared = tmp_path / "prepared"
    prepare_suite(MANIFEST, prepared)
    split_file = tmp_path / "phase0-splits.json"
    write_frozen_calendar(split_file, freeze_calendar(MANIFEST, prepared))

    result = run_repeated_leaderboard(
        MANIFEST,
        tmp_path / "leaderboard",
        ("baseline",),
        split_file=split_file,
        repetitions=2,
    )

    assert result["stability"]["status"] == "stable"
    assert len(result["stability"]["runs"]) == 2
    assert result["stability"]["holdout"] == {
        "status": "reserved_unscored",
        "score_rows": 0,
    }
    assert "latency_ms" in result["stability"]["ignored_measurements"]
    assert result["leaderboard"].exists()
    assert result["reference_models"].exists()
    assert result["stability_file"].exists()
    first_run = Path(result["stability"]["runs"][0]["report"]).parent
    second_run = Path(result["stability"]["runs"][1]["report"]).parent
    with gzip.open(first_run / "ledger.sqlite.gz", "rb") as stream:
        assert stream.read(16) == b"SQLite format 3\x00"
    assert (second_run / "ledger.sqlite").exists()

    with result["leaderboard"].open(newline="") as stream:
        scores = list(csv.DictReader(stream))
    holdout = [row for row in scores if row["split"] == "final"]
    assert holdout
    assert all(row["status"] == "reserved" and row["mae"] == "" for row in holdout)
    assert any(row["provider"] == "baseline" and row["mae"] for row in scores)

    with result["reference_models"].open(newline="") as stream:
        models = {row["model"]: row for row in csv.DictReader(stream)}
    assert models["seasonal_naive"]["status"] == "evaluated"
    assert models["timestral_28m"]["status"] == "not_requested"
    assert models["ets"]["status"] == "available"
    assert models["theta"]["status"] == "available"
    assert models["autoarima"]["status"] == "available"
    assert models["timestral_123m"]["status"] == "not_requested"


def test_holdout_validator_rejects_any_final_score_row(tmp_path):
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "report.json").write_text(
        json.dumps(
            {
                "score_splits": ["exploration", "selection"],
                "datasets": {
                    "activity": {
                        "providers": {
                            "baseline": {
                                "splits": {
                                    "final": {
                                        "status": "reserved",
                                        "origin_count": 0,
                                        "count": 0,
                                        "mae": None,
                                        "mase": None,
                                        "smape": None,
                                        "wql": None,
                                        "relative_mae": None,
                                    }
                                }
                            }
                        }
                    }
                },
            }
        )
    )
    with (run_directory / "origins.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "dataset",
                "provider",
                "split",
                "origin",
                "target_start",
                "target_end",
                "input_key",
                "status",
                "reason",
            ),
        )
        writer.writeheader()
        writer.writerow(
            {
                "dataset": "activity",
                "provider": "baseline",
                "split": "final",
                "origin": "2024-01-01T00:00:00Z",
                "target_start": "2024-01-02T00:00:00Z",
                "target_end": "2024-01-03T00:00:00Z",
                "input_key": "",
                "status": "reserved",
                "reason": "holdout_reserved_for_final_evaluation",
            }
        )
    with (run_directory / "origin_scores.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("dataset", "provider", "split", "origin", "mae"),
        )
        writer.writeheader()
        writer.writerow(
            {
                "dataset": "activity",
                "provider": "baseline",
                "split": "final",
                "origin": "2024-01-01T00:00:00Z",
                "mae": "0",
            }
        )

    with pytest.raises(RuntimeError, match="final holdout score rows"):
        _assert_holdout_reserved(run_directory)
