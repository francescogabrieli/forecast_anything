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

import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from ..connectors.csv import load_csv_rows
from ..connectors.http_json import (
    SecretResolver,
    load_http_json,
    sanitize_rows,
    sanitize_text,
    sensitive_key,
)
from ..contracts import (
    DomainError,
    Observation,
    Snapshot,
    SourceField,
    SourceProfile,
    SourceSpec,
)
from ..temporal import freeze
from .catalog import source_revision

_ROLES = tuple(Observation.model_fields)
_SEMANTICS = ("frequency", "timezone", "calendar", "missing_values")
_CANDIDATES = {
    "event_time": {"event_time", "date", "timestamp", "time"},
    "available_at": {"available_at", "published", "published_at"},
    "revision": {"revision", "edition"},
    "value": {"value", "amount"},
}


def _read(spec: SourceSpec, limit: int | None, resolver: SecretResolver | None):
    if spec.kind == "http_json":
        return load_http_json(spec, limit=limit, secret_resolver=resolver)
    if spec.secret_ref is not None:
        raise DomainError(
            "source_unavailable", {"reason": "csv_credentials_unsupported"}
        )
    return sanitize_rows(
        load_csv_rows(Path(spec.location)), mapping=spec.mapping, limit=limit
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
                not isinstance(constant, str) or sanitize_text(constant) == constant
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


def ingest_source(
    spec: SourceSpec, as_of: datetime, *, secret_resolver: SecretResolver | None = None
) -> Snapshot:
    """Require explicit semantics, normalize observations, then core freeze."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise DomainError("naive_timestamp", {"field": "as_of"})
    rows = _read(spec, None, secret_resolver)
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
    return freeze(
        tuple(observations),
        as_of,
        (
            f"source_revision={source_revision(spec)}",
            "Explicit source mapping and time semantics.",
        ),
    )
