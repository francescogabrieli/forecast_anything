"""Frozen temporal partitions and complete, non-overlapping target windows."""

import itertools
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from ..contracts import DomainError

Partition = Literal["exploration", "selection", "final"]


def _calendar(timestamps):
    if not timestamps or any(
        t.tzinfo is None or t.utcoffset() is None for t in timestamps
    ):
        raise DomainError("invalid_split_calendar", {})
    normalized = tuple(t.astimezone(UTC) for t in timestamps)
    if any(b <= a for a, b in itertools.pairwise(normalized)):
        raise DomainError("invalid_split_calendar", {})
    return normalized


@dataclass(frozen=True)
class TemporalSplit:
    exploration_end: datetime
    selection_end: datetime
    final_start: datetime
    horizon: int
    stride: int
    _timestamps: tuple[datetime, ...] = field(default=(), repr=False)
    final_end: datetime | None = None

    def origins_for(
        self, partition: Partition, timestamps: tuple[datetime, ...]
    ) -> tuple[datetime, ...]:
        """Issue at an existing timestamp; targets are the next horizon entries.

        Partition bounds apply to targets, not the issuance timestamp. The frozen
        calendar must be reused verbatim (equivalent UTC instants are accepted).
        """
        calendar = _calendar(timestamps)
        if self._timestamps and calendar != self._timestamps:
            raise DomainError("changed_split_calendar", {})
        if partition not in {"exploration", "selection", "final"}:
            raise DomainError("invalid_partition", {"partition": partition})
        first = next(
            (
                i
                for i, t in enumerate(calendar)
                if (partition == "exploration" or t > self.exploration_end)
                and (partition != "final" or t >= self.final_start)
            ),
            len(calendar),
        )
        last = next(
            (
                i
                for i, t in enumerate(calendar)
                if (partition == "exploration" and t > self.exploration_end)
                or (partition == "selection" and t > self.selection_end)
            ),
            len(calendar),
        )
        if partition == "final" and self.final_end is not None:
            last = next(
                (i for i, t in enumerate(calendar) if t > self.final_end),
                len(calendar),
            )
        # The first timestamp supplies context; an origin needs a preceding row.
        return tuple(
            calendar[start - 1]
            for start in range(max(first, 1), last - self.horizon + 1, self.stride)
        )

    @property
    def status(self) -> str:
        if not self._timestamps:
            return "insufficient_evidence"
        return (
            "ready"
            if all(
                self.origins_for(p, self._timestamps)
                for p in ("exploration", "selection", "final")
            )
            else "insufficient_evidence"
        )


def build_splits(
    timestamps: tuple[datetime, ...],
    horizon: int,
    stride: int | None = None,
    *,
    exploration_end: datetime | None = None,
    selection_end: datetime | None = None,
    final_start: datetime | None = None,
    final_end: datetime | None = None,
) -> TemporalSplit:
    if type(horizon) is not int or horizon <= 0:
        raise DomainError("invalid_horizon", {"horizon": horizon})
    if stride is not None and (type(stride) is not int or stride <= 0):
        raise DomainError("invalid_stride", {"stride": stride})
    calendar = _calendar(timestamps)
    if len(calendar) < 4:
        raise DomainError(
            "insufficient_timestamps", {"required": 4, "actual": len(calendar)}
        )
    boundaries = (exploration_end, selection_end, final_start, final_end)
    if any(boundary is not None for boundary in boundaries):
        if any(boundary is None for boundary in boundaries):
            raise DomainError("invalid_split_boundaries", {})
        if any(
            boundary.tzinfo is None or boundary.utcoffset() is None
            for boundary in boundaries
            if boundary is not None
        ):
            raise DomainError("invalid_split_boundaries", {})
        normalized = tuple(
            boundary.astimezone(UTC) for boundary in boundaries if boundary is not None
        )
        if any(boundary not in calendar for boundary in normalized):
            raise DomainError("invalid_split_boundaries", {})
        if not (normalized[0] < normalized[1] < normalized[2] <= normalized[3]):
            raise DomainError("invalid_split_boundaries", {})
        return TemporalSplit(
            exploration_end=normalized[0],
            selection_end=normalized[1],
            final_start=normalized[2],
            horizon=horizon,
            stride=horizon if stride is None else stride,
            _timestamps=calendar,
            final_end=normalized[3],
        )

    exploration, selection = len(calendar) // 2, 3 * len(calendar) // 4
    return TemporalSplit(
        exploration_end=calendar[exploration - 1],
        selection_end=calendar[selection - 1],
        final_start=calendar[selection],
        horizon=horizon,
        stride=horizon if stride is None else stride,
        _timestamps=calendar,
    )
