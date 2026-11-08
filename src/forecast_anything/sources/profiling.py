"""Deterministic source interpretation and point-in-time ingestion (no LLM).

Mapping convention (all semantics must be explicitly resolved before ingest):

    {"event_time": "date", "available_at": "published", "value": "amount",
     "series_id": {"constant": "sales"}, "revision": "edition",
     "unit": {"constant": "count"}, "frequency": {"constant": "D"},
     "timezone": {"constant": "UTC"}, "calendar": {"constant": "gregorian"},
     "missing_values": {"constant": [""]}}

Observation roles map to a column name or {"constant": JSON scalar}. Frequency,
timezone (IANA), calendar (currently gregorian), and missing_values (an explicit
list of scalar sentinels) use constants. Missing sentinels apply only to value;
JSON null is a missing value only when declared in that list. Naive/date-only
timestamps use the declared zone; ambiguous/nonexistent local times fail.
No available_at, entity, revision, unit or cadence is synthesized. Proposals are
suggestions, never executable mappings. All source content remains untrusted.
HTTP records_path is a separate optional dotted path to an array of records.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from ..connectors.csv import load_csv_rows, parse_csv_rows
from ..connectors.http_json import (
    SecretResolver,
    load_http_json,
    sanitize_rows,
    sanitize_text,
    sensitive_key,
)
from ..contracts import (
    CsvPreview,
    DomainError,
    Observation,
    Snapshot,
    SourceField,
    SourceProfile,
    SourceSpec,
)
from ..temporal import freeze
from .catalog import source_revision

_MAX_GUIDED_CSV_BYTES = 64 * 1024 * 1024
_MAX_GUIDED_CSV_ROWS = 100_000

_ROLES = tuple(Observation.model_fields)
_SEMANTICS = ("frequency", "timezone", "calendar", "missing_values")
_CANDIDATES = {
    "event_time": {"event_time", "date", "timestamp", "time"},
    "available_at": {"available_at", "published", "published_at"},
    "revision": {"revision", "edition"},
    "value": {"value", "amount"},
}


def _read(
    spec: SourceSpec,
    limit: int | None,
    resolver: SecretResolver | None,
    *,
    read_limit: int | None = None,
):
    if spec.kind == "http_json":
        return load_http_json(spec, limit=limit, secret_resolver=resolver)
    if spec.secret_ref is not None:
        raise DomainError(
            "source_unavailable", {"reason": "csv_credentials_unsupported"}
        )
    return sanitize_rows(
        load_csv_rows(Path(spec.location), limit=read_limit),
        mapping=spec.mapping,
        limit=limit,
    )


def _typed(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.strip() == "":
        return value
    try:
        number = float(value)
        if math.isfinite(number):
            return int(value) if value.lstrip("+-").isdigit() else number
    except ValueError:
        pass
    return value


def _data_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    try:
        datetime.fromisoformat(value)
        return "datetime"
    except (ValueError, TypeError):
        return "string"


def _constant(mapping: dict, role: str):
    value = mapping.get(role)
    if isinstance(value, dict) and set(value) == {"constant"}:
        return value["constant"]
    raise ValueError


def _profile(spec: SourceSpec, rows) -> SourceProfile:
    rows = tuple(
        {key: _typed(value) for key, value in row.items()} for row in rows[:100]
    )
    columns = sorted({key for row in rows for key in row})
    fields = {}
    for key in columns:
        values = [row.get(key) for row in rows]
        kinds = {_data_type(value) for value in values if value is not None}
        kind = (next(iter(kinds)) if len(kinds) == 1 else "mixed") if kinds else "null"
        if kinds == {"integer", "number"}:
            kind = "number"
        fields[key] = SourceField(
            data_type=kind, nullable=any(value is None for value in values)
        )
    unresolved, proposed = [], {}
    for role in _ROLES:
        value = spec.mapping.get(role)
        resolved = False
        if isinstance(value, str):
            resolved = value in fields and not sensitive_key(value)
        elif isinstance(value, dict) and set(value) == {"constant"}:
            constant = value["constant"]
            resolved = not isinstance(constant, (dict, list)) and (
                not isinstance(constant, str)
                or (bool(constant.strip()) and sanitize_text(constant) == constant)
            )
            if role != "value" and constant is None:
                resolved = False
        if resolved:
            proposed[role] = value
        else:
            unresolved.append(role)
            candidates = [
                key for key in columns if key.lower() in _CANDIDATES.get(role, set())
            ]
            if len(candidates) == 1:
                proposed[role] = candidates[0]
    for semantic in _SEMANTICS:
        try:
            constant = _constant(spec.mapping, semantic)
            if semantic == "missing_values":
                valid = isinstance(constant, list) and all(
                    not isinstance(value, (dict, list)) for value in constant
                )
            elif semantic == "timezone":
                ZoneInfo(constant)
                valid = True
            elif semantic == "calendar":
                valid = constant == "gregorian"
            elif semantic == "frequency":
                valid = isinstance(constant, str) and (
                    constant in {"D", "H"}
                    or re.fullmatch(r"[1-9][0-9]*[hd]", constant) is not None
                )
            else:
                valid = (
                    isinstance(constant, str)
                    and bool(constant.strip())
                    and sanitize_text(constant) == constant
                )
            if not valid:
                raise ValueError
            proposed[semantic] = {"constant": constant}
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            unresolved.append(semantic)
    # An operational threshold is a declaration, never a statistic of samples.
    limit = spec.mapping.get("operational_limit")
    if isinstance(limit, dict) and set(limit) == {"constant"}:
        value = limit["constant"]
        if type(value) in (int, float) and math.isfinite(value):
            proposed["operational_limit"] = limit
        else:
            unresolved.append("operational_limit")
    return SourceProfile(
        source_id=spec.source_id,
        source_revision=source_revision(spec),
        fields=fields,
        proposed_mapping=proposed,
        unresolved=tuple(unresolved),
        assumptions=(
            "Column roles are proposals until explicitly mapped.",
            "Field types describe a sample of at most 100 rows.",
        ),
        sample_rows=rows,
    )


def inspect_source(
    spec: SourceSpec, *, secret_resolver: SecretResolver | None = None
) -> SourceProfile:
    """Scan source credentials and expose at most 100 sanitized sample rows."""
    return _profile(spec, _read(spec, 100, secret_resolver))


def _read_guided_csv(location: str) -> bytes:
    """Open each resolved path component without following replacement symlinks."""
    fd = None
    try:
        path = Path(location)
        parts = path.parts
        if not path.is_absolute() or any(part in {".", ".."} for part in parts):
            raise ValueError
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open("/", directory_flags)
        for part in parts[1:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        file_fd = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
        )
        try:
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                raise ValueError
            with os.fdopen(file_fd, "rb") as stream:
                file_fd = None
                content = stream.read(_MAX_GUIDED_CSV_BYTES + 1)
        finally:
            if file_fd is not None:
                os.close(file_fd)
        if len(content) > _MAX_GUIDED_CSV_BYTES:
            raise DomainError("source_too_large", {})
        return content
    except (OSError, ValueError):
        raise DomainError("source_unavailable", {"reason": "csv_read_failed"}) from None
    finally:
        if fd is not None:
            os.close(fd)


def preview_csv(
    spec: SourceSpec, as_of: datetime, *, content: bytes | None = None
) -> CsvPreview:
    """Describe one captured file and bind its exact content to the proposal."""
    if spec.kind != "csv" or spec.secret_ref is not None:
        raise DomainError(
            "source_unavailable", {"reason": "csv_credentials_unsupported"}
        )
    if content is None:
        content = _read_guided_csv(spec.location)
    digest, version = _csv_identity(spec, content, as_of)
    rows = sanitize_rows(
        parse_csv_rows(content, limit=100), mapping=spec.mapping, limit=100
    )
    profile = _profile(spec, rows)
    hints = {}
    unit_columns = [name for name in profile.fields if name.lower() == "unit"]
    if len(unit_columns) == 1 and rows:
        values = {row.get(unit_columns[0]) for row in rows}
        if len(values) == 1:
            unit = next(iter(values))
            if isinstance(unit, str) and unit.strip() and unit != "[redacted]":
                hints["unit"] = unit
    event_column = profile.proposed_mapping.get("event_time")
    if isinstance(event_column, str) and len(rows) >= 3:
        try:
            times = [datetime.fromisoformat(str(row[event_column])) for row in rows]
            intervals = {(b - a).total_seconds() for a, b in zip(times, times[1:])}
            if intervals == {86400}:
                hints["frequency"] = "1d"
            elif intervals == {3600}:
                hints["frequency"] = "1h"
        except (ValueError, TypeError, KeyError):
            pass
    return CsvPreview(
        profile=profile,
        content_digest=digest,
        proposal_version=version,
        suggestions=hints,
    )


def _csv_identity(spec: SourceSpec, content: bytes, as_of: datetime) -> tuple[str, str]:
    digest = sha256(content).hexdigest()
    proposal = json.dumps(
        {
            "algorithm": "guided-csv-v1",
            "as_of": as_of.astimezone(timezone.utc).isoformat(),
            "spec": spec.model_dump(mode="json"),
            "content_digest": digest,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return digest, sha256(proposal.encode()).hexdigest()


def _timestamp(value: Any, zone: ZoneInfo) -> datetime:
    if not isinstance(value, str):
        raise ValueError
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        return parsed
    first, second = (
        parsed.replace(tzinfo=zone, fold=0),
        parsed.replace(tzinfo=zone, fold=1),
    )
    if first.utcoffset() != second.utcoffset():
        raise ValueError("ambiguous or nonexistent local time")
    if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != parsed:
        raise ValueError("nonexistent local time")
    return first


def read_observations(
    spec: SourceSpec,
    *,
    secret_resolver: SecretResolver | None = None,
    max_rows: int | None = None,
) -> tuple[Observation, ...]:
    """Normalize supplied revisions without selecting a vintage or reordering."""
    if max_rows is not None and (type(max_rows) is not int or max_rows < 1):
        raise DomainError("invalid_row_limit", {})
    limit = None if max_rows is None else max_rows + 1
    rows = _read(spec, limit, secret_resolver, read_limit=limit)
    if max_rows is not None and len(rows) > max_rows:
        raise DomainError("source_row_limit", {"max_rows": max_rows})
    return _observations_from_rows(spec, rows)


def _observations_from_rows(spec: SourceSpec, rows) -> tuple[Observation, ...]:
    profile = _profile(spec, rows)
    if profile.unresolved:
        raise DomainError(
            "unresolved_source_mapping", {"unresolved": profile.unresolved}
        )
    zone = ZoneInfo(_constant(spec.mapping, "timezone"))
    missing_values = _constant(spec.mapping, "missing_values")
    observations = []
    for number, row in enumerate(rows, start=1):
        try:
            values = {
                role: row[mapping] if isinstance(mapping, str) else mapping["constant"]
                for role in _ROLES
                for mapping in (spec.mapping[role],)
            }
            if any(value == "[redacted]" for value in values.values()):
                raise ValueError
            missing = any(
                type(values["value"]) is type(sentinel) and values["value"] == sentinel
                for sentinel in missing_values
            )
            if missing:
                values["value"] = None
            elif values["value"] is None or isinstance(values["value"], bool):
                raise ValueError
            for role in ("event_time", "available_at"):
                values[role] = _timestamp(values[role], zone)
            observations.append(Observation.model_validate(values))
        except (KeyError, ValueError, TypeError, ValidationError):
            raise DomainError("invalid_source_row", {"row": number}) from None
    return tuple(observations)


def capture_confirmed_csv(spec: SourceSpec, proposal_version: str, as_of: datetime):
    content = _read_guided_csv(spec.location)
    if _csv_identity(spec, content, as_of)[1] != proposal_version:
        raise DomainError("source_content_changed", {})
    preview = preview_csv(spec, as_of, content=content)
    raw_rows = parse_csv_rows(content, limit=_MAX_GUIDED_CSV_ROWS + 1)
    if len(raw_rows) > _MAX_GUIDED_CSV_ROWS:
        raise DomainError("source_row_limit", {"max_rows": _MAX_GUIDED_CSV_ROWS})
    rows = sanitize_rows(raw_rows, mapping=spec.mapping, limit=None)
    observations = _observations_from_rows(spec, rows)
    snapshot = freeze(
        observations,
        as_of,
        (
            f"source_revision={source_revision(spec)}",
            f"csv_content_sha256={preview.content_digest}",
            "Explicit source mapping and time semantics.",
        ),
    )
    return preview.profile, snapshot


def ingest_source(
    spec: SourceSpec, as_of: datetime, *, secret_resolver: SecretResolver | None = None
) -> Snapshot:
    """Require explicit semantics, normalize observations, then core freeze."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise DomainError("naive_timestamp", {"field": "as_of"})
    return freeze(
        read_observations(spec, secret_resolver=secret_resolver),
        as_of,
        (
            f"source_revision={source_revision(spec)}",
            "Explicit source mapping and time semantics.",
        ),
    )
