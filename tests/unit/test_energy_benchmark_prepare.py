import csv
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.prepare import _energy


def test_energy_recipe_reads_the_predeclared_meter_column(tmp_path):
    raw = tmp_path / "energy.csv"
    with raw.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "Date",
                "Time",
                "Global_active_power",
                "Global_reactive_power",
            ),
            delimiter=";",
        )
        writer.writeheader()
        for minute in range(60):
            writer.writerow(
                {
                    "Date": "01/01/2007",
                    "Time": f"00:{minute:02d}:00",
                    "Global_active_power": "1.0",
                    "Global_reactive_power": "2.0",
                }
            )

    values, quality = _energy(
        raw,
        {"source": {"format": "csv"}, "value_column": "Global_reactive_power"},
        (datetime(2007, 1, 1, tzinfo=UTC),),
    )

    assert values == [2.0]
    assert quality["quality"][0]["complete"]
