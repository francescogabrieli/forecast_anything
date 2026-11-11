"""Canonical snapshots containing only observations available at an instant."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256

from forecast_anything.contracts import DomainError, Observation, Snapshot


def freeze(
    observations: tuple[Observation, ...],
    as_of: datetime,
    assumptions: tuple[str, ...] = (),
) -> Snapshot:
    """Select latest availability per phenomenon, treating revision IDs as opaque.

    Identical duplicates collapse. Conflicting revision identities or availability
    ties fail explicitly; future observations never influence a snapshot.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise DomainError("naive_timestamp", {"field": "as_of"})
    as_of = as_of.astimezone(UTC)
    revisions: dict[tuple[str, datetime, str], Observation] = {}
    latest: dict[tuple[str, datetime], Observation] = {}
    visible = []
    for observation in observations:
        normalized = Observation(
            **{
                **observation.model_dump(),
                "event_time": observation.event_time.astimezone(UTC),
                "available_at": observation.available_at.astimezone(UTC),
                "value": 0.0 if observation.value == 0 else observation.value,
            }
        )
        if normalized.available_at <= as_of:
            visible.append(normalized)
    # Check every visible revision before selection: a later revision must not
    # accidentally hide inconsistent copies of an older revision.
    for observation in visible:
        key = (observation.series_id, observation.event_time)
        revision_key = (*key, observation.revision)
        previous = revisions.get(revision_key)
        if previous is not None and previous != observation:
            raise DomainError(
                "conflicting_revision",
                {
                    "series_id": observation.series_id,
                    "event_time": observation.event_time.isoformat(),
                    "revision": observation.revision,
                },
            )
        revisions[revision_key] = observation
    # Group by availability so even superseded ambiguous ties are detected.
    availability: dict[tuple[str, datetime, datetime], Observation] = {}
    for observation in revisions.values():
        key = (observation.series_id, observation.event_time)
        availability_key = (*key, observation.available_at)
        previous = availability.get(availability_key)
        if previous is not None and previous != observation:
            raise DomainError(
                "conflicting_availability",
                {
                    "series_id": observation.series_id,
                    "event_time": observation.event_time.isoformat(),
                    "available_at": observation.available_at.isoformat(),
                },
            )
        availability[availability_key] = observation
        selected = latest.get(key)
        if selected is None or observation.available_at > selected.available_at:
            latest[key] = observation
    selected_observations = tuple(latest[key] for key in sorted(latest))
    content = {
        "as_of": as_of.isoformat(),
        "observations": [o.model_dump(mode="json") for o in selected_observations],
        "assumptions": list(assumptions),
    }
    canonical = json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return Snapshot(
        snapshot_id=sha256(canonical.encode("utf-8")).hexdigest(),
        as_of=as_of,
        observations=selected_observations,
        assumptions=assumptions,
    )
