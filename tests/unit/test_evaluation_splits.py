"""Frozen evaluation splits and holdout windows."""

from datetime import timedelta

import pytest
from evaluation_fixtures import T
from pydantic import ValidationError

from forecast_anything.contracts import (
    DomainError,
)
from forecast_anything.evaluation.splits import build_splits


def test_final_split_is_separate():
    split = build_splits(tuple(T + timedelta(days=i) for i in range(100)), horizon=5)
    assert split.exploration_end < split.selection_end < split.final_start
    assert split.stride == split.horizon == 5
    assert split.exploration_end == T + timedelta(days=49)
    assert split.selection_end == T + timedelta(days=74)
    assert split.final_start == T + timedelta(days=75)


def test_no_overlap_final_split():
    timestamps = tuple(T + timedelta(days=i) for i in range(103))
    split = build_splits(timestamps, horizon=5)
    windows = {}
    for partition in ("exploration", "selection", "final"):
        origins = split.origins_for(partition, timestamps)
        windows[partition] = [
            set(timestamps[timestamps.index(origin) + 1 : timestamps.index(origin) + 6])
            for origin in origins
        ]
        assert all(len(w) == 5 for w in windows[partition])
        assert all(
            not a & b
            for a, b in zip(windows[partition], windows[partition][1:], strict=False)
        )
    assert max(set.union(*windows["exploration"])) <= split.exploration_end
    assert min(set.union(*windows["selection"])) > split.exploration_end
    assert max(set.union(*windows["selection"])) <= split.selection_end
    assert min(set.union(*windows["final"])) >= split.final_start
    with pytest.raises((ValidationError, AttributeError)):
        split.final_start = T


@pytest.mark.parametrize(
    "timestamps,horizon",
    [
        ((), 1),
        ((T, T), 1),
        ((T + timedelta(days=1), T), 1),
        ((T.replace(tzinfo=None),), 1),
        ((T,), 0),
        ((T,), True),
    ],
)
def test_invalid_splits(timestamps, horizon):
    with pytest.raises(DomainError):
        build_splits(timestamps, horizon)


def test_short_split_has_no_final_origins():
    timestamps = tuple(T + timedelta(days=i) for i in range(8))
    split = build_splits(timestamps, 5)
    assert split.origins_for("final", timestamps) == ()
    assert split.status == "insufficient_evidence"


def test_frozen_split_rejects_extended_or_revised_calendar():
    timestamps = tuple(T + timedelta(days=i) for i in range(100))
    split = build_splits(timestamps, 5)
    with pytest.raises(DomainError, match="changed_split_calendar"):
        split.origins_for("final", (*timestamps, T + timedelta(days=100)))
