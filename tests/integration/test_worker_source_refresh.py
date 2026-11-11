"""Source refresh and incremental worker execution."""

from datetime import timedelta
from typing import ClassVar

import pytest
from worker_fixtures import T, inputs, payload, registered_watch, setup

from forecast_anything.jobs import JobQueue
from forecast_anything.worker import Worker


def test_same_source_change_only_recomputes_descendants(tmp_path):
    _ledger, provider, runtime = setup(tmp_path)
    graph, snapshots = inputs()
    first = runtime.run(graph, snapshots, T, "initial")
    changed = snapshots["a"].model_dump()
    changed["observations"][-1]["value"] = 100
    changed["snapshot_id"] = "revised-a"
    from forecast_anything.contracts import Snapshot

    snapshots["a"] = Snapshot.model_validate(changed)
    second = runtime.run(graph, snapshots, T, "refresh", previous_run_id=first.run_id)
    assert provider.calls == ["a", "b", "a"]
    assert second.results["f_a"].point == ((100,),)
    assert second.results["f_b"] == first.results["f_b"]
    assert second.parent_run_id == first.run_id


def test_due_watch_expires_before_resume_and_coalesces_source_refresh(tmp_path):
    ledger, _, runtime = setup(tmp_path)
    _, registered = registered_watch(tmp_path, ledger)
    ledger.advance_watch(
        "watch", {"kind": "paused"}, T - timedelta(hours=1), event_id="pause"
    )
    queue = JobQueue(ledger)
    worker = Worker(runtime, queue)
    result = worker.resume_watch("watch", T, event_id="resume")
    assert result.lifecycle == "evaluating"
    assert result.quality == "stale"
    assert not result.operational
    assert [h["event"]["kind"] for h in ledger.watch_history("watch")] == [
        "created",
        "paused",
        "refresh_expired",
        "resumed",
    ]
    assert worker.run_due(T, limit=1)
    assert ledger.get_watch("watch").quality == "stale"
    assert worker.run_due(T + timedelta(seconds=1), limit=1) == ()
    assert registered.spec.source_id == "sales"


def test_source_refresh_creates_new_epoch_and_preserves_old_watch(tmp_path):
    ledger, _, runtime = setup(tmp_path)
    csv, registered = registered_watch(tmp_path, ledger)
    csv.write_text("time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,9\n")
    old = ledger.get_watch("watch")
    queue = JobQueue(ledger)
    queue.enqueue(
        f"refresh/sales/{registered.revision}/manual",
        {
            "kind": "source_refresh",
            "source_id": "sales",
            "revision": registered.revision,
            "as_of": T.isoformat(),
        },
    )
    Worker(runtime, queue).run_due(T)
    watches = ledger.list_watches()
    assert len(watches) == 2
    fresh = next(w for w in watches if w.watch_id != "watch")
    assert fresh.supersedes_watch_id == "watch"
    assert fresh.candidate.epoch_id != old.candidate.epoch_id
    assert fresh.candidate_id != old.candidate_id
    assert not fresh.operational
    assert ledger.get_watch("watch").candidate == old.candidate
    assert ledger.get_watch("watch").candidate_invalidated
    assert (
        ledger.get_discovery_epoch("original").source_snapshot_ids
        == old.source_snapshot_ids
    )
    assert ledger.discovery_usage(fresh.candidate.epoch_id)[0] == 1
    assert ledger.discovery_usage("original") == (1, 0)


def test_append_replay_recovers_run_after_crash_before_enqueue(tmp_path, monkeypatch):
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
    )
    from forecast_anything.operators import register_builtin_operators

    ledger, _, runtime = setup(tmp_path)
    runtime.operators = register_builtin_operators()
    csv, registered = registered_watch(tmp_path, ledger, due=T)
    watch = ledger.get_watch("watch")
    question = ledger.create_question(
        QuestionCreateRequest(
            key="append-crash",
            title="Sales outlook",
            meaning="Forecast daily sales",
            source_ids=("sales",),
            selection={"provider": "seasonal_naive", "horizon": 1},
        )
    )
    ledger.link_question_reference(
        question.question_id,
        QuestionReferenceRequest(
            key="watch-reference",
            revision=1,
            target_type="watch",
            target_id=watch.watch_id,
        ),
    )
    csv.write_text(
        "time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n2026-10-24,4\n"
    )
    queue = JobQueue(ledger)
    queue.enqueue(
        f"refresh/sales/{registered.revision}/append-crash",
        {
            "kind": "source_refresh",
            "source_id": "sales",
            "revision": registered.revision,
            "as_of": T.isoformat(),
        },
    )
    enqueue = queue.enqueue

    def crash_before_run(key, payload, **kwargs):
        if key.startswith("watch-run/"):
            raise KeyboardInterrupt("crash after append transition")
        return enqueue(key, payload, **kwargs)

    monkeypatch.setattr(queue, "enqueue", crash_before_run)
    with pytest.raises(KeyboardInterrupt, match="append transition"):
        Worker(runtime, queue).run_due(T, limit=1)
    assert (
        ledger.get_watch(watch.watch_id).source_snapshot_ids[-1]
        != (watch.source_snapshot_ids[-1])
    )
    assert ledger.list_inbox_events(question_id=question.question_id).total_count == 0

    monkeypatch.setattr(queue, "enqueue", enqueue)
    recovered_at = T + timedelta(seconds=61)
    ledger.clock = runtime.clock = lambda: recovered_at
    Worker(runtime, queue).run_due(recovered_at)

    references = ledger.list_question_references(question.question_id, revision=1)
    run_references = [
        reference
        for reference in references.references
        if reference.target_type == "run"
    ]
    assert len(run_references) == 1
    assert any(
        event.event_kind == "forecast_issued"
        for event in ledger.list_inbox_events(question_id=question.question_id).events
    )


def test_valid_append_preserves_watch_and_links_new_provisional_run_to_question(
    tmp_path,
):
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
    )
    from forecast_anything.sources.catalog import SourceCatalog

    ledger, _, runtime = setup(tmp_path)
    from forecast_anything.operators import register_builtin_operators

    runtime.operators = register_builtin_operators()
    csv, registered = registered_watch(tmp_path, ledger, due=T + timedelta(days=1))
    old = ledger.get_watch("watch")
    question = ledger.create_question(
        QuestionCreateRequest(
            key="saved-sales",
            title="Sales outlook",
            meaning="Forecast daily sales",
            source_ids=("sales",),
            selection={"provider": "seasonal_naive", "horizon": 1},
        )
    )
    ledger.link_question_reference(
        question.question_id,
        QuestionReferenceRequest(
            key="watch-v1",
            revision=1,
            target_type="watch",
            target_id=old.watch_id,
        ),
    )
    csv.write_text(
        "time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n2026-10-24,4\n"
    )
    current_revision = SourceCatalog(ledger.path).get("sales").revision
    assert current_revision == registered.revision

    queue = JobQueue(ledger)
    queue.enqueue(
        f"refresh/sales/{registered.revision}/append",
        {
            "kind": "source_refresh",
            "source_id": "sales",
            "revision": registered.revision,
            "as_of": T.isoformat(),
        },
    )
    Worker(runtime, queue).run_due(T)

    watches = ledger.list_watches()
    updated = ledger.get_watch(old.watch_id)
    references = ledger.list_question_references(question.question_id, revision=1)
    run_refs = [ref for ref in references.references if ref.target_type == "run"]
    assert len(watches) == 1
    assert updated.candidate_id == old.candidate_id
    assert updated.quality == "provisional"
    assert not updated.evidence_applicable
    assert updated.source_snapshot_ids[-1] != old.source_snapshot_ids[-1]
    assert len(run_refs) == 1
    run = ledger.get_run(run_refs[0].target_id)
    assert run.snapshot_ids
    events = ledger.list_inbox_events(question_id=question.question_id)
    forecast_events = [
        event for event in events.events if event.event_kind == "forecast_issued"
    ]
    assert len(forecast_events) == 1
    assert forecast_events[0].run_id == run.run_id


def test_queued_source_change_recomputes_only_descendant_operators(tmp_path):
    from forecast_anything.operators import register_builtin_operators

    ledger, provider, runtime = setup(tmp_path)
    operator = register_builtin_operators()["sum_aligned"]

    class CountingOperator:
        calls: ClassVar[list] = []

        def contract(self):
            return operator.contract()

        def apply(self, inputs, parameters):
            self.calls.append(inputs["value"].series_ids[0])
            return operator.apply(inputs, parameters)

    counted = CountingOperator()
    runtime.operators = {"sum_aligned": counted}
    p = payload()
    p["graph"]["nodes"].extend(
        {
            "node_id": f"total_{name}",
            "kind": "transform",
            "inputs": [f"f_{name}"],
            "config": {
                "operator": "sum_aligned",
                "parameters": {"bindings": {"value": f"f_{name}"}},
                "relation_type": {f"f_{name}": "accounting"},
            },
        }
        for name in ("a", "b")
    )
    queue = JobQueue(ledger)
    job = queue.enqueue("run/initial", p)
    Worker(runtime, queue).run_due(T)
    first = queue.history(job.job_id)[0]["result"]["run_id"]
    p["previous_run_id"] = first
    p["snapshots"]["a"]["snapshot_id"] = "changed-a"
    p["snapshots"]["a"]["observations"][-1]["value"] = 100
    updated = queue.enqueue("run/update", p)
    Worker(runtime, queue).run_due(T)
    current = ledger.get_run(queue.history(updated.job_id)[0]["result"]["run_id"])
    assert provider.calls == ["a", "b", "a"]
    assert counted.calls == ["a", "b", "a"]
    assert current.results["total_a"].point == ((100,),)
    assert current.results["total_b"].point == ((3,),)


def test_runtime_completed_runs_produce_a_selective_update_summary(tmp_path):
    from forecast_anything.contracts import Snapshot
    from forecast_anything.watches import summarize_change

    _, _, runtime = setup(tmp_path)
    graph, snapshots = inputs()
    first = runtime.run(graph, snapshots, T, "initial")
    changed = snapshots["a"].model_dump()
    changed["snapshot_id"] = "revised-a"
    changed["observations"][-1]["value"] = 100
    snapshots["a"] = Snapshot.model_validate(changed)
    second = runtime.run(graph, snapshots, T, "revised", previous_run_id=first.run_id)
    summary = summarize_change(first, second)
    assert summary["changes"] == [
        {
            "node_id": "f_a",
            "series_id": "a",
            "timestamp": T.isoformat(),
            "representation": "point",
            "previous": 3.0,
            "current": 100.0,
            "delta": 97.0,
            "unit": "count",
        }
    ]
