"""Durable work, fencing, and restart fault boundaries."""

from datetime import timedelta

import pytest
from worker_fixtures import T, inputs, payload, registered_watch, setup
from worker_fixtures import qualify_watch as qualify_watch

from forecast_anything.contracts import DomainError
from forecast_anything.jobs import JobQueue, LeaseGuard
from forecast_anything.store import Ledger
from forecast_anything.worker import Worker


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


def test_parent_run_is_part_of_job_emission_identity(tmp_path):
    _, _, runtime = setup(tmp_path)
    first = runtime.run(*inputs(), T, "first")
    second = runtime.run(*inputs(), T, "second")
    runtime.run(*inputs(), T, "update", previous_run_id=first.run_id)
    with pytest.raises(DomainError, match="idempotency_conflict"):
        runtime.run(*inputs(), T, "update", previous_run_id=second.run_id)


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
