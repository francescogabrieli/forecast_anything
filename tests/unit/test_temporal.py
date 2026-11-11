from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from forecast_anything.contracts import DomainError, Observation
from forecast_anything.temporal import freeze


def observation(
    value=10, revision="z", available="2026-10-19T00:00:00+00:00", **kwargs
):
    return Observation(
        series_id="a",
        event_time="2026-10-18T00:00:00+00:00",
        available_at=available,
        revision=revision,
        value=value,
        unit="count",
        **kwargs,
    )


def test_late_revision_is_invisible_asof():
    old = observation()
    new = observation(12, "a", "2026-10-21T00:00:00+00:00")
    assert freeze((new, old), datetime(2026, 10, 20, tzinfo=UTC)).observations == (old,)
    assert freeze((old, new), datetime(2026, 10, 22, tzinfo=UTC)).observations == (new,)


def test_conflicting_same_revision():
    with pytest.raises(DomainError):
        freeze(
            (observation(), observation(12)),
            datetime(2026, 10, 24, tzinfo=UTC),
        )


def test_conflicting_availability_tie():
    with pytest.raises(DomainError):
        freeze(
            (observation(), observation(12, "other")),
            datetime(2026, 10, 24, tzinfo=UTC),
        )


def test_same_revision_with_changed_availability_is_conflicting():
    with pytest.raises(DomainError):
        freeze(
            (observation(), observation(12, "z", "2026-10-20T00:00:00+00:00")),
            datetime(2026, 10, 24, tzinfo=UTC),
        )


def test_snapshot_hash_is_order_independent():
    t = datetime(2026, 10, 24, tzinfo=UTC)
    a = Observation(
        series_id="a", event_time=t, available_at=t, revision="1", value=1, unit="count"
    )
    b = Observation(
        series_id="b", event_time=t, available_at=t, revision="1", value=2, unit="count"
    )
    assert freeze((a, b), t).snapshot_id == freeze((b, a), t).snapshot_id
    assert freeze((b, a, a), t).observations == (a, b)


def test_assumed_availability_and_asof_are_part_of_identity():
    t = datetime(2026, 10, 24, tzinfo=UTC)
    declared = ("assumed_available_at=event_time", "retrospective dataset")
    snapshot = freeze((observation(),), t, declared)
    assert snapshot.assumptions == declared
    assert snapshot.snapshot_id != freeze((observation(),), t).snapshot_id
    assert (
        snapshot.snapshot_id
        != freeze((observation(),), t.replace(day=25), declared).snapshot_id
    )


def test_naive_asof_is_rejected():
    with pytest.raises(DomainError):
        freeze((), datetime(2026, 10, 24))


def test_dst_repeated_hours_are_distinct_and_normalized():
    rome = ZoneInfo("Europe/Rome")
    first = datetime(2026, 10, 25, 2, 30, tzinfo=rome, fold=0)
    second = datetime(2026, 10, 25, 2, 30, tzinfo=rome, fold=1)
    a = Observation(
        series_id="a",
        event_time=first,
        available_at=first,
        revision="1",
        value=1,
        unit="count",
    )
    b = Observation(
        series_id="a",
        event_time=second,
        available_at=second,
        revision="1",
        value=2,
        unit="count",
    )
    early = freeze((a, b), datetime(2026, 10, 25, 1, tzinfo=UTC))
    assert [o.value for o in early.observations] == [1]
    later = freeze((b, a), second)
    assert [o.event_time.isoformat() for o in later.observations] == [
        "2026-10-25T00:30:00+00:00",
        "2026-10-25T01:30:00+00:00",
    ]
    assert later.as_of.isoformat() == "2026-10-25T01:30:00+00:00"
    utc = tuple(
        o.model_copy(
            update={
                "event_time": o.event_time.astimezone(UTC),
                "available_at": o.available_at.astimezone(UTC),
            }
        )
        for o in (a, b)
    )
    assert later.snapshot_id == freeze(utc, second.astimezone(UTC)).snapshot_id


def test_future_conflicts_do_not_change_current_snapshot():
    t = datetime(2026, 10, 20, tzinfo=UTC)
    future = (
        observation(12, "new", "2026-10-21T00:00:00+00:00"),
        observation(13, "new", "2026-10-21T00:00:00+00:00"),
    )
    assert (
        freeze((observation(), *future), t).snapshot_id
        == freeze((observation(),), t).snapshot_id
    )


def test_empty_snapshot_and_missing_value():
    t = datetime(2026, 10, 24, tzinfo=UTC)
    assert freeze((), t).observations == ()
    assert freeze((observation(None),), t).observations[0].value is None


def test_signed_zero_duplicates_have_order_independent_identity():
    t = datetime(2026, 10, 24, tzinfo=UTC)
    positive, negative = observation(0.0), observation(-0.0)
    assert (
        freeze((positive, negative), t).snapshot_id
        == freeze((negative, positive), t).snapshot_id
    )
