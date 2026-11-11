"""Watch lineage and controls across worker runs."""

from datetime import timedelta

from worker_fixtures import T, payload, qualify_watch, registered_watch, setup

from forecast_anything.jobs import JobQueue
from forecast_anything.worker import Worker


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
