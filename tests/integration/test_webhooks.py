"""Durable inbox outbox delivery, suppression, retries and restart recovery."""

import hmac
import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.error import HTTPError

import pytest

from forecast_anything.contracts import (
    QuestionCreateRequest,
    QuestionTitlePatch,
    WebhookSubscriptionRequest,
)
from forecast_anything.jobs import JobQueue
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.worker import Worker

T = datetime(2026, 11, 8, tzinfo=timezone.utc)


def _setup(tmp_path, target_url="http://127.0.0.1:8765/updates"):
    now = [T]
    ledger = Ledger(tmp_path / "webhooks.db", clock=lambda: now[0])
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        {},
        lambda: now[0],
    )
    question = ledger.create_question(
        QuestionCreateRequest(
            key="webhook-question",
            title="Sales outlook",
            meaning="Forecast daily sales",
            source_ids=("sales",),
            selection={"provider": "seasonal_naive", "horizon": 1},
        )
    )
    subscription = ledger.create_webhook_subscription(
        WebhookSubscriptionRequest(target_url=target_url, secret="test-secret")
    )
    event = ledger.record_inbox_event(
        question_id=question.question_id,
        revision=1,
        event_kind="forecast_issued",
        transition_id="run-1",
        summary="A forecast is available.",
        payload={"quality": "provisional"},
    )
    return ledger, runtime, now, question, subscription, event


def _delivery(ledger, subscription_id):
    return ledger.list_webhook_deliveries(subscription_id, limit=10).deliveries[0]


def test_inbox_event_and_outbox_enqueue_are_atomic_and_idempotent(tmp_path):
    ledger, _, _, question, subscription, first = _setup(tmp_path)
    retry = ledger.record_inbox_event(
        question_id=question.question_id,
        revision=1,
        event_kind="forecast_issued",
        transition_id="run-1",
        summary="A forecast is available.",
        payload={"quality": "provisional"},
    )
    assert retry.event_id == first.event_id
    assert _delivery(ledger, subscription.subscription_id).state == "pending"
    with ledger._connection() as connection:
        assert (
            connection.execute("SELECT count(*) FROM webhook_outbox").fetchone()[0] == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM jobs WHERE json_extract(payload, '$.kind') = 'webhook_delivery'"
            ).fetchone()[0]
            == 1
        )
        stored_secret = connection.execute(
            "SELECT secret FROM webhook_subscriptions WHERE subscription_id = ?",
            (subscription.subscription_id,),
        ).fetchone()[0]
    assert stored_secret == "test-secret"
    assert "secret" not in subscription.model_dump()


def test_delivery_has_stable_id_and_hmac_signature(tmp_path, monkeypatch):
    import forecast_anything.worker as worker_module

    ledger, runtime, _, question, subscription, event = _setup(tmp_path)
    sent = []

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def open(self, request, timeout):
            body = request.data
            sent.append(
                (request.get_header("X-forecast-event-id"), body, request.headers)
            )
            return Response()

    monkeypatch.setattr(worker_module, "build_opener", lambda *args: Opener())
    queue = JobQueue(ledger)
    Worker(runtime, queue).run_due(T)

    delivery = _delivery(ledger, subscription.subscription_id)
    assert delivery.state == "delivered"
    assert len(sent) == 1
    header, body, headers = sent[0]
    parsed = json.loads(body)
    assert header == event.event_id
    assert parsed["event_id"] == event.event_id
    assert parsed["question_id"] == question.question_id
    expected = hmac.new(b"test-secret", body, sha256).hexdigest()
    assert headers["X-forecast-signature"] == f"sha256={expected}"
    assert "summary" not in parsed and "payload" not in parsed


def test_muting_after_queueing_preserves_inbox_and_suppresses_delivery(
    tmp_path, monkeypatch
):
    import forecast_anything.worker as worker_module

    ledger, runtime, _, question, subscription, event = _setup(tmp_path)

    class NoSend:
        def open(self, *args, **kwargs):
            raise AssertionError("muted delivery must not make an HTTP request")

    monkeypatch.setattr(worker_module, "build_opener", lambda *args: NoSend())
    ledger.patch_question(question.question_id, QuestionTitlePatch(muted=True))
    Worker(runtime, JobQueue(ledger)).run_due(T)

    assert (
        ledger.list_inbox_events(question_id=question.question_id).events[0].event_id
        == event.event_id
    )
    assert (
        _delivery(ledger, subscription.subscription_id).state
        == "delivery_suppressed_muted"
    )


def test_delivery_failure_uses_30_and_120_second_delays_and_stops_after_three(
    tmp_path, monkeypatch
):
    import forecast_anything.worker as worker_module

    ledger, runtime, now, question, subscription, event = _setup(tmp_path)
    sent = []

    class NoResponse:
        def open(self, request, timeout):
            sent.append(request.get_header("X-forecast-event-id"))
            raise HTTPError(request.full_url, 503, "unavailable", {}, None)

    monkeypatch.setattr(worker_module, "build_opener", lambda *args: NoResponse())
    queue = JobQueue(ledger)
    with ledger._connection() as connection:
        job_id = connection.execute(
            "SELECT job_id FROM jobs WHERE json_extract(payload, '$.kind') = 'webhook_delivery'"
        ).fetchone()[0]
    job = queue.get(job_id)
    Worker(runtime, queue).run_due(now[0])
    first_retry = _delivery(ledger, subscription.subscription_id)
    assert first_retry.attempts == 1
    assert first_retry.next_attempt_at == now[0] + timedelta(seconds=30)
    assert queue.get(job.job_id).state == "pending"
    assert queue.get(job.job_id).lease_until is None
    now[0] = first_retry.next_attempt_at
    Worker(runtime, queue).run_due(now[0])
    second_retry = _delivery(ledger, subscription.subscription_id)
    assert second_retry.attempts == 2
    assert second_retry.next_attempt_at == now[0] + timedelta(seconds=120)
    now[0] = second_retry.next_attempt_at
    Worker(runtime, queue).run_due(now[0])

    delivery = _delivery(ledger, subscription.subscription_id)
    assert delivery.state == "delivery_failed"
    assert delivery.attempts == 3
    assert len(sent) == 3
    assert set(sent) == {event.event_id}
    assert ledger.list_inbox_events(question_id=question.question_id).total_count == 1


def test_crash_recovery_reuses_same_event_id(tmp_path, monkeypatch):
    import forecast_anything.worker as worker_module

    ledger, runtime, now, _, subscription, event = _setup(tmp_path)
    seen = []

    class CrashAfterSend:
        def open(self, request, timeout):
            seen.append(request.get_header("X-forecast-event-id"))
            raise KeyboardInterrupt("crash after request reached receiver")

    monkeypatch.setattr(worker_module, "build_opener", lambda *args: CrashAfterSend())
    queue = JobQueue(ledger)
    with pytest.raises(KeyboardInterrupt):
        Worker(runtime, queue, lease_seconds=1).run_due(now[0])
    assert _delivery(ledger, subscription.subscription_id).state == "delivering"

    class Success:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Recover:
        def open(self, request, timeout):
            seen.append(request.get_header("X-forecast-event-id"))
            return Success()

    monkeypatch.setattr(worker_module, "build_opener", lambda *args: Recover())
    now[0] += timedelta(seconds=2)
    Worker(runtime, JobQueue(ledger), lease_seconds=1).run_due(now[0])

    assert seen == [event.event_id, event.event_id]
    assert _delivery(ledger, subscription.subscription_id).state == "delivered"
    assert _delivery(ledger, subscription.subscription_id).attempts == 2


def test_crash_after_retry_commit_reschedules_pending_webhook(tmp_path, monkeypatch):
    import forecast_anything.worker as worker_module

    ledger, runtime, now, _, subscription, event = _setup(tmp_path)
    sent = []

    class NoResponse:
        def open(self, request, timeout):
            sent.append(request.get_header("X-forecast-event-id"))
            raise HTTPError(request.full_url, 503, "unavailable", {}, None)

    monkeypatch.setattr(worker_module, "build_opener", lambda *args: NoResponse())
    queue = JobQueue(ledger)
    with ledger._connection() as connection:
        job_id = connection.execute(
            "SELECT job_id FROM jobs WHERE json_extract(payload, '$.kind') = 'webhook_delivery'"
        ).fetchone()[0]
    job = queue.get(job_id)
    Worker(runtime, queue).run_due(now[0])
    first_retry = _delivery(ledger, subscription.subscription_id)
    now[0] = first_retry.next_attempt_at

    fail = queue.fail

    def crash_after_second_outbox_commit(claimed, *args, **kwargs):
        if claimed.job_id == job.job_id:
            raise KeyboardInterrupt("crash after webhook retry state commit")
        return fail(claimed, *args, **kwargs)

    monkeypatch.setattr(queue, "fail", crash_after_second_outbox_commit)
    with pytest.raises(KeyboardInterrupt, match="retry state commit"):
        Worker(runtime, queue, lease_seconds=60).run_due(now[0])
    second_retry = _delivery(ledger, subscription.subscription_id)
    assert second_retry.attempts == 2
    assert second_retry.state == "pending"
    assert len(sent) == 2

    monkeypatch.setattr(queue, "fail", fail)
    now[0] += timedelta(seconds=61)
    Worker(runtime, queue, lease_seconds=60).run_due(now[0])
    recovered = queue.get(job.job_id)
    assert recovered.state == "pending"
    assert recovered.lease_until is None
    with ledger._connection() as connection:
        next_due = connection.execute(
            "SELECT next_due_at FROM jobs WHERE job_id = ?", (job.job_id,)
        ).fetchone()[0]
    assert (
        datetime.fromtimestamp(next_due, timezone.utc) == second_retry.next_attempt_at
    )
    assert len(sent) == 2

    now[0] = second_retry.next_attempt_at
    Worker(runtime, queue).run_due(now[0])
    assert _delivery(ledger, subscription.subscription_id).attempts == 3
    assert _delivery(ledger, subscription.subscription_id).state == "delivery_failed"
    assert sent == [event.event_id, event.event_id, event.event_id]


def test_local_webhook_acceptance_survives_ledger_reopen(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    received = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(
                (
                    self.headers.get("X-Forecast-Event-Id"),
                    self.headers.get("X-Forecast-Signature"),
                    self.rfile.read(int(self.headers["Content-Length"])),
                )
            )
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        target_url = f"http://127.0.0.1:{server.server_port}/updates"
        ledger, runtime, _, question, subscription, event = _setup(tmp_path, target_url)
        Worker(runtime, JobQueue(ledger)).run_due(T)

        assert len(received) == 1
        header, signature, body = received[0]
        assert header == event.event_id
        assert (
            signature == f"sha256={hmac.new(b'test-secret', body, sha256).hexdigest()}"
        )
        assert json.loads(body)["question_id"] == question.question_id
        assert _delivery(ledger, subscription.subscription_id).state == "delivered"
        recovered = Ledger(ledger.path)
        assert (
            recovered.list_inbox_events(question_id=question.question_id)
            .events[0]
            .event_id
            == event.event_id
        )
        assert (
            recovered.list_webhook_deliveries(subscription.subscription_id)
            .deliveries[0]
            .state
            == "delivered"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
