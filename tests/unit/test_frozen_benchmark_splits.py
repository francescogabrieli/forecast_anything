import csv
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.frozen_splits import (
    dataset_origins,
    freeze_calendar,
    validate_frozen_calendar,
    write_frozen_calendar,
)
from benchmarks.prepare import prepare_suite
from forecast_anything.evaluation.splits import build_splits

MANIFEST = Path("tests/fixtures/benchmarks/manifest.yaml")


def test_build_splits_supports_stride_one_and_keeps_horizon_default():
    timestamps = tuple(
        datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(32)
    )

    mobile = build_splits(timestamps, horizon=3, stride=1)
    non_overlapping = build_splits(timestamps, horizon=3)

    mobile_origins = mobile.origins_for("exploration", timestamps)
    non_overlapping_origins = non_overlapping.origins_for("exploration", timestamps)
    assert mobile.stride == 1
    assert mobile_origins[1] - mobile_origins[0] == timedelta(days=1)
    assert len(mobile_origins) > len(non_overlapping_origins)
    assert non_overlapping.stride == 3


def test_previously_evaluated_final_origins_are_removed_from_frozen_holdout():
    timestamps = tuple(
        datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(40)
    )
    split = build_splits(timestamps, horizon=2, stride=1)

    origins = dataset_origins(
        split, timestamps, {"final_origin_policy": "previously_evaluated"}
    )

    assert origins["exploration"]
    assert origins["selection"]
    assert origins["final"] == ()


def test_fresh_final_window_freezes_explicit_boundaries_and_origins(tmp_path):
    timestamps = tuple(
        datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(80)
    )
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "datasets": {
                    "activity": {
                        "horizon": 3,
                        "origin_stride": 1,
                        "final_origin_policy": "fresh_window",
                        "split_bounds": {
                            "exploration_end": timestamps[29].isoformat(),
                            "selection_end": timestamps[49].isoformat(),
                            "final_start": timestamps[50].isoformat(),
                            "final_end": timestamps[64].isoformat(),
                        },
                    }
                },
            }
        )
    )
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    with (prepared / "activity.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("event_time",))
        writer.writeheader()
        writer.writerows({"event_time": value.isoformat()} for value in timestamps)

    frozen = freeze_calendar(manifest, prepared)

    dataset = frozen["datasets"]["activity"]
    assert dataset["exploration_end"] == timestamps[29].isoformat()
    assert dataset["selection_end"] == timestamps[49].isoformat()
    assert dataset["final_start"] == timestamps[50].isoformat()
    assert dataset["final_end"] == timestamps[64].isoformat()
    assert dataset["origin_count"]["final"] == 13


def test_fresh_final_windows_reject_any_historically_scored_target_timestamp():
    timestamps = tuple(
        datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(40)
    )
    split = build_splits(
        timestamps,
        horizon=3,
        stride=1,
        exploration_end=timestamps[19],
        selection_end=timestamps[24],
        final_start=timestamps[25],
        final_end=timestamps[39],
    )

    with pytest.raises(ValueError, match="reuses historically scored target"):
        dataset_origins(
            split,
            timestamps,
            {"final_origin_policy": "fresh_window", "series_id": "web:one"},
            historical_target_timestamps={timestamps[30]},
        )


def test_historical_target_guard_is_scoped_to_the_series_id():
    timestamps = tuple(
        datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(40)
    )
    split = build_splits(
        timestamps,
        horizon=3,
        stride=1,
        exploration_end=timestamps[19],
        selection_end=timestamps[24],
        final_start=timestamps[25],
        final_end=timestamps[39],
    )

    origins = dataset_origins(
        split,
        timestamps,
        {"final_origin_policy": "fresh_window", "series_id": "web:one"},
        historical_target_timestamps=set(),
    )

    assert origins["final"]


def test_freeze_calendar_loads_exact_historical_targets_by_series_id(tmp_path):
    timestamps = tuple(
        datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index) for index in range(40)
    )
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "historical_targets_file": "historical_targets.json",
                "datasets": {
                    "activity": {
                        "series_id": "web:one",
                        "horizon": 3,
                        "origin_stride": 1,
                        "final_origin_policy": "fresh_window",
                        "split_bounds": {
                            "exploration_end": timestamps[19].isoformat(),
                            "selection_end": timestamps[24].isoformat(),
                            "final_start": timestamps[25].isoformat(),
                            "final_end": timestamps[39].isoformat(),
                        },
                    }
                },
            }
        )
    )
    (tmp_path / "historical_targets.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "series": {
                    "web:one": {"target_timestamps": [timestamps[30].isoformat()]},
                    "web:other": {"target_timestamps": [timestamps[31].isoformat()]},
                },
            }
        )
    )
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    with (prepared / "activity.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("event_time",))
        writer.writeheader()
        writer.writerows({"event_time": value.isoformat()} for value in timestamps)

    with pytest.raises(ValueError, match="reuses historically scored target"):
        freeze_calendar(manifest, prepared)


def test_m4_daily_recipe_keeps_official_test_values_and_start_timestamp(tmp_path):
    import hashlib
    import json

    from benchmarks.prepare import prepare_suite

    fixture = tmp_path / "m4-fixture"
    fixture.mkdir()
    sources = {
        "info": (
            "M4-info.csv",
            "M4id,category,Frequency,Horizon,SP,StartingDate\nD1,Macro,1,2,Daily,01-01-20 12:00\n",
        ),
        "train": ("Daily-train.csv", "V1,V2,V3,V4\nD1,1,2,3\n"),
        "test": ("Daily-test.csv", "V1,V2,V3\nD1,4,5\n"),
    }
    file_config = {}
    for key, (filename, content) in sources.items():
        path = fixture / filename
        path.write_text(content)
        file_config[key] = {
            "path": filename,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    manifest = fixture / "manifest.yaml"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "datasets": {
                    "m4_daily_d1": {
                        "source": {"files": file_config},
                        "series_id": "D1",
                        "unit": "value",
                        "frequency": "1d",
                        "horizon": 2,
                        "expected_category": "Macro",
                        "period": 1,
                        "recipe": "m4_daily",
                        "assumed_available_at": "period_end_UTC",
                    }
                },
            }
        )
    )

    prepared = prepare_suite(manifest, tmp_path / "prepared")["m4_daily_d1"]
    rows = list(csv.DictReader(prepared.open(newline="")))
    metadata = json.loads((tmp_path / "prepared" / "preparation.json").read_text())

    assert [row["value"] for row in rows] == ["1.0", "2.0", "3.0", "4.0", "5.0"]
    assert rows[0]["event_time"] == "2020-01-01T12:00:00+00:00"
    assert metadata["datasets"]["m4_daily_d1"]["coverage"]["train_rows"] == 3
    assert metadata["datasets"]["m4_daily_d1"]["coverage"]["official_test_rows"] == 2


def test_frozen_calendar_hashes_and_validation_reject_tampering(tmp_path):
    prepare_suite(MANIFEST, tmp_path / "data")
    frozen = freeze_calendar(MANIFEST, tmp_path / "data")
    destination = tmp_path / "frozen.json"
    write_frozen_calendar(destination, frozen)

    assert frozen["split_sha256"]
    assert frozen["datasets"]["activity"]["calendar_sha256"]
    assert frozen["datasets"]["activity"]["origin_sha256"]["final"]
    assert validate_frozen_calendar(destination, MANIFEST, tmp_path / "data") == frozen

    tampered = json.loads(destination.read_text())
    tampered["datasets"]["activity"]["origin_sha256"]["final"] = "0" * 64
    write_frozen_calendar(destination, tampered)
    with pytest.raises(ValueError, match="frozen split mismatch"):
        validate_frozen_calendar(destination, MANIFEST, tmp_path / "data")
