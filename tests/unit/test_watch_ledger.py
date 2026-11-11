"""Durable watch qualification, history and migrations."""

import sqlite3
from datetime import timedelta

import pytest
from watch_fixtures import NOW, active_watch, candidate, decision, run, watch

from forecast_anything.contracts import (
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EvaluationContext,
    EvaluationRecord,
    Observation,
    Snapshot,
)
from forecast_anything.discovery.policy import assess_candidate
from forecast_anything.evaluation.records import evaluate_run
from forecast_anything.store import MIGRATIONS, Ledger
from forecast_anything.watches import (
    create_watch,
)


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
    with (
        sqlite3.connect(ledger.path) as connection,
        pytest.raises(sqlite3.IntegrityError),
    ):
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


def test_watch_history_offset_beyond_sqlite_range_is_empty(tmp_path):
    ledger = stored_watch(tmp_path)
    assert ledger.watch_history_page("w", offset=2**100) == ((), None)
