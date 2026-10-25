"""CSV observations with explicit identity, availability, revision and unit.

All six Observation columns are required. Empty value cells mean None; no
other field is inferred. Additional/duplicate columns and ragged rows fail.
"""

import csv
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
