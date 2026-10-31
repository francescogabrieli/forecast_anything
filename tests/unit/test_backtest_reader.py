"""Revision capture retains raw history and refuses overflow before interpreting rows."""

from datetime import datetime, timezone

import pytest

from forecast_anything.contracts import DomainError, Observation, SourceSpec
from forecast_anything.sources import profiling
from forecast_anything.sources.catalog import source_revision
from forecast_anything.temporal import freeze

MAPPING = {
    "series_id": {"constant": "sales"},
    "event_time": "date",
    "available_at": "published",
    "revision": "edition",
    "value": "amount",
    "unit": {"constant": "count"},
    "frequency": {"constant": "D"},
    "timezone": {"constant": "Europe/Rome"},
    "calendar": {"constant": "gregorian"},
    "missing_values": {"constant": [""]},
}


def source(tmp_path, text):
    path = tmp_path / "private.csv"
    path.write_text("date,published,edition,amount\n" + text)
    return SourceSpec(
        source_id="sales",
        kind="csv",
        location=str(path),
        mapping=MAPPING,
        refresh_seconds=60,
    )


def test_reader_retains_revisions_and_ingest_bytes_remain_unchanged(tmp_path):
    assert hasattr(profiling, "read_observations"), "raw revision reader is required"
    spec = source(tmp_path, "2026-10-23,2026-10-23,a,-0\n2026-10-23,2026-10-25,b,2\n")
    rows = profiling.read_observations(spec)
    assert tuple(row.revision for row in rows) == ("a", "b")
    assert rows[0].event_time.isoformat() == "2026-10-23T00:00:00+02:00"
    as_of = datetime(2026, 10, 24, tzinfo=timezone.utc)
    expected = freeze(
        (
            Observation(
                series_id="sales",
                event_time="2026-10-23T00:00:00+02:00",
                available_at="2026-10-23T00:00:00+02:00",
                revision="a",
                value=-0.0,
                unit="count",
            ),
        ),
        as_of,
        (
            f"source_revision={source_revision(spec)}",
            "Explicit source mapping and time semantics.",
        ),
    )
    assert (
        profiling.ingest_source(spec, as_of).model_dump_json()
        == expected.model_dump_json()
    )


def test_reader_rejects_overflow_before_parsing_rows_or_later_csv(tmp_path):
    assert hasattr(profiling, "read_observations"), (
        "bounded revision reader is required"
    )
    spec = source(tmp_path, 'invalid,invalid,a,1\ninvalid,invalid,b,2\n"unterminated')
    with pytest.raises(DomainError) as error:
        profiling.read_observations(spec, max_rows=1)
    assert error.value.code == "source_row_limit"
    assert str(tmp_path) not in error.value.model_dump_json()


def test_reader_checks_as_of_before_source_io(tmp_path):
    spec = source(tmp_path, "invalid,invalid,a,1\n")
    with pytest.raises(DomainError) as error:
        profiling.ingest_source(spec, datetime(2026, 1, 1))
    assert error.value.code == "naive_timestamp"


def test_reader_accepts_exact_limit_and_rejects_invalid_limits(tmp_path):
    spec = source(tmp_path, "2026-10-23,2026-10-23,a,1\n")
    assert len(profiling.read_observations(spec, max_rows=1)) == 1
    for limit in (0, -1, True, 1.5):
        with pytest.raises(DomainError, match="invalid_row_limit"):
            profiling.read_observations(spec, max_rows=limit)
