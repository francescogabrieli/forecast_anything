"""Bounded snapshot and series summaries."""

from __future__ import annotations

from collections import defaultdict

from ..contracts import (
    Snapshot,
    SnapshotSeriesPage,
    SnapshotSeriesSummary,
    SnapshotSummary,
)


def _bounded_samples(
    values, *, count: int, max_bytes: int
) -> tuple[tuple[str, ...], bool]:
    samples = []
    for value in sorted(set(values)):
        if len(samples) >= count:
            return tuple(samples), True
        if len(value.encode("utf-8")) > max_bytes:
            continue
        samples.append(value)
    return tuple(samples), len(samples) < len(set(values))


def _series(snapshot: Snapshot) -> tuple[SnapshotSeriesSummary, ...]:
    groups = defaultdict(list)
    for observation in snapshot.observations:
        groups[observation.series_id].append(observation)
    result = []
    for series_id, observations in sorted(groups.items()):
        units, units_truncated = _bounded_samples(
            (row.unit for row in observations), count=8, max_bytes=128
        )
        event_times = [row.event_time for row in observations]
        availability_times = [row.available_at for row in observations]
        result.append(
            SnapshotSeriesSummary(
                snapshot_id=snapshot.snapshot_id,
                series_id=series_id,
                observation_count=len(observations),
                missing_count=sum(row.value is None for row in observations),
                revision_count=len({row.revision for row in observations}),
                unit_count=len({row.unit for row in observations}),
                units=units,
                units_truncated=units_truncated,
                event_time_start=min(event_times) if event_times else None,
                event_time_end=max(event_times) if event_times else None,
                available_at_start=min(availability_times)
                if availability_times
                else None,
                available_at_end=max(availability_times)
                if availability_times
                else None,
            )
        )
    return tuple(result)


def summarize_snapshot(snapshot: Snapshot) -> SnapshotSummary:
    observations = snapshot.observations
    event_times = [row.event_time for row in observations]
    availability_times = [row.available_at for row in observations]
    assumptions, assumptions_truncated = _bounded_samples(
        snapshot.assumptions, count=16, max_bytes=256
    )
    return SnapshotSummary(
        snapshot_id=snapshot.snapshot_id,
        as_of=snapshot.as_of,
        observation_count=len(observations),
        series_count=len({row.series_id for row in observations}),
        missing_count=sum(row.value is None for row in observations),
        revision_count=len({row.revision for row in observations}),
        event_time_start=min(event_times) if event_times else None,
        event_time_end=max(event_times) if event_times else None,
        available_at_start=min(availability_times) if availability_times else None,
        available_at_end=max(availability_times) if availability_times else None,
        assumption_count=len(snapshot.assumptions),
        assumptions=assumptions,
        assumptions_truncated=assumptions_truncated,
    )


def snapshot_series_page(
    snapshot: Snapshot, *, offset: int = 0, limit: int = 25
) -> SnapshotSeriesPage:
    if (
        type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise ValueError("invalid snapshot series page")
    series = _series(snapshot)
    end = offset + limit
    return SnapshotSeriesPage(
        snapshot_id=snapshot.snapshot_id,
        series=series[offset:end],
        next_offset=end if end < len(series) else None,
    )
