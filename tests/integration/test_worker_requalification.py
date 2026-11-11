"""Watch requalification scheduling and evidence budgets."""

from datetime import datetime, timedelta

import pytest
from worker_fixtures import T, _provisional_requalification_case, qualify_watch, setup

from forecast_anything.jobs import JobQueue
from forecast_anything.worker import Worker


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
            "execution_started_at": T.isoformat(),
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


def test_requalification_can_schedule_without_a_previous_qualification(tmp_path):
    ledger, runtime, _, now = _provisional_requalification_case(
        tmp_path, appended_days=141, qualified=False
    )
    assert ledger.get_watch("watch").qualification_snapshot_id is None
    queue = JobQueue(ledger)
    worker = Worker(runtime, queue)
    worker._schedule_requalifications(now)
    with ledger._connection() as connection:
        (job_id,) = connection.execute(
            "SELECT job_id FROM jobs WHERE json_extract(payload, '$.automatic_requalification') = 1"
        ).fetchone()
    assert queue.original_payload(job_id).get("origin_target_after") is None
    worker.run_due(now)
    assert queue.get(job_id).state == "completed"


def test_requalification_budget_starts_on_first_claim_after_queue_delay(
    tmp_path, monkeypatch
):
    ledger, runtime, _, scheduled_at = _provisional_requalification_case(
        tmp_path, appended_days=141
    )
    queue = JobQueue(ledger)
    worker = Worker(runtime, queue)
    worker._schedule_requalifications(scheduled_at)
    with ledger._connection() as connection:
        row = connection.execute(
            "SELECT job_id, payload FROM jobs WHERE json_extract(payload, '$.automatic_requalification') = 1"
        ).fetchone()
    job_id, original_payload = row
    import json

    assert "execution_deadline_at" not in json.loads(original_payload)

    # The durable job waits longer than its 300-second compute budget before
    # any worker claims it. A crash then lets a second worker reclaim the lease.
    first_claim_at = scheduled_at + timedelta(seconds=301)
    ledger.clock = runtime.clock = lambda: first_claim_at
    observed = []

    def crash_after_claim(job, now):
        observed.append(job.payload.copy())
        raise KeyboardInterrupt("worker exited after first claim")

    monkeypatch.setattr(worker, "_execute", crash_after_claim)
    with pytest.raises(KeyboardInterrupt, match="first claim"):
        worker.run_due(first_claim_at)

    first_payload = queue.get(job_id).payload
    expected_deadline = first_claim_at + timedelta(seconds=300)
    assert first_payload["execution_started_at"] == first_claim_at.isoformat()
    assert first_payload["execution_deadline_at"] == expected_deadline.isoformat()

    second_claim_at = first_claim_at + timedelta(seconds=61)
    ledger.clock = runtime.clock = lambda: second_claim_at
    resumed = Worker(runtime, queue)
    monkeypatch.setattr(
        resumed,
        "_execute",
        lambda job, now: observed.append(job.payload.copy()) or {"recovered": True},
    )
    resumed.run_due(second_claim_at)

    assert observed[1]["execution_deadline_at"] == expected_deadline.isoformat()
    assert (
        datetime.fromisoformat(observed[1]["execution_deadline_at"]) > second_claim_at
    )
    assert queue.get(job_id).state == "completed"


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

    ledger, runtime, _question, now = _provisional_requalification_case(
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
