"""Pure comparison rules for deciding whether a source refresh is an append."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .contracts import DomainError, Observation, Snapshot

SnapshotChangeKind = Literal[
    "unchanged",
    "append",
    "mapping_changed",
    "historical_availability_altered",
    "historical_correction",
    "historical_deletion",
    "invalid_append",
]


@dataclass(frozen=True)
class SnapshotChange:
    kind: SnapshotChangeKind
    added: tuple[Observation, ...] = ()

    @property
    def added_count(self) -> int:
        return len(self.added)


def _observation_map(snapshot: Snapshot) -> dict[tuple[str, datetime], Observation]:
    values = {(row.series_id, row.event_time): row for row in snapshot.observations}
    if len(values) != len(snapshot.observations):
        raise DomainError("ambiguous_snapshot_observations", {})
    return values


def classify_snapshot_change(
    previous: Snapshot,
    current: Snapshot,
    now: datetime,
    *,
    mapping_unchanged: bool = True,
) -> SnapshotChange:
    """Return append only when every historical observation is unchanged.

    Snapshot identity includes capture time, so identical observations in a later
    capture are compared by their data rather than by ``snapshot_id``.
    """
    previous = Snapshot.model_validate(previous.model_dump())
    current = Snapshot.model_validate(current.model_dump())
    if now.tzinfo is None or now.utcoffset() is None:
        raise DomainError("naive_timestamp", {"field": "now"})
    if not mapping_unchanged:
        return SnapshotChange("mapping_changed")

    old = _observation_map(previous)
    new = _observation_map(current)

    for key, old_row in old.items():
        new_row = new.get(key)
        if new_row is None:
            continue
        if old_row.available_at != new_row.available_at:
            return SnapshotChange("historical_availability_altered")

    if any(key not in new for key in old):
        return SnapshotChange("historical_deletion")

    for key, old_row in old.items():
        new_row = new[key]
        if (
            old_row.series_id,
            old_row.event_time,
            old_row.value,
            old_row.revision,
            old_row.unit,
        ) != (
            new_row.series_id,
            new_row.event_time,
            new_row.value,
            new_row.revision,
            new_row.unit,
        ):
            return SnapshotChange("historical_correction")

    added = tuple(new[key] for key in sorted(new.keys() - old.keys()))
    if not added:
        return SnapshotChange("unchanged")

    latest_old = max((row.event_time for row in old.values()), default=None)
    if latest_old is None or any(row.event_time <= latest_old for row in added):
        return SnapshotChange("historical_correction", added)
    if any(row.available_at > now for row in added):
        return SnapshotChange("invalid_append", added)
    return SnapshotChange("append", added)
