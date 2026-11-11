"""Provider protocol and shared validation for fixed UTC numerical calendars."""

import itertools
import re
from datetime import UTC, timedelta
from typing import Protocol

from ..contracts import (
    Capabilities,
    DomainError,
    ForecastRequest,
    ForecastResult,
    Snapshot,
)


class ForecastProvider(Protocol):
    def capabilities(self) -> Capabilities: ...
    def forecast(self, request: ForecastRequest) -> ForecastResult: ...


def frequency_step(frequency: str) -> timedelta:
    if not re.fullmatch(r"[1-9][0-9]*[hd]", frequency):
        raise DomainError("unsupported_frequency", {"frequency": frequency})
    try:
        return timedelta(
            **{"hours" if frequency[-1] == "h" else "days": int(frequency[:-1])}
        )
    except OverflowError as error:
        raise DomainError("unsupported_frequency", {"frequency": frequency}) from error


def observation_grid(snapshot: Snapshot, frequency: str):
    """Return sorted series histories after checking availability and aligned grids.

    Event times may lie in the future for known-future covariates; callers decide
    whether this snapshot is history or a future calendar. No resampling occurs.
    """
    step = frequency_step(frequency)
    groups = {}
    for observation in snapshot.observations:
        if observation.available_at.astimezone(UTC) > snapshot.as_of.astimezone(UTC):
            raise DomainError(
                "unavailable_observation", {"series_id": observation.series_id}
            )
        groups.setdefault(observation.series_id, []).append(observation)
    if not groups:
        raise DomainError("empty_history", {})
    calendar = None
    for series_id, observations in groups.items():
        observations.sort(key=lambda o: o.event_time.astimezone(UTC))
        timestamps = tuple(o.event_time.astimezone(UTC) for o in observations)
        if any(b - a != step for a, b in itertools.pairwise(timestamps)):
            raise DomainError("irregular_calendar", {"series_id": series_id})
        if len({o.unit for o in observations}) != 1:
            raise DomainError("incompatible_units", {"series_id": series_id})
        if calendar is not None and timestamps != calendar:
            raise DomainError("incompatible_calendar", {"series_id": series_id})
        calendar = timestamps
    return groups, calendar
