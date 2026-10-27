from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "e2e" / "serve_observatory.py"
SPEC = importlib.util.spec_from_file_location("serve_observatory", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_usability_csv_stays_forecastable_for_the_session(tmp_path):
    now = datetime(2026, 10, 27, 13, tzinfo=timezone.utc)

    path = MODULE.write_usability_fixture(tmp_path, now)

    rows = path.read_text().splitlines()
    dates = [
        datetime.fromisoformat(row.split(",")[0]).replace(tzinfo=timezone.utc)
        for row in rows[1:]
    ]
    assert rows[0] == "time,value"
    assert len(dates) == 3
    assert dates[-1].date() == now.date()
    assert dates[-1] <= now < dates[-1] + timedelta(days=1)
