from datetime import UTC, datetime, timedelta

from forecast_anything.continuity import classify_snapshot_change
from forecast_anything.contracts import (
    EligibilityDecision,
    Observation,
    Snapshot,
    SourceProfile,
)
from forecast_anything.discovery.candidates import CandidateProposal, compile_proposal
from forecast_anything.watches import advance_watch, create_watch

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def _row(day: int, value: float, *, available_day: int | None = None, revision="1"):
    return Observation(
        series_id="sales",
        event_time=datetime(2026, 10, day, tzinfo=UTC),
        available_at=datetime(2026, 10, available_day or day, tzinfo=UTC),
        revision=revision,
        value=value,
        unit="count",
    )


def _snapshot(identity: str, rows, *, as_of=NOW):
    return Snapshot(
        snapshot_id=identity,
        as_of=as_of,
        observations=tuple(rows),
        assumptions=(),
    )


def _active_watch(**changes):
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
    candidate = compile_proposal(
        CandidateProposal(
            template_id="forecast_change", source_ids=("sales",), reason="Review sales"
        ),
        (profile,),
        epoch_id="epoch",
    )
    watch = create_watch(
        candidate,
        watch_id="watch-1",
        next_due_at=NOW + timedelta(days=1),
        source_snapshot_ids=("before",),
    )
    decision = EligibilityDecision(
        action="activate",
        reason_codes=("qualified_final_evidence",),
        candidate_id=watch.candidate_id,
        protocol_id=candidate.protocol_id,
        epoch_id=candidate.epoch_id,
        evaluation_ids=("evaluation",),
        policy_version=watch.policy_version,
    )
    active = advance_watch(
        watch, {"kind": "evidence_qualified", "decision": decision}, NOW
    )
    return active.model_copy(update=changes)


def test_snapshot_change_classifies_identical_data_and_strict_append():
    previous = _snapshot("before", [_row(1, 1), _row(2, 2)])

    unchanged = classify_snapshot_change(
        previous, _snapshot("same-data", previous.observations), NOW
    )
    appended = classify_snapshot_change(
        previous,
        _snapshot("after", [*previous.observations, _row(3, 3)]),
        NOW,
    )

    assert unchanged.kind == "unchanged"
    assert appended.kind == "append"
    assert appended.added_count == 1


def test_snapshot_change_invalidates_historical_availability_mutation():
    previous = _snapshot("before", [_row(1, 1), _row(2, 2)])
    revised = _snapshot("after", [_row(1, 1, available_day=3), _row(2, 2)])

    change = classify_snapshot_change(previous, revised, NOW)

    assert change.kind == "historical_availability_altered"
    assert change.added_count == 0


def test_snapshot_change_invalidates_value_revision_and_deletion_mutations():
    previous = _snapshot("before", [_row(1, 1), _row(2, 2)])

    corrected = classify_snapshot_change(
        previous,
        _snapshot("corrected", [_row(1, 9, revision="2"), _row(2, 2)]),
        NOW,
    )
    deleted = classify_snapshot_change(
        previous, _snapshot("deleted", [_row(1, 1)]), NOW
    )

    assert corrected.kind == "historical_correction"
    assert deleted.kind == "historical_deletion"


def test_snapshot_change_rejects_late_rows_and_mapping_changes_as_append():
    previous = _snapshot("before", [_row(1, 1), _row(3, 3)])

    late = classify_snapshot_change(
        previous,
        _snapshot("late", [*previous.observations, _row(2, 2)]),
        NOW,
    )
    mapping = classify_snapshot_change(
        previous,
        _snapshot("mapping", [*previous.observations, _row(4, 4)]),
        NOW,
        mapping_unchanged=False,
    )

    assert late.kind == "historical_correction"
    assert mapping.kind == "mapping_changed"


def test_data_appended_keeps_candidate_but_marks_watch_provisional():
    watch = _active_watch(last_run_id="run-1")
    due = NOW + timedelta(hours=3)
    qualification_due = NOW + timedelta(minutes=15)

    updated = advance_watch(
        watch,
        {
            "kind": "data_appended",
            "source_id": "sales",
            "snapshot_id": "after",
            "next_due_at": due,
            "requalification_due_at": qualification_due,
        },
        NOW,
    )

    assert updated.watch_id == watch.watch_id
    assert updated.candidate_id == watch.candidate_id
    assert updated.source_snapshot_ids == ("before", "after")
    assert updated.last_run_id == "run-1"
    assert (updated.lifecycle, updated.quality, updated.evidence_applicable) == (
        "evaluating",
        "provisional",
        False,
    )
    assert updated.next_due_at == due
    assert updated.requalification_due_at == qualification_due


def test_historical_availability_change_invalidates_applicable_evidence():
    watch = _active_watch()

    updated = advance_watch(
        watch,
        {"kind": "historical_availability_altered", "source_id": "sales"},
        NOW,
    )

    assert updated.candidate_id == watch.candidate_id
    assert updated.candidate_invalidated is True
    assert updated.invalidated_evaluation_ids == ("evaluation",)
    assert updated.evidence_applicable is False
    assert updated.quality == "provisional"


def test_horizon_expiry_does_not_rewrite_historical_qualification():
    watch = _active_watch(forecast_horizon_end=NOW - timedelta(seconds=1))

    expired = advance_watch(watch, {"kind": "horizon_expired"}, NOW)

    assert expired.quality == "stale"
    assert expired.evidence_applicable is True
    assert expired.eligibility_decision == watch.eligibility_decision
    assert expired.quality_reason == "horizon_expired"
