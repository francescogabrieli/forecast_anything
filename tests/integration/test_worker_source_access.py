"""Shared source subscriptions, revocation, and failures."""

from datetime import timedelta

from worker_fixtures import T, registered_watch, setup

from forecast_anything.jobs import JobQueue
from forecast_anything.worker import Worker


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
