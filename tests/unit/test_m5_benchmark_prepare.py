import csv
import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.prepare import prepare_suite


def _m5_fixture(tmp_path):
    bundle = tmp_path / "m5"
    bundle.mkdir()
    dates = [date(2020, 1, 1) + timedelta(days=index) for index in range(4)]

    with (bundle / "calendar.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("date",))
        writer.writerows((day.isoformat(),) for day in dates)

    with (bundle / "sales_train_validation.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "item_id",
                "dept_id",
                "cat_id",
                "store_id",
                "state_id",
                "d_1",
                "d_2",
                "d_3",
                "d_4",
            )
        )
        writer.writerows(
            (
                ("item_1", "FOODS_1", "FOODS", "CA_1", "CA", 1, 2, 0, 3),
                ("item_2", "FOODS_1", "FOODS", "CA_1", "CA", 10, 0, 5, 2),
                ("item_3", "HOUSEHOLD_1", "HOUSEHOLD", "TX_1", "TX", 7, 4, 2, 0),
            )
        )

    # These files are checksum-verified but must never be parsed into observations.
    for name in (
        "sales_train_evaluation.csv",
        "sales_test_validation.csv",
        "sales_test_evaluation.csv",
        "sell_prices.csv",
    ):
        (bundle / name).write_text("this file is deliberately not a usable CSV\n")

    files = {}
    for path in sorted(bundle.glob("*.csv")):
        content = path.read_bytes()
        files[path.name] = {
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "source": f"https://drive.google.com/file/d/{path.stem}/view",
        }
    (bundle / "source-checksums.json").write_text(
        json.dumps(
            {
                "source_repository": "https://github.com/Mcompetitions/M5-methods#readme",
                "source_folder": "https://drive.google.com/drive/folders/official-m5",
                "files": files,
            }
        )
    )

    source_files = {
        name: {
            "bytes": entry["bytes"],
            "sha256": entry["sha256"],
            "source": entry["source"],
        }
        for name, entry in files.items()
    }
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "datasets": {
                    "m5_retail": {
                        "source": {
                            "kind": "real_observations",
                            "format": "m5_official_csv_bundle",
                            "source_repository": "https://github.com/Mcompetitions/M5-methods#readme",
                            "source_folder": "https://drive.google.com/drive/folders/official-m5",
                            "directory": "m5",
                            "checksums_file": "m5/source-checksums.json",
                            "files": source_files,
                        },
                        "series_id": "m5:all_stores_all_items",
                        "unit": "items",
                        "frequency": "1d",
                        "horizon": 2,
                        "period": 7,
                        "context": 2,
                        "origin_stride": 1,
                        "expected_source_rows": 3,
                        "recipe": "m5_retail",
                        "assumed_available_at": "period_end_UTC",
                        "selection_rule": "All item-store rows, aggregated by day without score-based filtering.",
                    }
                },
            }
        )
    )
    return manifest


def test_m5_recipe_aggregates_training_sales_and_uses_only_training_and_calendar(
    tmp_path,
):
    manifest = _m5_fixture(tmp_path)

    prepared = prepare_suite(manifest, tmp_path / "prepared")

    rows = list(csv.DictReader(prepared["m5_retail"].open(newline="")))
    assert [float(row["value"]) for row in rows] == [18.0, 6.0, 7.0, 5.0]
    assert [row["event_time"] for row in rows] == [
        "2020-01-02T00:00:00+00:00",
        "2020-01-03T00:00:00+00:00",
        "2020-01-04T00:00:00+00:00",
        "2020-01-05T00:00:00+00:00",
    ]

    metadata = json.loads((tmp_path / "prepared" / "preparation.json").read_text())
    coverage = metadata["datasets"]["m5_retail"]["coverage"]
    assert coverage["source_series_rows"] == 3
    assert coverage["source_files_used"] == [
        "calendar.csv",
        "sales_train_validation.csv",
    ]
    assert coverage["source_files_verified"] == sorted(
        (
            "calendar.csv",
            "sales_train_validation.csv",
            "sales_train_evaluation.csv",
            "sales_test_validation.csv",
            "sales_test_evaluation.csv",
            "sell_prices.csv",
        )
    )


def test_m5_verifies_checksums_for_unused_test_files(tmp_path):
    manifest = _m5_fixture(tmp_path)
    (tmp_path / "m5" / "sales_test_validation.csv").write_text("tampered\n")

    with pytest.raises(
        ValueError, match=r"M5 source size mismatch: sales_test_validation\.csv"
    ):
        prepare_suite(manifest, tmp_path / "prepared")
