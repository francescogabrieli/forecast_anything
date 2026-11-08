"""CSV observations with explicit identity, availability, revision and unit.

All six Observation columns are required. Empty value cells mean None; no
other field is inferred. Additional/duplicate columns and ragged rows fail.
"""

import csv
import io
from itertools import islice
from pathlib import Path

from pydantic import ValidationError

from ..contracts import DomainError, Observation


def load_csv(path: Path) -> tuple[Observation, ...]:
    fields = set(Observation.model_fields)
    observations = []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        try:
            header = reader.fieldnames or []
            if len(header) != len(fields) or set(header) != fields:
                raise DomainError(
                    "invalid_csv_header", {"required": sorted(fields), "actual": header}
                )
            for row_number, row in enumerate(reader, start=2):
                if None in row or any(value is None for value in row.values()):
                    raise DomainError(
                        "invalid_csv_row", {"row": row_number, "reason": "column count"}
                    )
                row["value"] = None if row["value"].strip() == "" else row["value"]
                try:
                    observations.append(Observation.model_validate(row))
                except ValidationError as error:
                    raise DomainError(
                        "invalid_csv_row",
                        {
                            "row": row_number,
                            "errors": error.errors(
                                include_context=False, include_url=False
                            ),
                        },
                    ) from error
        except csv.Error as error:
            raise DomainError(
                "invalid_csv", {"line": reader.line_num, "message": str(error)}
            ) from error
    return tuple(observations)


def load_csv_rows(
    path: Path, *, limit: int | None = None
) -> tuple[dict[str, str], ...]:
    """Read tabular source data without interpreting or executing its cells.

    Unlike load_csv, this accepts arbitrary columns for explicit source mapping.
    Errors deliberately omit paths, headers and values: these may hold secrets.
    """
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            return _parse_csv_stream(stream, limit=limit)
    except (OSError, UnicodeError, csv.Error):
        raise DomainError("source_unavailable", {"reason": "csv_read_failed"}) from None


def parse_csv_rows(
    data: bytes, *, limit: int | None = None
) -> tuple[dict[str, str], ...]:
    """Parse an immutable byte capture using the normal source CSV rules."""
    try:
        with io.StringIO(data.decode("utf-8-sig"), newline="") as stream:
            return _parse_csv_stream(stream, limit=limit)
    except (UnicodeError, csv.Error):
        raise DomainError("source_unavailable", {"reason": "csv_read_failed"}) from None


def _parse_csv_stream(stream, *, limit):
    rows = []
    reader = csv.DictReader(stream, strict=True)
    header = reader.fieldnames or []
    if not header or len(header) != len(set(header)) or any(not h for h in header):
        raise DomainError("invalid_source_data", {"reason": "invalid_csv_header"})
    bounded = reader if limit is None else islice(reader, limit)
    for row_number, row in enumerate(bounded, start=2):
        if None in row or any(value is None for value in row.values()):
            raise DomainError("invalid_source_row", {"row": row_number})
        rows.append(row)
    return tuple(rows)
