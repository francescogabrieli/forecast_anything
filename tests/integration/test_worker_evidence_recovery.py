"""Worker evidence publication and recovery after interruption."""

from datetime import datetime, timedelta

import pytest
from worker_fixtures import (
    T,
    _provisional_requalification_case,
    inputs,
    registered_watch,
    setup,
)

from forecast_anything.contracts import Observation
from forecast_anything.jobs import JobQueue
from forecast_anything.temporal import freeze
from forecast_anything.worker import Worker


def test_requalification_wait_retry_does_not_rewrite_inbox_transition(tmp_path):
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
    )

    ledger, _, runtime = setup(tmp_path)
    registered_watch(tmp_path, ledger)
    watch = ledger.get_watch("watch")
    question = ledger.create_question(
        QuestionCreateRequest(
            key="requalification-wait",
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
    worker = Worker(runtime, JobQueue(ledger))
    reason = "insufficient_new_final_origins"

    worker._wait_for_requalification(
        watch,
        worker._question_links_for_watch(watch.watch_id),
        T,
        reason=reason,
        new_origins=1,
        due_at=T + timedelta(seconds=60),
    )
    current = ledger.get_watch(watch.watch_id)
    worker._wait_for_requalification(
        current,
        worker._question_links_for_watch(watch.watch_id),
        T + timedelta(seconds=61),
        reason=reason,
        new_origins=1,
        due_at=T + timedelta(seconds=121),
    )

    inbox = ledger.list_inbox_events(
        question_id=question.question_id, offset=0, limit=10
    )
    assert inbox.total_count == 1
    assert inbox.events[0].event_kind == "requalification_waiting"
    assert "requalification_due_at" not in inbox.events[0].payload
    assert ledger.get_watch(watch.watch_id).requalification_due_at == T + timedelta(
        seconds=121
    )


def test_requalification_publication_replays_after_deadline_without_duplicates(
    tmp_path, monkeypatch
):
    from forecast_anything.backtesting.store import BacktestStore

    ledger, runtime, question, scheduled_at = _provisional_requalification_case(
        tmp_path, appended_days=141
    )
    queue = JobQueue(ledger)
    worker = Worker(runtime, queue)
    worker._schedule_requalifications(scheduled_at)
    with ledger._connection() as connection:
        job_id = connection.execute(
            "SELECT job_id FROM jobs WHERE json_extract(payload, '$.automatic_requalification') = 1"
        ).fetchone()[0]
    job = queue.get(job_id)
    candidate_id = job.payload["candidate_id"]
    decision_count_before = len(ledger.eligibility_decisions(candidate_id))
    original_complete = queue.complete

    def crash_after_publication(*args, **kwargs):
        raise KeyboardInterrupt("worker exited after decision publication")

    monkeypatch.setattr(queue, "complete", crash_after_publication)
    with pytest.raises(KeyboardInterrupt, match="decision publication"):
        worker.run_due(scheduled_at)

    report = BacktestStore(ledger).get_report(job_id)
    persisted_event_ids = {
        event.event_id
        for event in ledger.list_inbox_events(question_id=question.question_id).events
    }
    persisted_decisions = ledger.eligibility_decisions(candidate_id)
    persisted_watch_events = ledger.watch_history("watch")
    provider_calls = len(runtime.providers["seasonal_naive"].calls)
    deadline = datetime.fromisoformat(
        queue.get(job_id).payload["execution_deadline_at"]
    )
    replay_at = deadline + timedelta(seconds=1)
    ledger.clock = runtime.clock = lambda: replay_at
    monkeypatch.setattr(queue, "complete", original_complete)

    completed = Worker(runtime, queue).run_due(replay_at)

    assert completed == (job_id,)
    assert queue.get(job_id).state == "completed"
    assert queue.get(job_id).attempt == 1
    assert len(queue.history(job_id)) == 1
    assert queue.history(job_id)[-1]["result"]["report_id"] == report.report_id
    assert len(runtime.providers["seasonal_naive"].calls) == provider_calls
    assert len(ledger.eligibility_decisions(candidate_id)) == decision_count_before + 1
    assert ledger.eligibility_decisions(candidate_id) == persisted_decisions
    assert {
        event.event_id
        for event in ledger.list_inbox_events(question_id=question.question_id).events
    } == persisted_event_ids
    final_watch_events = ledger.watch_history("watch")
    assert len(final_watch_events) == len(persisted_watch_events)
    assert (
        sum(
            entry["event_id"] == f"backtest/{report.report_id}"
            for entry in final_watch_events
        )
        == 1
    )


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
