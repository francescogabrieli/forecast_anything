"""Durable work, fencing, selective replay and restart fault boundaries."""

from datetime import datetime, timedelta, timezone

import pytest

from forecast_anything.contracts import DomainError, GraphSpec, Node, Observation
from forecast_anything.jobs import JobQueue, LeaseGuard
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze
from forecast_anything.worker import Worker

T = datetime(2026, 10, 24, tzinfo=timezone.utc)


class CountingProvider(SeasonalNaiveProvider):
    def __init__(self):
        super().__init__(1)
        self.calls = []
        self.fail = False

    def forecast(self, request):
        self.calls.append(request.snapshot.observations[0].series_id)
        if self.fail:
            raise RuntimeError("offline")
        return super().forecast(request)


def inputs():
    nodes, snapshots = [], {}
    for source in ("a", "b"):
        snapshots[source] = freeze(
            tuple(
                Observation(
                    series_id=source,
                    event_time=T - timedelta(hours=3 - i),
                    available_at=T,
                    revision="1",
                    value=i + 1,
                    unit="count",
                )
                for i in range(3)
            ),
            T,
        )
        nodes.extend(
            (
                Node(
                    node_id=source,
                    kind="source",
                    inputs=(),
                    config={
                        "source_id": source,
                        "series_ids": [source],
                        "units": ["count"],
                        "frequency": "1h",
                    },
                ),
                Node(
                    node_id=f"f_{source}",
                    kind="forecast",
                    inputs=(source,),
                    config={
                        "provider": "seasonal_naive",
                        "history": source,
                        "horizon": 1,
                        "frequency": "1h",
                        "options": {"period": 1},
                        "relation_type": {source: "statistical"},
                    },
                ),
            )
        )
    return GraphSpec(graph_id="two-branches", version=1, nodes=tuple(nodes)), snapshots


def setup(tmp_path, clock=None):
    ledger = Ledger(tmp_path / "state.db", clock=clock or (lambda: T))
    provider = CountingProvider()
    return (
        ledger,
        provider,
        Runtime(ledger, {"seasonal_naive": provider}, {}, clock or (lambda: T)),
    )


def payload():
    graph, snapshots = inputs()
    return {
        "kind": "run",
        "graph": graph.model_dump(mode="json"),
        "snapshots": {k: v.model_dump(mode="json") for k, v in snapshots.items()},
        "as_of": T.isoformat(),
    }


def test_job_key_is_idempotent(tmp_path):
    queue = JobQueue(Ledger(tmp_path / "state.db"))
    assert queue.enqueue("refresh/s/1", {"source_id": "s"}).job_id == (
        queue.enqueue("refresh/s/1", {"source_id": "s"}).job_id
    )
    with pytest.raises(DomainError, match="idempotency_conflict"):
        queue.enqueue("refresh/s/1", {"source_id": "changed"})


def test_restart_recovers_pending_job(tmp_path):
    ledger, _, _ = setup(tmp_path)
    job = JobQueue(ledger).enqueue("run/1", payload())
    ledger, provider, runtime = setup(tmp_path)
    queue = JobQueue(ledger)
    assert Worker(runtime, queue).run_due(T) == (job.job_id,)
    assert queue.get(job.job_id).state == "completed"
    assert provider.calls == ["a", "b"]
    assert Worker(runtime, queue).run_due(T) == ()


def test_automatic_requalification_deadline_triggers_worker_timeout_handler(
    tmp_path, monkeypatch
):
    from threading import Event
    from time import sleep

    ledger, _, runtime = setup(tmp_path)
    queue = JobQueue(ledger)
    deadline = T + timedelta(milliseconds=20)
    job = queue.enqueue(
        "slow-automatic-requalification",
        {
            "kind": "backtest",
            "automatic_requalification": True,
            "execution_budget_seconds": 1,
            "execution_deadline_at": deadline.isoformat(),
        },
    )
    expired = Event()
    worker = Worker(
        runtime,
        queue,
        execution_timeout_handler=expired.set,
    )
    monkeypatch.setattr(worker, "_execute", lambda *_: sleep(0.06) or {})

    worker.run_due(T)

    assert expired.is_set()
    assert queue.get(job.job_id).state == "failed"
    assert queue.history(job.job_id)[0]["error"]["code"] == (
        "backtest_time_budget_exceeded"
    )


def test_expired_owner_cannot_commit(tmp_path):
    now = [T]
    ledger, provider, runtime = setup(tmp_path, lambda: now[0])
    queue = JobQueue(ledger)
    job = queue.enqueue("run/1", payload())
    old = queue.claim("old", T, 60)
    now[0] = T + timedelta(seconds=60)
    with pytest.raises(DomainError, match="lease_lost"):
        runtime.run(
            *inputs(),
            T,
            "emission",
            lease_guard=LeaseGuard(job.job_id, old.lease_token),
        )
    assert ledger.get_run_by_key("emission") is None
    assert ledger.events_after(0) == ()
    current = queue.claim("new", now[0], 60)
    assert current.attempt == old.attempt
    assert current.lease_token != old.lease_token
    with pytest.raises(DomainError, match="lease_lost"):
        queue.complete(old, now[0])
    # An already expired guard now rejects graph/snapshot writes before inference.
    assert provider.calls == []


def test_same_source_change_only_recomputes_descendants(tmp_path):
    ledger, provider, runtime = setup(tmp_path)
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


def test_retry_and_outbox_do_not_duplicate_completed_run(tmp_path, monkeypatch):
    ledger, provider, runtime = setup(tmp_path)
    queue = JobQueue(ledger)
    job = queue.enqueue("run/1", payload())
    original = queue.complete

    def crash(*args, **kwargs):
        raise KeyboardInterrupt("power loss after run commit")

    monkeypatch.setattr(queue, "complete", crash)
    with pytest.raises(KeyboardInterrupt):
        Worker(runtime, queue).run_due(T)
    assert len([e for e in ledger.events_after(0) if e.kind == "run_completed"]) == 1
    monkeypatch.setattr(queue, "complete", original)
    runtime.clock = lambda: T + timedelta(seconds=61)
    ledger.clock = runtime.clock
    assert Worker(runtime, JobQueue(ledger)).run_due(runtime.clock()) == (job.job_id,)
    assert provider.calls == ["a", "b"]
    assert len([e for e in ledger.events_after(0) if e.kind == "run_completed"]) == 1


def test_failed_attempt_has_new_emission_and_preserved_history(tmp_path):
    ledger, provider, runtime = setup(tmp_path)
    queue = JobQueue(ledger)
    job = queue.enqueue("run/1", payload())
    provider.fail = True
    assert Worker(runtime, queue).run_due(T) == (job.job_id,)
    assert queue.get(job.job_id).attempt == 2
    assert Worker(runtime, queue).run_due(T) == ()
    provider.fail = False
    runtime.clock = lambda: T + timedelta(seconds=30)
    ledger.clock = runtime.clock
    Worker(runtime, queue).run_due(runtime.clock())
    assert queue.get(job.job_id).state == "completed"
    assert [a["state"] for a in queue.history(job.job_id)] == ["failed", "completed"]
    assert len([e for e in ledger.events_after(0) if e.kind == "run_failed"]) == 1
    assert len([e for e in ledger.events_after(0) if e.kind == "run_completed"]) == 1


def test_before_commit_crash_leaves_no_run_or_outbox(tmp_path, monkeypatch):
    ledger, _, runtime = setup(tmp_path)
    queue = JobQueue(ledger)
    queue.enqueue("run/1", payload())
    original = ledger.append_run

    def crash(*args, **kwargs):
        raise KeyboardInterrupt("power loss before commit")

    monkeypatch.setattr(ledger, "append_run", crash)
    with pytest.raises(KeyboardInterrupt):
        Worker(runtime, queue).run_due(T)
    assert ledger.events_after(0) == ()
    monkeypatch.setattr(ledger, "append_run", original)
    runtime.clock = lambda: T + timedelta(seconds=61)
    ledger.clock = runtime.clock
    Worker(runtime, queue).run_due(runtime.clock())
    assert len([e for e in ledger.events_after(0) if e.kind == "run_completed"]) == 1


def registered_watch(
    tmp_path, ledger, due=T, templates=("forecast_change",), final_origins=()
):
    from forecast_anything.contracts import DiscoveryBudget, DiscoveryEpoch, SourceSpec
    from forecast_anything.discovery.candidates import (
        CandidateProposal,
        compile_proposal,
    )
    from forecast_anything.sources.catalog import SourceCatalog
    from forecast_anything.sources.profiling import ingest_source, inspect_source
    from forecast_anything.watches import create_watch

    csv = tmp_path / "sales.csv"
    csv.write_text("time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n")
    spec = SourceSpec(
        source_id="sales",
        kind="csv",
        location=str(csv),
        refresh_seconds=120,
        mapping={
            "event_time": "time",
            "available_at": "time",
            "value": "value",
            **{
                k: {"constant": v}
                for k, v in {
                    "series_id": "sales",
                    "unit": "count",
                    "revision": "1",
                    "frequency": "D",
                    "calendar": "gregorian",
                    "timezone": "UTC",
                    "missing_values": [],
                }.items()
            },
        },
    )
    registered = SourceCatalog(ledger.path).append(spec)
    snap = ingest_source(spec, T)
    ledger.put_snapshot(snap)
    candidates = tuple(
        compile_proposal(
            CandidateProposal(
                template_id=template, source_ids=("sales",), reason="Review"
            ),
            (inspect_source(spec),),
            epoch_id="original",
        )
        for template in templates
    )
    ledger.put_discovery_epoch(
        DiscoveryEpoch(
            epoch_id="original",
            source_snapshot_ids=(snap.snapshot_id,),
            explored_candidate_ids=tuple(c.candidate_id for c in candidates),
            final_origin_ids=final_origins,
            final_candidate_id=candidates[0].candidate_id if final_origins else None,
        ),
        DiscoveryBudget(max_candidates=len(candidates), max_tool_calls=3),
    )
    for index, c in enumerate(candidates):
        ledger.register_candidate(c)
        ledger.put_watch(
            create_watch(
                c, watch_id="watch" if index == 0 else f"watch-{index}", next_due_at=due
            ),
            now=T - timedelta(days=1),
        )
    return csv, registered


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


def test_historical_correction_keeps_question_linked_to_successor_and_run(tmp_path):
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
    )
    from forecast_anything.operators import register_builtin_operators

    ledger, _, runtime = setup(tmp_path)
    runtime.operators = register_builtin_operators()
    csv, registered = registered_watch(tmp_path, ledger, due=T)
    old = ledger.get_watch("watch")
    question = ledger.create_question(
        QuestionCreateRequest(
            key="correction-continuity",
            title="Sales outlook",
            meaning="Forecast daily sales",
            source_ids=("sales",),
            selection={"provider": "seasonal_naive", "horizon": 1},
        )
    )
    ledger.link_question_reference(
        question.question_id,
        QuestionReferenceRequest(
            key="old-watch",
            revision=1,
            target_type="watch",
            target_id=old.watch_id,
        ),
    )
    csv.write_text("time,value\n2026-10-21,1\n2026-10-22,99\n2026-10-23,3\n")
    queue = JobQueue(ledger)
    queue.enqueue(
        f"refresh/sales/{registered.revision}/correction",
        {
            "kind": "source_refresh",
            "source_id": "sales",
            "revision": registered.revision,
            "as_of": T.isoformat(),
        },
    )

    Worker(runtime, queue).run_due(T, limit=20)

    successor = next(
        watch
        for watch in ledger.list_watches()
        if watch.supersedes_watch_id == old.watch_id
    )
    references = ledger.list_question_references(question.question_id, revision=1)
    assert any(
        reference.target_type == "watch" and reference.target_id == successor.watch_id
        for reference in references.references
    )
    run_references = [
        reference
        for reference in references.references
        if reference.target_type == "run"
    ]
    assert run_references
    run = ledger.get_run(run_references[-1].target_id)
    assert run.snapshot_ids == (successor.source_snapshot_ids[-1],)
    event_kinds = {
        event.event_kind
        for event in ledger.list_inbox_events(question_id=question.question_id).events
    }
    assert "historical_correction" in event_kinds
    assert "forecast_issued" in event_kinds


def test_all_paused_watches_stop_shared_source_polling(tmp_path):
    from forecast_anything.api.service import Observatory
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
        QuestionTitlePatch,
    )

    ledger, _, runtime = setup(tmp_path)
    registered_watch(tmp_path, ledger, due=T)
    question_ids = []
    for index in range(2):
        question = ledger.create_question(
            QuestionCreateRequest(
                key=f"paused-{index}",
                title=f"Question {index}",
                meaning="Forecast daily sales",
                source_ids=("sales",),
                selection={"provider": "seasonal_naive", "horizon": 1},
            )
        )
        ledger.link_question_reference(
            question.question_id,
            QuestionReferenceRequest(
                key=f"watch-{index}",
                revision=1,
                target_type="watch",
                target_id="watch",
            ),
        )
        question_ids.append(question.question_id)
    service = Observatory(ledger, runtime)
    for question_id in question_ids:
        service.patch_question(question_id, QuestionTitlePatch(status="paused"))

    Worker(runtime, JobQueue(ledger)).run_due(T)

    with ledger._connection() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM jobs WHERE json_extract(payload, '$.kind') = 'source_refresh'"
            ).fetchone()[0]
            == 0
        )


def test_source_revocation_notifies_questions_and_suppresses_queued_run(tmp_path):
    from forecast_anything.api.service import Observatory
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
    )
    from forecast_anything.operators import register_builtin_operators

    ledger, _, runtime = setup(tmp_path)
    runtime.operators = register_builtin_operators()
    _, _ = registered_watch(tmp_path, ledger)
    watch = ledger.get_watch("watch")
    question = ledger.create_question(
        QuestionCreateRequest(
            key="revocation-notice",
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
    snapshot_id = watch.source_snapshot_ids[-1]
    queue = JobQueue(ledger)
    job = queue.enqueue(
        "queued-run-before-revocation",
        {
            "kind": "run",
            "watch_id": watch.watch_id,
            "graph": watch.candidate.graph.model_dump(mode="json"),
            "snapshots": {
                "sales": ledger.get_snapshot(snapshot_id).model_dump(mode="json")
            },
            "as_of": T.isoformat(),
            "question_links": (
                {
                    "question_id": question.question_id,
                    "revision": 1,
                    "priority": 3,
                },
            ),
        },
    )

    Observatory(ledger, runtime).set_source_subscription("sales", active=False)
    Worker(runtime, queue).run_due(T)

    assert ledger.get_run_by_key(job.emission_key) is None
    event = ledger.list_inbox_events(question_id=question.question_id).events[0]
    assert event.event_kind == "source_subscription_revoked"
    assert queue.get(job.job_id).state == "completed"
    assert queue.history(job.job_id)[0]["result"]["suppressed"] == "watch_not_active"


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


def test_automatic_requalification_uses_30_fresh_origins_and_resolves_question(
    tmp_path,
):
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
    )
    from forecast_anything.operators import register_builtin_operators

    ledger, _, runtime = setup(tmp_path)
    runtime.operators = register_builtin_operators()
    qualify_watch(tmp_path, ledger)
    from forecast_anything.sources.catalog import SourceCatalog

    csv = tmp_path / "sales.csv"
    registered = SourceCatalog(ledger.path).get("sales")
    original_qualification_snapshot = ledger.get_watch(
        "watch"
    ).qualification_snapshot_id
    question = ledger.create_question(
        QuestionCreateRequest(
            key="saved-sales-requal",
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
            target_id="watch",
        ),
    )
    base = T - timedelta(days=3)
    csv.write_text(
        "time,value\n"
        + "".join(
            f"{(base + timedelta(days=index)).date().isoformat()},{value}\n"
            for index, value in enumerate(
                [1, 2, 3] + [2 if index % 2 == 1 else 5 for index in range(3, 141)]
            )
        )
    )
    now = T + timedelta(days=141)
    ledger.clock = lambda: now
    runtime.clock = lambda: now
    queue = JobQueue(ledger)
    queue.enqueue(
        f"refresh/sales/{registered.revision}/requalify",
        {
            "kind": "source_refresh",
            "source_id": "sales",
            "revision": registered.revision,
            "as_of": now.isoformat(),
        },
    )

    Worker(runtime, queue).run_due(now, limit=10)

    updated = ledger.get_watch("watch")
    assert updated.eligibility_decision.action == "activate"
    assert updated.evidence_applicable is True
    assert updated.qualification_snapshot_id is not None
    assert updated.qualification_snapshot_id != original_qualification_snapshot
    references = ledger.list_question_references(question.question_id, revision=1)
    reports = [ref for ref in references.references if ref.target_type == "backtest"]
    assert len(reports) == 1
    from forecast_anything.backtesting.store import BacktestStore

    plan = BacktestStore(ledger).get_plan(reports[0].target_id)
    fresh_final = [origin for origin in plan.origins if origin.partition == "final"]
    assert len(fresh_final) >= 30
    assert all(origin.target_start > plan.origin_target_after for origin in fresh_final)
    assert ledger.list_inbox_events(question_id=question.question_id).total_count >= 3
    with ledger._connection() as connection:
        budget_count = connection.execute(
            "SELECT count(*) FROM requalification_budgets WHERE question_id = ?",
            (question.question_id,),
        ).fetchone()[0]
    assert budget_count == 1


def _provisional_requalification_case(tmp_path, *, appended_days):
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
    )
    from forecast_anything.operators import register_builtin_operators
    from forecast_anything.sources.catalog import SourceCatalog
    from forecast_anything.sources.profiling import ingest_source

    ledger, _, runtime = setup(tmp_path)
    runtime.operators = register_builtin_operators()
    qualify_watch(tmp_path, ledger)
    question = ledger.create_question(
        QuestionCreateRequest(
            key=f"requalification-{appended_days}",
            title="Sales outlook",
            meaning="Forecast daily sales",
            source_ids=("sales",),
            selection={"provider": "seasonal_naive", "horizon": 1},
        )
    )
    ledger.link_question_reference(
        question.question_id,
        QuestionReferenceRequest(
            key="watch-link",
            revision=1,
            target_type="watch",
            target_id="watch",
        ),
    )
    registered = SourceCatalog(ledger.path).get("sales")
    csv = tmp_path / "sales.csv"
    base = T - timedelta(days=3)
    values = [1, 2, 3] + [2 if index % 2 else 5 for index in range(3, appended_days)]
    csv.write_text(
        "time,value\n"
        + "".join(
            f"{(base + timedelta(days=index)).date().isoformat()},{value}\n"
            for index, value in enumerate(values)
        )
    )
    now = T + timedelta(days=appended_days)
    snapshot = ingest_source(registered.spec, now)
    ledger.put_snapshot(snapshot)
    ledger.advance_watch(
        "watch",
        {
            "kind": "data_appended",
            "source_id": "sales",
            "snapshot_id": snapshot.snapshot_id,
            "next_due_at": now + timedelta(days=1),
            "requalification_due_at": now,
        },
        now,
        event_id=f"test-append/{snapshot.snapshot_id}",
    )
    return ledger, runtime, question, now


def test_automatic_requalification_waits_when_fewer_than_30_final_origins_exist(
    tmp_path,
):
    ledger, runtime, question, now = _provisional_requalification_case(
        tmp_path, appended_days=4
    )
    worker = Worker(runtime, JobQueue(ledger))

    worker._schedule_requalifications(now)

    assert ledger.get_watch("watch").requalification_reason == (
        "insufficient_new_final_origins"
    )
    assert ledger.get_watch("watch").requalification_new_origins < 30
    assert (
        ledger.list_inbox_events(question_id=question.question_id)
        .events[0]
        .payload["reason"]
        == "insufficient_new_final_origins"
    )
    with ledger._connection() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM requalification_budgets WHERE question_id = ?",
                (question.question_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM jobs WHERE json_extract(payload, '$.automatic_requalification') = 1"
            ).fetchone()[0]
            == 0
        )


def test_automatic_requalification_budget_allows_one_job_per_question_in_24_hours(
    tmp_path,
):
    ledger, runtime, question, now = _provisional_requalification_case(
        tmp_path, appended_days=141
    )
    worker = Worker(runtime, JobQueue(ledger))

    worker._schedule_requalifications(now)
    from forecast_anything.sources.catalog import SourceCatalog
    from forecast_anything.sources.profiling import ingest_source

    source = SourceCatalog(ledger.path).get("sales")
    csv = tmp_path / "sales.csv"
    base = T - timedelta(days=3)
    csv.write_text(
        csv.read_text() + f"{(base + timedelta(days=141)).date().isoformat()},2\n"
    )
    next_now = now + timedelta(hours=12)
    next_snapshot = ingest_source(source.spec, next_now)
    ledger.put_snapshot(next_snapshot)
    ledger.advance_watch(
        "watch",
        {
            "kind": "data_appended",
            "source_id": "sales",
            "snapshot_id": next_snapshot.snapshot_id,
            "next_due_at": next_now + timedelta(days=1),
            "requalification_due_at": next_now,
        },
        next_now,
        event_id=f"test-append/{next_snapshot.snapshot_id}",
    )
    worker._schedule_requalifications(next_now)

    watch = ledger.get_watch("watch")
    assert watch.requalification_reason == "automatic_requalification_budget_exhausted"
    assert watch.requalification_due_at == now + timedelta(hours=24)
    with ledger._connection() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM requalification_budgets WHERE question_id = ?",
                (question.question_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM jobs WHERE json_extract(payload, '$.automatic_requalification') = 1"
            ).fetchone()[0]
            == 1
        )


def test_automatic_requalification_uses_scheduled_snapshot_after_source_changes(
    tmp_path,
):
    from forecast_anything.backtesting.store import BacktestStore
    from forecast_anything.sources.catalog import SourceCatalog

    ledger, runtime, question, now = _provisional_requalification_case(
        tmp_path, appended_days=141
    )
    worker = Worker(runtime, JobQueue(ledger))
    worker._schedule_requalifications(now)
    snapshot_id = ledger.get_watch("watch").source_snapshot_ids[-1]
    scheduled_snapshot = ledger.get_snapshot(snapshot_id)

    source = SourceCatalog(ledger.path).get("sales")
    csv = tmp_path / "sales.csv"
    changed = csv.read_text().replace(",5\n", ",999\n", 1)
    csv.write_text(changed)
    assert ",999\n" in csv.read_text()
    worker.run_due(now, limit=10)

    references = ledger.list_question_references(question.question_id, revision=1)
    backtest = next(
        reference
        for reference in references.references
        if reference.target_type == "backtest"
    )
    plan = BacktestStore(ledger).get_plan(backtest.target_id)
    assert plan.archive.source_revision == source.revision
    assert plan.archive.observations == scheduled_snapshot.observations
    assert plan.archive.captured_at == scheduled_snapshot.as_of


def test_automatic_requalification_retries_after_cooldown_even_when_stale(tmp_path):
    from forecast_anything.contracts import DomainError

    ledger, runtime, question, now = _provisional_requalification_case(
        tmp_path, appended_days=141
    )
    queue = JobQueue(ledger)
    worker = Worker(runtime, queue)
    worker._schedule_requalifications(now)
    with ledger._connection() as connection:
        job_ids = [
            row[0]
            for row in connection.execute(
                "SELECT job_id FROM jobs WHERE json_extract(payload, '$.automatic_requalification') = 1"
            ).fetchall()
        ]
    first = queue.get(job_ids[0])
    claimed = queue.claim("failed-requalification", now, 60)
    assert claimed is not None and claimed.job_id == first.job_id
    queue.fail(
        claimed,
        now,
        DomainError("backtest_time_budget_exceeded", {"seconds": 300}).model_dump(),
        max_attempts=1,
    )
    worker._record_requalification_failure(claimed, now)
    next_now = now + timedelta(hours=24)
    ledger.clock = runtime.clock = lambda: next_now
    ledger.advance_watch(
        "watch", {"kind": "horizon_expired"}, next_now, event_id="expired"
    )
    assert ledger.get_watch("watch").quality == "stale"

    worker._schedule_requalifications(next_now)

    with ledger._connection() as connection:
        job_ids = [
            row[0]
            for row in connection.execute(
                "SELECT job_id FROM jobs WHERE json_extract(payload, '$.automatic_requalification') = 1"
            ).fetchall()
        ]
    retries = [queue.get(job_id) for job_id in job_ids]
    assert len(retries) == 2
    assert retries[0].job_id != retries[1].job_id
    assert retries[1].state == "pending"
    assert ledger.get_watch("watch").requalification_due_at is None


def test_pausing_one_question_leaves_shared_source_run_for_another(tmp_path):
    from forecast_anything.api.service import Observatory
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
        QuestionTitlePatch,
    )
    from forecast_anything.operators import register_builtin_operators

    ledger, _, runtime = setup(tmp_path)
    runtime.operators = register_builtin_operators()
    csv, _ = registered_watch(
        tmp_path, ledger, templates=("forecast_change", "expected_deviation")
    )
    watches = ledger.list_watches()
    questions = []
    for index, watch in enumerate(watches):
        question = ledger.create_question(
            QuestionCreateRequest(
                key=f"shared-source-{index}",
                title=f"Sales outlook {index}",
                meaning="Forecast daily sales",
                source_ids=("sales",),
                selection={"provider": "seasonal_naive", "horizon": 1},
            )
        )
        ledger.link_question_reference(
            question.question_id,
            QuestionReferenceRequest(
                key=f"watch-ref-{index}",
                revision=1,
                target_type="watch",
                target_id=watch.watch_id,
            ),
        )
        questions.append(question)
    Observatory(ledger, runtime).patch_question(
        questions[0].question_id, QuestionTitlePatch(status="paused")
    )
    assert ledger.get_watch(watches[0].watch_id).lifecycle == "paused"
    assert ledger.get_watch(watches[1].watch_id).lifecycle != "paused"

    csv.write_text(
        "time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n2026-10-24,4\n"
    )
    Worker(runtime, JobQueue(ledger)).run_due(T)

    first_refs = ledger.list_question_references(questions[0].question_id, revision=1)
    second_refs = ledger.list_question_references(questions[1].question_id, revision=1)
    assert not any(ref.target_type == "run" for ref in first_refs.references)
    assert any(ref.target_type == "run" for ref in second_refs.references)


def test_source_subscription_revocation_suppresses_queued_refresh(tmp_path):
    from forecast_anything.api.service import Observatory

    ledger, _, runtime = setup(tmp_path)
    csv, registered = registered_watch(tmp_path, ledger)
    before = ledger.get_watch("watch").source_snapshot_ids
    service = Observatory(ledger, runtime)
    subscription = service.set_source_subscription("sales", active=False)
    assert not subscription.active
    assert ledger.get_watch("watch").lifecycle == "unsupported"

    queue = JobQueue(ledger)
    job = queue.enqueue(
        "refresh-after-revocation",
        {
            "kind": "source_refresh",
            "source_id": "sales",
            "revision": registered.revision,
            "as_of": T.isoformat(),
        },
    )
    Worker(runtime, queue).run_due(T)

    assert queue.get(job.job_id).state == "completed"
    assert queue.history(job.job_id)[0]["result"] == {
        "suppressed": "source_subscription_revoked"
    }
    assert ledger.get_watch("watch").source_snapshot_ids == before
    assert csv.exists()


def test_unavailable_source_does_not_publish_empty_snapshot_or_loop(tmp_path):
    ledger, _, runtime = setup(tmp_path)
    csv, registered = registered_watch(tmp_path, ledger)
    csv.unlink()
    queue = JobQueue(ledger)
    job = queue.enqueue(
        "refresh/sales/missing",
        {
            "kind": "source_refresh",
            "source_id": "sales",
            "revision": registered.revision,
            "as_of": T.isoformat(),
        },
    )
    Worker(runtime, queue).run_due(T)
    assert queue.get(job.job_id).state == "pending"
    assert queue.history(job.job_id)[0]["state"] == "failed"
    assert queue.history(job.job_id)[0]["error"]["code"] == "source_unavailable"
    assert len(ledger.list_watches()) == 1
    assert Worker(runtime, queue).run_due(T + timedelta(seconds=1)) == ()
    assert not ledger.get_watch("watch").operational


def test_discovery_checkpoint_survives_restart_without_resetting_budget(tmp_path):
    ledger, _, runtime = setup(tmp_path)
    registered_watch(tmp_path, ledger, due=T + timedelta(days=1))
    queue = JobQueue(ledger)
    job = queue.enqueue(
        "discovery/agent",
        {"kind": "discovery", "epoch_id": "original", "source_ids": ["sales"]},
    )

    class Gateway:
        def start(self, epoch_id, source_ids, key):
            assert (epoch_id, source_ids, key) == ("original", ("sales",), job.job_id)
            return "session-1"

        def poll(self, session_id):
            assert session_id == "session-1"
            return None

    worker = Worker(runtime, queue, discovery_gateway=Gateway())
    worker.run_due(T, limit=1)
    assert queue.get(job.job_id).payload["session_id"] == "session-1"
    assert ledger.discovery_usage("original") == (1, 0)
    for index in range(3):
        ledger.consume_discovery_tool_call("original", f"real-tool/{index}")
    assert ledger.discovery_usage("original") == (1, 3)
    ledger, _, runtime = setup(tmp_path, lambda: T + timedelta(seconds=30))

    class ResumedGateway:
        def start(self, *args):
            raise AssertionError("must resume same session")

        def poll(self, session_id):
            assert session_id == "session-1"
            return ()

    queue = JobQueue(ledger)
    Worker(runtime, queue, discovery_gateway=ResumedGateway()).run_due(
        runtime.clock(), limit=1
    )
    assert queue.get(job.job_id).state == "completed"
    assert ledger.discovery_usage("original") == (1, 3)


def test_lease_expiring_during_publication_rolls_back_run_and_events(
    tmp_path, monkeypatch
):
    now = [T]
    ledger, _, runtime = setup(tmp_path, lambda: now[0])
    queue = JobQueue(ledger)
    queue.enqueue("run/1", payload())
    job = queue.claim("old", T, 60)
    from contextlib import contextmanager

    original = ledger._transaction

    @contextmanager
    def expires_before_commit(*args, **kwargs):
        with original(*args, **kwargs) as connection:
            yield connection
            # Source/graph inserts do not publish; expire only the run transaction.
            if connection.execute("SELECT 1 FROM runs").fetchone():
                now[0] = T + timedelta(seconds=60)

    monkeypatch.setattr(ledger, "_transaction", expires_before_commit)
    with pytest.raises(DomainError, match="lease_lost"):
        runtime.run(*inputs(), T, job.emission_key, lease_guard=job.guard)
    assert ledger.events_after(0) == ()
    assert ledger.get_run_by_key(job.emission_key) is None


def test_renewal_extends_lease_without_reviving_an_expired_owner(tmp_path):
    now = [T]
    ledger, _, _ = setup(tmp_path, lambda: now[0])
    queue = JobQueue(ledger)
    job = queue.enqueue("run/1", payload())
    current = queue.claim("owner", T, 60)
    now[0] = T + timedelta(seconds=20)
    queue.renew(current, now[0])
    assert queue.claim("other", T + timedelta(seconds=60), 60) is None
    now[0] = T + timedelta(seconds=80)
    with pytest.raises(DomainError, match="lease_lost"):
        queue.renew(current, now[0])
    assert queue.claim("other", now[0], 60).job_id == job.job_id


def test_shared_source_keeps_separate_successor_lineage(tmp_path):
    ledger, _, runtime = setup(tmp_path)
    csv, _ = registered_watch(
        tmp_path, ledger, templates=("forecast_change", "expected_deviation")
    )
    csv.write_text("time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,9\n")
    queue = JobQueue(ledger)
    Worker(runtime, queue).run_due(T)
    successors = [w for w in ledger.list_watches() if w.supersedes_watch_id]
    assert {w.supersedes_watch_id for w in successors} == {"watch", "watch-1"}
    assert len({w.candidate.epoch_id for w in successors}) == 2
    assert all(not w.operational for w in successors)
    with ledger._connection() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM source_polling").fetchone()[0] == 1
        )


def test_reclaimed_owner_cannot_append_even_before_current_lease_expires(tmp_path):
    now = [T]
    ledger, _, runtime = setup(tmp_path, lambda: now[0])
    queue = JobQueue(ledger)
    queue.enqueue("run/1", payload())
    stale = queue.claim("old", T, 60)
    now[0] += timedelta(seconds=61)
    queue.claim("new", now[0], 60)
    with pytest.raises(DomainError, match="lease_lost"):
        runtime.run(*inputs(), T, stale.emission_key, lease_guard=stale.guard)
    assert ledger.events_after(0) == ()


def qualify_watch(tmp_path, ledger):
    from forecast_anything.contracts import (
        EvaluationContext,
        ForecastResult,
        RunRecord,
        Snapshot,
    )
    from forecast_anything.discovery.policy import assess_candidate
    from forecast_anything.evaluation.records import evaluate_run

    registered_watch(
        tmp_path, ledger, final_origins=tuple(f"day-{i}" for i in range(30))
    )
    watch = ledger.get_watch("watch")
    candidate = watch.candidate
    epoch = ledger.get_discovery_epoch("original")
    records = []
    for i, origin in enumerate(epoch.final_origin_ids):
        target = T + timedelta(days=i + 1)
        result = ForecastResult(
            series_ids=("sales",),
            timestamps=(target,),
            units=("count",),
            point=((1,),),
            provider_id="scripted",
            provider_revision="v1",
            quantiles=None,
            paths=None,
            sample_group_id=None,
            assumptions=(),
        )
        run = RunRecord(
            run_id=f"qualified-{i}",
            graph_id=candidate.graph.graph_id,
            graph_version=1,
            as_of=T,
            snapshot_ids=epoch.source_snapshot_ids,
            requested_provider={},
            actual_provider={},
            state="completed",
            results={
                "forecast": result,
                "question": result,
                "reference": result.model_copy(update={"point": ((2,),)}),
            },
            evidence_ids=(),
            scenario_id=None,
            parent_run_id=None,
        )
        ledger.append_run(run, (), run.run_id)
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
        record = evaluate_run(run, actuals, candidate.graph).model_copy(
            update={
                "discovery": EvaluationContext(
                    candidate_id=candidate.candidate_id,
                    protocol_id=candidate.protocol_id,
                    epoch_id="original",
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
    decision = assess_candidate(candidate, tuple(records), epoch)
    assert decision.action == "activate"
    ledger.append_eligibility_decision(candidate.candidate_id, decision)
    ledger.advance_watch(
        "watch",
        {
            "kind": "evidence_qualified",
            "decision": decision,
            "next_due_at": T + timedelta(days=1),
        },
        T,
        event_id="qualification",
    )
    return decision


def test_resume_after_deadline_cannot_restore_old_activated_evidence(tmp_path):
    ledger, _, runtime = setup(tmp_path)
    decision = qualify_watch(tmp_path, ledger)
    ledger.advance_watch("watch", {"kind": "paused"}, T, event_id="pause")
    late = T + timedelta(days=1)
    resumed = Worker(runtime, JobQueue(ledger)).resume_watch(
        "watch", late, event_id="resume"
    )
    assert resumed.eligibility_decision == decision
    assert resumed.quality == "stale"
    assert resumed.lifecycle == "evaluating"
    assert not resumed.operational
    # Replaying that control after expiry cannot return a historical operational state.
    assert (
        not Worker(runtime, JobQueue(ledger))
        .resume_watch("watch", late, event_id="resume")
        .operational
    )


def test_source_mapping_revision_invalidates_before_future_deadline_resume(tmp_path):
    from forecast_anything.sources.catalog import SourceCatalog

    ledger, _, runtime = setup(tmp_path)
    decision = qualify_watch(tmp_path, ledger)
    ledger.advance_watch("watch", {"kind": "paused"}, T, event_id="pause")
    catalog = SourceCatalog(ledger.path)
    spec = catalog.get("sales").spec
    spec.mapping["unit"] = {"constant": "EUR"}
    catalog.append(spec)
    resumed = Worker(runtime, JobQueue(ledger)).resume_watch(
        "watch", T, event_id="resume"
    )
    assert resumed.candidate_invalidated
    assert resumed.invalidated_evaluation_ids == decision.evaluation_ids
    assert resumed.lifecycle == "evaluating"
    assert not resumed.operational


def test_http_401_refresh_remains_an_explicit_failure(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from forecast_anything.sources.catalog import SourceCatalog

    ledger, _, runtime = setup(tmp_path)
    _, registered = registered_watch(tmp_path, ledger)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"never publish this body")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        spec = registered.spec.model_copy(
            update={
                "kind": "http_json",
                "location": f"http://127.0.0.1:{server.server_port}/",
            }
        )
        revision = SourceCatalog(ledger.path).append(spec).revision
        queue = JobQueue(ledger)
        job = queue.enqueue(
            "refresh/http/1",
            {
                "kind": "source_refresh",
                "source_id": "sales",
                "revision": revision,
                "as_of": T.isoformat(),
            },
        )
        Worker(runtime, queue).run_due(T)
        error = queue.history(job.job_id)[0]["error"]
        assert error["code"] == "source_unavailable"
        assert error["details"]["status"] == 401
        assert "never publish" not in str(error)
        assert len(ledger.list_watches()) == 1
        with ledger._connection() as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_parent_run_is_part_of_job_emission_identity(tmp_path):
    _, _, runtime = setup(tmp_path)
    first = runtime.run(*inputs(), T, "first")
    second = runtime.run(*inputs(), T, "second")
    runtime.run(*inputs(), T, "update", previous_run_id=first.run_id)
    with pytest.raises(DomainError, match="idempotency_conflict"):
        runtime.run(*inputs(), T, "update", previous_run_id=second.run_id)


def test_queued_source_change_recomputes_only_descendant_operators(tmp_path):
    from forecast_anything.operators import register_builtin_operators

    ledger, provider, runtime = setup(tmp_path)
    operator = register_builtin_operators()["sum_aligned"]

    class CountingOperator:
        calls = []

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


def test_successor_watch_preserves_pause_mute_and_priority_controls(tmp_path):
    ledger, _, runtime = setup(tmp_path)
    # The second watch keeps this shared source active while the first is paused.
    # That lets the test verify inherited controls when another question still
    # needs the source poll.
    csv, _ = registered_watch(
        tmp_path,
        ledger,
        templates=("forecast_change", "expected_deviation"),
    )
    for event in (
        {"kind": "paused"},
        {"kind": "muted", "muted": True},
        {"kind": "priority_changed", "priority": 5},
    ):
        ledger.advance_watch("watch", event, T, event_id=event["kind"])
    csv.write_text("time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,9\n")
    Worker(runtime, JobQueue(ledger)).run_due(T)
    successor = next(
        w for w in ledger.list_watches() if w.supersedes_watch_id == "watch"
    )
    assert (successor.lifecycle, successor.muted, successor.priority) == (
        "paused",
        True,
        5,
    )
    assert not successor.operational


def test_evaluation_job_persists_scores_and_recovers_after_completion_crash(
    tmp_path, monkeypatch
):
    from forecast_anything.contracts import Snapshot

    ledger, _, runtime = setup(tmp_path)
    graph, snapshots = inputs()
    snapshots = {
        name: freeze(
            tuple(
                o.model_copy(update={"event_time": o.event_time + timedelta(hours=1)})
                for o in snapshot.observations
            ),
            T,
        )
        for name, snapshot in snapshots.items()
    }
    run = runtime.run(graph, snapshots, T, "forecast")
    actuals = Snapshot(
        snapshot_id="actuals",
        as_of=T + timedelta(hours=1),
        assumptions=(),
        observations=tuple(
            Observation(
                series_id=series,
                event_time=T + timedelta(hours=1),
                available_at=T + timedelta(hours=1),
                revision="1",
                value=value,
                unit="count",
            )
            for series, value in (("a", 4), ("b", 3))
        ),
    )
    ledger.put_snapshot(actuals)
    queue = JobQueue(ledger)
    job = queue.enqueue(
        "evaluate/forecast",
        {"kind": "evaluation", "run_id": run.run_id, "actuals_snapshot_id": "actuals"},
    )
    worker = Worker(runtime, queue)
    original = queue.complete

    def crash(*args, **kwargs):
        raise KeyboardInterrupt("after evaluation commit")

    monkeypatch.setattr(queue, "complete", crash)
    with pytest.raises(KeyboardInterrupt):
        worker.run_due(T)
    with ledger._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == 1
    monkeypatch.setattr(queue, "complete", original)
    ledger.clock = runtime.clock = lambda: T + timedelta(seconds=61)
    Worker(runtime, queue).run_due(runtime.clock())
    result = queue.history(job.job_id)[0]["result"]
    evaluation = ledger.get_evaluation(result["evaluation_id"])
    assert evaluation.metrics["f_a"]["mae"] == 1.0
    assert evaluation.metrics["f_b"]["mae"] == 0.0
    with ledger._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == 1


@pytest.mark.parametrize("completion_committed", [False, True])
def test_completion_ack_error_preserves_published_attempt(
    tmp_path, monkeypatch, completion_committed
):
    import sqlite3

    ledger, provider, runtime = setup(tmp_path)
    queue = JobQueue(ledger)
    job = queue.enqueue("run/ack", payload())
    complete = queue.complete

    def fail_ack(*args, **kwargs):
        if completion_committed:
            complete(*args, **kwargs)
        raise sqlite3.OperationalError("transient completion acknowledgement failure")

    monkeypatch.setattr(queue, "complete", fail_ack)
    with pytest.raises(sqlite3.OperationalError, match="acknowledgement failure"):
        Worker(runtime, queue).run_due(T)
    assert queue.get(job.job_id).attempt == 1
    assert ledger.get_run_by_key(f"{job.job_id}/1").state == "completed"
    assert ledger.get_run_by_key(f"{job.job_id}/2") is None
    assert (
        len(
            [event for event in ledger.events_after(0) if event.kind == "run_completed"]
        )
        == 1
    )
    monkeypatch.setattr(queue, "complete", complete)
    ledger.clock = runtime.clock = lambda: T + timedelta(seconds=61)
    Worker(runtime, queue).run_due(runtime.clock())
    assert queue.get(job.job_id).state == "completed"
    assert queue.get(job.job_id).attempt == 1
    assert [attempt["state"] for attempt in queue.history(job.job_id)] == ["completed"]
    assert provider.calls == ["a", "b"]
    assert (
        len(
            [event for event in ledger.events_after(0) if event.kind == "run_completed"]
        )
        == 1
    )


def test_batch_resume_rechecks_deadline_crossed_by_preceding_run(tmp_path, monkeypatch):
    deadline = T + timedelta(days=1)
    batch_started = deadline - timedelta(seconds=10)
    now = [batch_started]
    ledger, provider, runtime = setup(tmp_path, lambda: now[0])
    qualify_watch(tmp_path, ledger)
    ledger.advance_watch("watch", {"kind": "paused"}, T, event_id="pause")
    queue = JobQueue(ledger)
    forecast = queue.enqueue("run/before-resume", payload())
    resume = queue.enqueue(
        "resume/after-run", {"kind": "watch_resume", "watch_id": "watch"}
    )
    original_forecast = provider.forecast

    def cross_deadline(request):
        result = original_forecast(request)
        now[0] = deadline + timedelta(seconds=10)
        return result

    monkeypatch.setattr(provider, "forecast", cross_deadline)
    assert Worker(runtime, queue).run_due(batch_started, limit=2) == (
        forecast.job_id,
        resume.job_id,
    )
    current = ledger.get_watch("watch")
    assert (current.lifecycle, current.quality, current.operational) == (
        "evaluating",
        "stale",
        False,
    )
    history = ledger.watch_history("watch")
    assert [entry["event"]["kind"] for entry in history[-2:]] == [
        "refresh_expired",
        "resumed",
    ]
    assert all(entry["occurred_at"] == now[0] for entry in history[-2:])
    assert queue.get(resume.job_id).state == "completed"
