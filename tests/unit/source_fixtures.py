"""Shared source mapping and CSV fixtures."""

from datetime import UTC, datetime

from forecast_anything.contracts import SourceSpec

AS_OF = datetime(2026, 10, 24, tzinfo=UTC)


MAPPING = {
    "series_id": {"constant": "sales"},
    "event_time": "date",
    "available_at": "published",
    "revision": "edition",
    "value": "amount",
    "unit": {"constant": "count"},
    "frequency": {"constant": "D"},
    "timezone": {"constant": "UTC"},
    "calendar": {"constant": "gregorian"},
    "missing_values": {"constant": [""]},
}


def csv_source(tmp_path, text="date,amount\n2026-10-24,1\n", mapping=None):
    path = tmp_path / "source.csv"
    path.write_text(text)
    return SourceSpec(
        source_id="s",
        kind="csv",
        location=str(path),
        secret_ref=None,
        mapping=mapping or {},
        refresh_seconds=60,
    )
