"""Watch qualification, durable relevance controls and comparable forecast changes."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from forecast_anything.contracts import (
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EligibilityDecision,
    EvaluationContext,
    EvaluationRecord,
    ForecastResult,
    Observation,
    RunRecord,
    Snapshot,
    SourceProfile,
    Watch,
)
from forecast_anything.discovery.candidates import CandidateProposal, compile_proposal
from forecast_anything.discovery.policy import assess_candidate
from forecast_anything.evaluation.records import evaluate_run
from forecast_anything.store import MIGRATIONS, Ledger
from forecast_anything.watches import (
    advance_watch,
    create_watch,
    group_notifications,
    summarize_change,
    summarize_watch_change,
)

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def candidate(template="forecast_change", epoch_id="epoch"):
    mapping = {
        name: {"constant": value}
        for name, value in {
            "event_time": "2026-01-01T00:00:00Z",
            "available_at": "2026-01-01T00:00:00Z",
            "revision": "1",
            "value": 1,
            "series_id": "sales",
            "unit": "count",
            "frequency": "D",
            "timezone": "UTC",
            "calendar": "gregorian",
            "missing_values": [],
        }.items()
    }
    profile = SourceProfile(
        source_id="sales",
        source_revision="mapping-v1",
        fields={},
        proposed_mapping=mapping,
        unresolved=(),
        assumptions=(),
    )
    return compile_proposal(
        CandidateProposal(
            template_id=template, source_ids=("sales",), reason="Review sales"
        ),
        (profile,),
        epoch_id=epoch_id,
    )


def watch(template="forecast_change", watch_id="w"):
    return create_watch(
        candidate(template), watch_id=watch_id, next_due_at=NOW + timedelta(days=1)
    )


def decision(w, action="activate", **changes):
    return EligibilityDecision.model_validate(
        dict(
            action=action,
            reason_codes=("qualified_final_evidence",),
            candidate_id=w.candidate_id,
            protocol_id=w.candidate.protocol_id,
            epoch_id=w.candidate.epoch_id,
            evaluation_ids=("evaluation",),
            policy_version=w.policy_version,
        )
        | changes
    )


def active_watch(**changes):
    w = watch()
    return advance_watch(
        w, {"kind": "evidence_qualified", "decision": decision(w)}, NOW
    ).model_copy(update=changes)


def test_refresh_expired_is_visible():
    t = datetime(2026, 10, 24, tzinfo=timezone.utc)
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


def run(run_id, timestamps, point, series=("sales",), units=("count",), **changes):
    result = ForecastResult(
        provider_id="seasonal_naive",
        provider_revision="1",
        series_ids=series,
        timestamps=tuple(NOW + timedelta(days=d) for d in timestamps),
        units=units,
        point=point,
        quantiles=None,
        paths=None,
        sample_group_id=None,
        assumptions=(),
    )
    return RunRecord.model_validate(
        dict(
            run_id=run_id,
            graph_id=candidate().graph.graph_id,
            graph_version=1,
            as_of=NOW,
            snapshot_ids=(f"snapshot-{run_id}",),
            requested_provider={},
            actual_provider={},
            state="completed",
            results={"question": result},
            evidence_ids=(),
            scenario_id=None,
            parent_run_id=None,
        )
        | changes
    )


def test_change_summary_separates_window_advance_from_common_target_changes():
    previous = run("old", (1, 2), ((10, 20),))
    current = run("new", (2, 3), ((23, 30),))
    summary = summarize_change(previous, current)
    assert summary["changes"] == [
        {
            "node_id": "question",
            "series_id": "sales",
            "timestamp": (NOW + timedelta(days=2)).isoformat(),
            "representation": "point",
            "previous": 20.0,
            "current": 23.0,
            "delta": 3.0,
            "unit": "count",
        }
    ]
    assert summary["added_targets"] == [
        {
            "node_id": "question",
            "series_id": "sales",
            "timestamp": (NOW + timedelta(days=3)).isoformat(),
        }
    ]
    assert summary["removed_targets"] == [
        {
            "node_id": "question",
            "series_id": "sales",
            "timestamp": (NOW + timedelta(days=1)).isoformat(),
        }
    ]
    assert summary["new_snapshot_ids"] == ["snapshot-new"]


def test_window_advance_alone_is_not_forecast_change():
    summary = summarize_change(
        run("a", (1, 2), ((10, 20),)), run("b", (2, 3), ((20, 30),))
    )
    assert summary["changes"] == []
    assert summary["added_targets"]


def test_change_summary_matches_series_identity_instead_of_row_position():
    a = run("a", (1,), ((10,), (50,)), series=("sales", "cost"), units=("count", "EUR"))
    b = run("b", (1,), ((55,), (10,)), series=("cost", "sales"), units=("EUR", "count"))
    summary = summarize_change(a, b)
    assert len(summary["changes"]) == 1
    assert summary["changes"][0]["series_id"] == "cost"
    assert summary["changes"][0]["delta"] == 5


def test_change_summary_compares_common_quantiles_without_pairing_joint_samples():
    before = run("a", (1,), ((10,),))
    after = run("b", (1,), ((10,),))
    before.results["question"] = before.results["question"].model_copy(
        update={
            "quantiles": {"0.5": ((10,),), "0.9": ((20,),)},
            "paths": (((1,),),),
            "sample_group_id": "old-samples",
        }
    )
    after.results["question"] = after.results["question"].model_copy(
        update={
            "quantiles": {"0.5": ((12,),), "0.95": ((30,),)},
            "paths": (((100,),),),
            "sample_group_id": "new-samples",
        }
    )
    summary = summarize_change(before, after)
    assert len(summary["changes"]) == 1
    assert summary["changes"][0]["representation"] == "quantile:0.5"
    assert summary["changes"][0]["delta"] == 2


def test_ambiguous_target_identity_is_rejected():
    with pytest.raises(DomainError, match="ambiguous_forecast_identity"):
        summarize_change(run("a", (1, 1), ((10, 10),)), run("b", (1,), ((11,),)))


@pytest.mark.parametrize(
    "changes",
    [
        {"graph_id": "other"},
        {"graph_version": 2},
        {"scenario_id": "scenario"},
        {"state": "failed"},
    ],
)
def test_incomparable_runs_are_rejected(changes):
    with pytest.raises(DomainError, match="incomparable_runs"):
        summarize_change(run("a", (1,), ((10,),)), run("b", (1,), ((11,),), **changes))


def test_incompatible_units_and_unshared_series_are_not_subtracted():
    summary = summarize_change(
        run("a", (1,), ((10,),)), run("b", (1,), ((11,),), units=("EUR",))
    )
    assert summary["changes"] == []
    assert summary["incomparable"]
    summary = summarize_change(
        run("a", (1,), ((10,),)), run("b", (1,), ((11,),), series=("other",))
    )
    assert summary["changes"] == []
    assert summary["added_targets"] == []


@pytest.mark.parametrize("template", ["forecast_change", "expected_deviation"])
def test_watch_change_summary_retains_question_semantics(template):
    w = watch(template)
    summary = summarize_watch_change(
        w, run("a", (1,), ((10,),)), run("b", (1,), ((11,),))
    )
    assert summary["template_id"] == template
    assert summary["question"] == "Review sales"
    assert summary["candidate_id"] == w.candidate_id
    assert "causal" in summary["explanation"]


def stored_watch(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate()
    ledger.put_snapshot(
        Snapshot(snapshot_id="snapshot-1", as_of=NOW, observations=(), assumptions=())
    )
    ledger.put_discovery_epoch(
        DiscoveryEpoch(
            epoch_id=c.epoch_id,
            source_snapshot_ids=("snapshot-1",),
            explored_candidate_ids=(c.candidate_id,),
            final_origin_ids=(),
        ),
        DiscoveryBudget(),
    )
    ledger.register_candidate(c)
    ledger.put_watch(watch())
    return ledger


def test_muting_preserves_history(tmp_path):
    ledger = stored_watch(tmp_path)
    issued = run("issued", (1,), ((10,),))
    ledger.append_run(issued, (), "issued")
    ledger.put_snapshot(
        Snapshot(snapshot_id="actuals", as_of=NOW, observations=(), assumptions=())
    )
    evaluation = EvaluationRecord(
        evaluation_id="evaluated",
        run_id="issued",
        actuals_snapshot_id="actuals",
        status="pending",
        metrics={},
        origin_count=0,
        assumptions=(),
    )
    ledger.append_evaluation(evaluation)
    original = ledger.get_watch("w")
    updated = ledger.advance_watch(
        "w", {"kind": "muted", "muted": True}, NOW, event_id="mute-1"
    )
    assert updated.muted
    reopened = Ledger(ledger.path)
    assert reopened.get_watch("w") == updated
    assert reopened.list_watches() == (updated,)
    history = reopened.watch_history("w")
    assert len(history) == 2
    assert history[0]["watch"] == original
    assert history[1]["watch"] == updated
    assert reopened.get_run("issued") == issued
    assert reopened.get_evaluation("evaluated") == evaluation
    assert reopened.get_candidate(original.candidate_id) == original.candidate
    assert (
        reopened.advance_watch(
            "w", {"kind": "muted", "muted": True}, NOW, event_id="mute-1"
        )
        == updated
    )
    assert len(reopened.watch_history("w")) == 2
    with pytest.raises(DomainError, match="idempotency_conflict"):
        reopened.advance_watch(
            "w", {"kind": "muted", "muted": False}, NOW, event_id="mute-1"
        )
    with sqlite3.connect(ledger.path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM watch_history")


def test_stored_transition_requires_ledger_validated_decision(tmp_path):
    ledger = stored_watch(tmp_path)
    w = ledger.get_watch("w")
    with pytest.raises(DomainError, match="unrecorded_eligibility_decision"):
        ledger.advance_watch(
            "w",
            {"kind": "evidence_qualified", "decision": decision(w)},
            NOW,
            event_id="fake",
        )
    assert len(ledger.watch_history("w")) == 1
    d = assess_candidate(
        w.candidate, (), ledger.get_discovery_epoch(w.candidate.epoch_id)
    )
    ledger.append_eligibility_decision(w.candidate_id, d)
    result = ledger.advance_watch(
        "w", {"kind": "evidence_qualified", "decision": d}, NOW, event_id="verified"
    )
    assert result.lifecycle == "evaluating"
    assert ledger.watch_history("w")[-1]["watch"].eligibility_decision == d


def qualified_stored_watch(tmp_path):
    ledger = Ledger(tmp_path / "qualified.db")
    c = candidate()
    ledger.put_snapshot(
        Snapshot(snapshot_id="snapshot-1", as_of=NOW, observations=(), assumptions=())
    )
    epoch = DiscoveryEpoch(
        epoch_id=c.epoch_id,
        source_snapshot_ids=("snapshot-1",),
        explored_candidate_ids=(c.candidate_id,),
        final_candidate_id=c.candidate_id,
        final_origin_ids=tuple(f"origin-{i}" for i in range(30)),
    )
    ledger.put_discovery_epoch(epoch, DiscoveryBudget())
    ledger.register_candidate(c)
    records = []
    for i, origin in enumerate(epoch.final_origin_ids):
        issued = run(f"issued-{i}", (i + 1,), ((1,),), snapshot_ids=("snapshot-1",))
        issued.results["forecast"] = issued.results["question"]
        issued.results["reference"] = issued.results["question"].model_copy(
            update={"point": ((2,),)}
        )
        ledger.append_run(issued, (), issued.run_id)
        target = NOW + timedelta(days=i + 1)
        actuals = Snapshot(
            snapshot_id=f"actuals-{i}",
            as_of=target,
            assumptions=(),
            observations=(
                Observation(
                    series_id="sales",
                    event_time=target,
                    available_at=target,
                    revision="1",
                    value=1,
                    unit="count",
                ),
            ),
        )
        ledger.put_snapshot(actuals)
        record = evaluate_run(issued, actuals, c.graph).model_copy(
            update={
                "discovery": EvaluationContext(
                    candidate_id=c.candidate_id,
                    protocol_id=c.protocol_id,
                    epoch_id=c.epoch_id,
                    origin_id=origin,
                    partition="final",
                    source_snapshot_ids=epoch.source_snapshot_ids,
                    target_start=target,
                    target_end=target,
                    temporal_valid=True,
                    semantic_valid=True,
                )
            }
        )
        ledger.append_evaluation(record)
        records.append(record)
    d = assess_candidate(c, tuple(records), epoch)
    assert d.action == "activate"
    ledger.append_eligibility_decision(c.candidate_id, d)
    ledger.put_watch(create_watch(c, watch_id="qualified", next_due_at=NOW), now=NOW)
    activated = ledger.advance_watch(
        "qualified",
        {
            "kind": "evidence_qualified",
            "decision": d,
            "next_due_at": NOW + timedelta(days=1),
        },
        NOW,
        event_id="qualification",
    )
    assert activated.operational
    return ledger, activated, records, d


def test_qualified_stored_evidence_activates_and_survives_revision_unchanged(tmp_path):
    ledger, activated, records, d = qualified_stored_watch(tmp_path)
    c = activated.candidate
    revised = ledger.advance_watch(
        "qualified",
        {
            "kind": "snapshot_revised",
            "snapshot_id": "snapshot-1",
            "revision": "snapshot-2",
        },
        NOW,
        event_id="revision",
    )
    assert not revised.operational
    with pytest.raises(DomainError, match="invalidated_watch_evidence"):
        ledger.advance_watch(
            "qualified",
            {"kind": "evidence_qualified", "decision": d},
            NOW,
            event_id="replay",
        )
    reopened = Ledger(ledger.path)
    assert reopened.get_evaluation(records[0].evaluation_id) == records[0]
    assert reopened.get_run("issued-0").results["question"].point == ((1,),)
    assert reopened.eligibility_decisions(c.candidate_id) == (d,)
    assert reopened.watch_history("qualified")[1]["watch"] == activated


@pytest.mark.parametrize("include_old_deadline", [False, True])
def test_durable_expired_decision_replay_cannot_restore_operational_watch(
    tmp_path, include_old_deadline
):
    ledger, activated, _, d = qualified_stored_watch(tmp_path)
    expired_at = activated.next_due_at
    stale = ledger.advance_watch(
        "qualified", {"kind": "refresh_expired"}, expired_at, event_id="expired"
    )
    history = ledger.watch_history("qualified")
    replay = {"kind": "evidence_qualified", "decision": d}
    if include_old_deadline:
        replay["next_due_at"] = activated.next_due_at
    with pytest.raises(DomainError, match="invalid_refresh_deadline"):
        ledger.advance_watch(
            "qualified", replay, expired_at, event_id="replayed-qualification"
        )
    reopened = Ledger(ledger.path)
    assert reopened.get_watch("qualified") == stale
    assert not reopened.get_watch("qualified").operational
    assert reopened.watch_history("qualified") == history
    future = expired_at + timedelta(days=1)
    for field in ("candidate_id", "protocol_id", "epoch_id", "policy_version"):
        with pytest.raises(DomainError, match="unrecorded_eligibility_decision"):
            reopened.advance_watch(
                "qualified",
                {
                    "kind": "evidence_qualified",
                    "decision": d.model_copy(update={field: "other"}),
                    "next_due_at": future,
                },
                expired_at,
                event_id=f"wrong-{field}",
            )
    restored = reopened.advance_watch(
        "qualified",
        {"kind": "evidence_qualified", "decision": d, "next_due_at": future},
        expired_at,
        event_id="valid-requalification",
    )
    assert restored.operational
    assert restored.next_due_at == future
    assert restored.eligibility_decision == d
    assert Ledger(ledger.path).watch_history("qualified")[-1]["watch"] == restored


def test_initial_watch_cannot_bypass_qualification_or_replace_history(tmp_path):
    ledger = stored_watch(tmp_path)
    w = ledger.get_watch("w")
    with pytest.raises(DomainError):
        ledger.put_watch(active_watch(watch_id="bypass"))
    with pytest.raises(DomainError):
        ledger.put_watch(w.model_copy(update={"muted": True}))
    assert ledger.get_watch("w") == w


def test_new_epoch_watch_links_to_predecessor_without_rebinding_it(tmp_path):
    ledger = stored_watch(tmp_path)
    old = ledger.advance_watch(
        "w",
        {
            "kind": "snapshot_revised",
            "snapshot_id": "snapshot-1",
            "revision": "snapshot-2",
        },
        NOW,
        event_id="revision",
    )
    new_candidate = candidate(epoch_id="epoch-2")
    ledger.put_snapshot(
        Snapshot(snapshot_id="snapshot-2", as_of=NOW, observations=(), assumptions=())
    )
    ledger.put_discovery_epoch(
        DiscoveryEpoch(
            epoch_id="epoch-2",
            source_snapshot_ids=("snapshot-2",),
            explored_candidate_ids=(new_candidate.candidate_id,),
            final_origin_ids=(),
        ),
        DiscoveryBudget(),
    )
    ledger.register_candidate(new_candidate)
    successor = create_watch(
        new_candidate, watch_id="successor", next_due_at=NOW, supersedes_watch_id="w"
    )
    ledger.put_watch(successor)
    reopened = Ledger(ledger.path)
    assert reopened.get_watch("successor").supersedes_watch_id == "w"
    assert reopened.get_watch("successor").candidate_id != old.candidate_id
    assert reopened.get_watch("w") == old
    assert len(reopened.watch_history("w")) == 2
    assert not reopened.get_watch("successor").operational


def test_watch_transition_rolls_back_when_history_write_fails(tmp_path):
    ledger = stored_watch(tmp_path)
    original = ledger.get_watch("w")
    with sqlite3.connect(ledger.path) as connection:
        connection.execute(
            "CREATE TRIGGER fail_watch_history BEFORE INSERT ON watch_history BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        ledger.advance_watch(
            "w", {"kind": "muted", "muted": True}, NOW, event_id="mute"
        )
    assert ledger.get_watch("w") == original
    assert len(ledger.watch_history("w")) == 1


def test_watch_creation_history_uses_creation_time_instead_of_refresh_deadline(
    tmp_path,
):
    ledger = stored_watch(tmp_path)
    later = create_watch(
        candidate(), watch_id="later", next_due_at=NOW + timedelta(days=7)
    )
    ledger.put_watch(later, now=NOW)
    assert ledger.watch_history("later")[0]["occurred_at"] == NOW


def test_unknown_or_unrelated_supersession_is_rejected(tmp_path):
    ledger = stored_watch(tmp_path)
    w = create_watch(
        candidate(), watch_id="same-candidate", next_due_at=NOW, supersedes_watch_id="w"
    )
    with pytest.raises(DomainError, match="invalid_watch_supersession"):
        ledger.put_watch(w)
    with pytest.raises(DomainError, match="missing_watch_predecessor"):
        ledger.put_watch(w.model_copy(update={"supersedes_watch_id": "missing"}))


def test_migration_upgrades_v3_and_preserves_ledger_records(tmp_path):
    from importlib.resources import files

    path = tmp_path / "v3.db"
    with sqlite3.connect(path) as connection:
        for migration in (
            "001_initial.sql",
            "002_evaluations.sql",
            "003_discovery.sql",
        ):
            connection.executescript(
                files("forecast_anything").joinpath("migrations", migration).read_text()
            )
        connection.execute(
            "INSERT INTO snapshots VALUES (?, ?)",
            (
                "old",
                Snapshot(
                    snapshot_id="old", as_of=NOW, observations=(), assumptions=()
                ).model_dump_json(),
            ),
        )
    ledger = Ledger(path)
    assert ledger.get_snapshot("old").snapshot_id == "old"
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == len(
            MIGRATIONS
        )
    assert Ledger(path).list_watches() == ()
