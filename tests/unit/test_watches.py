"""Watch qualification, lifecycle and relevance controls."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from watch_fixtures import NOW, active_watch, decision, watch

from forecast_anything.contracts import (
    DomainError,
    Watch,
)
from forecast_anything.watches import (
    advance_watch,
    group_notifications,
)


def test_refresh_expired_is_visible():
    t = datetime(2026, 10, 24, tzinfo=UTC)
    w = Watch(
        watch_id="w",
        candidate_id="c",
        lifecycle="active",
        quality="usable",
        graph_id="g",
        graph_version=1,
        policy_version="1",
        next_due_at=t,
        muted=False,
    )
    assert advance_watch(w, {"kind": "refresh_expired"}, t).quality == "stale"


@pytest.mark.parametrize("action", ["provisional", "reject"])
def test_insufficient_evidence_never_activates(action):
    w = watch()
    result = advance_watch(
        w, {"kind": "evidence_qualified", "decision": decision(w, action)}, NOW
    )
    assert (result.lifecycle, result.quality, result.operational) == (
        "evaluating",
        "provisional",
        False,
    )
    assert result.candidate == w.candidate
    assert result.eligibility_decision.action == action
    result = advance_watch(active_watch(), {"kind": "insufficient_evidence"}, NOW)
    assert (result.lifecycle, result.quality, result.operational) == (
        "evaluating",
        "provisional",
        False,
    )


def test_qualified_activation_preserves_candidate_and_decision_lineage():
    w = watch()
    d = decision(w)
    result = advance_watch(
        w, {"kind": "evidence_qualified", "decision": d.model_dump()}, NOW
    )
    assert (result.lifecycle, result.quality, result.operational) == (
        "active",
        "usable",
        True,
    )
    assert result.candidate == w.candidate
    assert result.eligibility_decision == d
    assert w.lifecycle == "candidate"


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_id": "other"},
        {"protocol_id": "other"},
        {"epoch_id": "other"},
        {"policy_version": "other"},
        {"evaluation_ids": ()},
    ],
)
def test_activation_rejects_missing_or_wrong_lineage(changes):
    w = watch()
    with pytest.raises(DomainError):
        advance_watch(
            w, {"kind": "evidence_qualified", "decision": decision(w, **changes)}, NOW
        )
    assert w.lifecycle == "candidate"


def test_activation_without_decision_fails_closed():
    with pytest.raises(DomainError):
        advance_watch(watch(), {"kind": "evidence_qualified"}, NOW)


def test_unsupported_stays_unsupported():
    w = watch("unknown")
    assert w.lifecycle == "unsupported"
    result = advance_watch(
        w, {"kind": "evidence_qualified", "decision": decision(w)}, NOW
    )
    assert result.lifecycle == "unsupported"
    assert not result.operational


def test_stale_after_missing_refresh():
    w = active_watch(next_due_at=NOW)
    result = advance_watch(w, {"kind": "refresh_expired"}, NOW + timedelta(seconds=1))
    assert (result.lifecycle, result.quality, result.operational) == (
        "active",
        "stale",
        False,
    )
    assert result.eligibility_decision == w.eligibility_decision
    assert result.next_due_at == w.next_due_at
    with pytest.raises(DomainError):
        advance_watch(w, {"kind": "refresh_expired"}, NOW - timedelta(seconds=1))


@pytest.mark.parametrize("deadline", [None, NOW, NOW + timedelta(days=1)])
def test_expired_decision_replay_requires_effective_future_deadline(deadline):
    w = active_watch(next_due_at=NOW + timedelta(days=1))
    expired_at = NOW + timedelta(days=1)
    stale = advance_watch(w, {"kind": "refresh_expired"}, expired_at)
    event = {"kind": "evidence_qualified", "decision": w.eligibility_decision}
    if deadline is not None:
        event["next_due_at"] = deadline
    with pytest.raises(DomainError, match="invalid_refresh_deadline"):
        advance_watch(stale, event, expired_at)
    assert not stale.operational
    assert stale.quality == "stale"
    assert stale.next_due_at == expired_at


def test_initial_activation_requires_effective_future_deadline():
    w = watch().model_copy(update={"next_due_at": NOW})
    with pytest.raises(DomainError, match="invalid_refresh_deadline"):
        advance_watch(w, {"kind": "evidence_qualified", "decision": decision(w)}, NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"candidate_id": "other"},
        {"protocol_id": "other"},
        {"epoch_id": "other"},
        {"policy_version": "other"},
    ],
)
def test_future_deadline_restores_only_matching_qualification(changes):
    w = active_watch(next_due_at=NOW + timedelta(days=1))
    expired_at = NOW + timedelta(days=1)
    stale = advance_watch(w, {"kind": "refresh_expired"}, expired_at)
    event = {
        "kind": "evidence_qualified",
        "decision": decision(w, **changes),
        "next_due_at": expired_at + timedelta(days=1),
    }
    if changes:
        with pytest.raises(DomainError, match="decision_lineage_mismatch"):
            advance_watch(stale, event, expired_at)
        assert not stale.operational
    else:
        restored = advance_watch(stale, event, expired_at)
        assert restored.operational
        assert restored.next_due_at == NOW + timedelta(days=2)
        assert restored.eligibility_decision == stale.eligibility_decision


@pytest.mark.parametrize(
    "kind,key,old,new",
    [
        ("source_revised", "source_id", "sales", "mapping-v2"),
        ("mapping_revised", "source_id", "sales", "mapping-v2"),
        ("snapshot_revised", "snapshot_id", "snapshot-1", "snapshot-2"),
    ],
)
def test_revised_source_invalidates_dependent_evidence(kind, key, old, new):
    w = active_watch(source_snapshot_ids=("snapshot-1",))
    result = advance_watch(
        w, {"kind": kind, key: old, "revision": new, "origin_id": "update-1"}, NOW
    )
    assert (result.lifecycle, result.quality) == ("evaluating", "stale")
    assert not result.evidence_applicable
    assert result.reevaluation_required
    assert result.next_due_at == NOW
    assert result.invalidated_evaluation_ids == ("evaluation",)
    assert result.eligibility_decision == w.eligibility_decision
    assert result.candidate == w.candidate
    with pytest.raises(DomainError, match="invalidated_watch_evidence"):
        advance_watch(
            result, {"kind": "evidence_qualified", "decision": decision(w)}, NOW
        )
    assert advance_watch(w, {"kind": kind, key: "unrelated", "revision": new}, NOW) == w


@pytest.mark.parametrize(
    "kind,key",
    [
        ("source_revised", "source_id"),
        ("mapping_revised", "source_id"),
        ("snapshot_revised", "snapshot_id"),
    ],
)
def test_revised_dependency_requires_a_fresh_candidate_even_with_new_evidence(
    kind, key
):
    w = active_watch(source_snapshot_ids=("snapshot-1",))
    revised = advance_watch(
        w,
        {
            "kind": kind,
            key: "snapshot-1" if key == "snapshot_id" else "sales",
            "revision": "v2",
        },
        NOW,
    )
    with pytest.raises(DomainError, match="watch_candidate_invalidated"):
        advance_watch(
            revised,
            {
                "kind": "evidence_qualified",
                "decision": decision(w, evaluation_ids=("fresh",)),
            },
            NOW,
        )
    assert revised.candidate_invalidated


def test_qualification_can_schedule_next_refresh():
    w = watch()
    result = advance_watch(
        w,
        {
            "kind": "evidence_qualified",
            "decision": decision(w),
            "next_due_at": NOW + timedelta(days=1),
        },
        NOW,
    )
    assert result.next_due_at == NOW + timedelta(days=1)
    assert result.operational
    with pytest.raises(DomainError, match="invalid_refresh_deadline"):
        advance_watch(
            w,
            {"kind": "evidence_qualified", "decision": decision(w), "next_due_at": NOW},
            NOW,
        )


def test_shared_cause_is_grouped():
    first, second = active_watch(), active_watch(watch_id="second")
    groups = group_notifications(
        (
            {"watch": first, "origin_id": "update-1", "kind": "forecast_changed"},
            {"watch": second, "origin_id": "update-1", "kind": "forecast_changed"},
            {"watch": first, "origin_id": "update-2", "kind": "forecast_changed"},
            {
                "watch": active_watch(watch_id="muted", muted=True),
                "origin_id": "update-1",
                "kind": "forecast_changed",
            },
            {
                "watch": watch(watch_id="provisional"),
                "origin_id": "update-1",
                "kind": "forecast_changed",
            },
        )
    )
    assert [g["origin_id"] for g in groups] == ["update-1", "update-2"]
    assert groups[0]["watch_ids"] == ("w", "second")
    assert len(groups[0]["notifications"]) == 2
    assert second.watch_id == "second"


def test_pause_mute_priority_and_quality_are_independent():
    w = active_watch()
    paused = advance_watch(w, {"kind": "paused"}, NOW)
    assert paused.lifecycle == "paused"
    assert paused.quality == "usable"
    assert not paused.operational
    assert (
        advance_watch(
            paused, {"kind": "evidence_qualified", "decision": decision(w)}, NOW
        ).lifecycle
        == "paused"
    )
    resumed = advance_watch(paused, {"kind": "resumed"}, NOW)
    assert resumed.operational
    muted = advance_watch(w, {"kind": "muted", "muted": True}, NOW)
    assert (muted.lifecycle, muted.quality) == ("active", "usable")
    assert not muted.operational
    assert advance_watch(muted, {"kind": "muted", "muted": False}, NOW).operational
    assert (
        advance_watch(w, {"kind": "priority_changed", "priority": 0}, NOW).priority == 0
    )
    degraded = advance_watch(w, {"kind": "quality_degraded"}, NOW)
    assert (degraded.lifecycle, degraded.quality, degraded.operational) == (
        "active",
        "degraded",
        False,
    )


@pytest.mark.parametrize("priority", [-1, 6, True, 2.5])
def test_priority_is_bounded_integer(priority):
    with pytest.raises(ValidationError):
        Watch.model_validate(active_watch().model_dump() | {"priority": priority})


def test_unknown_events_and_naive_clock_fail_closed():
    with pytest.raises(DomainError, match="unknown_watch_event"):
        advance_watch(watch(), {"kind": "invented"}, NOW)
    with pytest.raises(DomainError, match="invalid_watch_time"):
        advance_watch(
            watch(), {"kind": "muted", "muted": True}, NOW.replace(tzinfo=None)
        )
