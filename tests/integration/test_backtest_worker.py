"""Worker failure/reclaim tests use real plans, child runs and SQLite leases."""

from datetime import timedelta
from pathlib import Path

import pytest
from test_backtest_api import T, request, setup, submit

from forecast_anything.backtesting.store import BacktestStore
from forecast_anything.contracts import DomainError
from forecast_anything.jobs import JobQueue
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.worker import Worker


class Provider:
    def __init__(self, before=None, *, fails=False):
        self.calls = 0
        self.before = before
        self.fails = fails
        self.revision = "1"

    def capabilities(self):
        return (
            SeasonalNaiveProvider(1)
            .capabilities()
            .model_copy(
                update={"provider_id": "controlled", "provider_revision": self.revision}
            )
        )

    def forecast(self, value):
        self.calls += 1
        if self.before:
            self.before()
        if self.fails:
            raise RuntimeError("/private/source.csv token=secret")
        return (
            SeasonalNaiveProvider(1)
            .forecast(value)
            .model_copy(
                update={"provider_id": "controlled", "provider_revision": self.revision}
            )
        )


def configured(runtime, client, provider):
    runtime.providers["controlled"] = provider
    body = request(selection={"provider": "controlled", "horizon": 2})
    return submit(client, body), body


def test_first_provider_observes_persisted_plan_and_actuals(tmp_path):
    ledger, runtime, _, revision, client = setup(tmp_path)
    store = BacktestStore(ledger)
    job_id = None

    def before():
        plan = store.get_plan(job_id)
        assert len(plan.archive.observations) == 16
        assert len(plan.origins) == 7
        assert (
            ledger.get_snapshot(plan.actuals_snapshot_id).snapshot_id
            == plan.actuals_snapshot_id
        )
        # Every subsequent call must use captured rows, despite file removal.
        Path(revision.spec.location).unlink(missing_ok=True)

    provider = Provider(before)
    job_id, _ = configured(runtime, client, provider)
    Worker(runtime, JobQueue(ledger)).run_due(T)
    assert client.get(f"/v1/jobs/{job_id}").json()["state"] == "completed"
    assert provider.calls == 7
    assert store.get_report(job_id).partitions[2].model_mae == 1.5


@pytest.mark.parametrize("new_attempt", [False, True])
def test_partial_origins_reclaim_uses_frozen_archive_and_stable_children(
    tmp_path, monkeypatch, new_attempt
):
    ledger, runtime, catalog, revision, client = setup(tmp_path)
    provider = Provider()
    job_id, body = configured(runtime, client, provider)
    queue, store = JobQueue(ledger), BacktestStore(ledger)
    old = queue.claim("old", T, 5)
    real_put = BacktestStore.put_origin

    def interrupted(self, outcome, **kwargs):
        if outcome.ordinal == 1:
            raise KeyboardInterrupt("simulated process termination after child publish")
        return real_put(self, outcome, **kwargs)

    monkeypatch.setattr(BacktestStore, "put_origin", interrupted)
    with pytest.raises(KeyboardInterrupt):
        Worker(runtime, queue)._execute(old, T)
    plan = store.get_plan(job_id)
    assert [o.ordinal for o in store.list_origins(job_id).origins] == [0]
    assert provider.calls == 2
    with ledger._connection() as connection:
        child_ids = tuple(
            row[0]
            for row in connection.execute("SELECT run_id FROM runs ORDER BY run_id")
        )
    Path(revision.spec.location).write_text("entirely changed and invalid source")
    catalog.append(revision.spec.model_copy(update={"kind": "http_json"}))
    if new_attempt:
        queue.fail(old, T, {"code": "interrupted"}, retry_seconds=0)
    runtime.clock = ledger.clock = lambda: T + timedelta(seconds=6)
    new = queue.claim("new", runtime.clock(), 60)
    assert new.job_id == old.job_id
    assert new.attempt == (2 if new_attempt else 1)
    with pytest.raises(DomainError, match="lease_lost"):
        store.put_plan(plan, lease_guard=old.guard)
    monkeypatch.setattr(BacktestStore, "put_origin", real_put)
    result = Worker(runtime, queue)._execute(new, runtime.clock())
    queue.complete(new, runtime.clock(), result)
    assert provider.calls == 7
    assert store.get_plan(job_id) == plan
    assert len(store.list_origins(job_id).origins) == 7
    with ledger._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 7
        assert connection.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == 7
        assert set(child_ids).issubset(
            {row[0] for row in connection.execute("SELECT run_id FROM runs")}
        )
    assert submit(client, body) == job_id
    assert store.get_report(job_id).captured_at == T
    assert store.get_report(job_id).partitions[2].matched_count == 4


def test_report_before_ack_recovers_without_provider_or_source(tmp_path, monkeypatch):
    ledger, runtime, _, revision, client = setup(tmp_path)
    provider = Provider()
    job_id, _ = configured(runtime, client, provider)
    queue = JobQueue(ledger)
    real_complete = queue.complete

    def interrupted(*args, **kwargs):
        raise RuntimeError("ack lost")

    monkeypatch.setattr(queue, "complete", interrupted)
    with pytest.raises(RuntimeError, match="ack lost"):
        Worker(runtime, queue, lease_seconds=5).run_due(T)
    store = BacktestStore(ledger)
    report = store.get_report(job_id)
    events = ledger.events_after(0, 1000)
    assert provider.calls == 7
    runtime.providers.clear()
    Path(revision.spec.location).unlink()
    runtime.clock = ledger.clock = lambda: T + timedelta(seconds=6)
    monkeypatch.setattr(queue, "complete", real_complete)
    Worker(runtime, queue).run_due(runtime.clock())
    assert client.get(f"/v1/jobs/{job_id}").json()["state"] == "completed"
    assert store.get_report(job_id) == report
    assert ledger.events_after(0, 1000) == events
    assert provider.calls == 7


def test_pending_origin_pages_are_absent_even_after_partial_execution(
    tmp_path, monkeypatch
):
    ledger, runtime, _, _, client = setup(tmp_path)
    provider = Provider()
    job_id, _ = configured(runtime, client, provider)
    queue = JobQueue(ledger)
    real_put = BacktestStore.put_origin

    def interrupted(self, outcome, **kwargs):
        real_put(self, outcome, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(BacktestStore, "put_origin", interrupted)
    with pytest.raises(KeyboardInterrupt):
        Worker(runtime, queue)._execute(queue.claim("old", T, 60), T)
    assert len(BacktestStore(ledger).list_origins(job_id).origins) == 1
    assert client.get(f"/v1/backtests/{job_id}").status_code == 404
    assert client.get(f"/v1/backtests/{job_id}/origins").status_code == 404


def test_provider_failures_keep_denominators_and_hide_private_exception(tmp_path):
    ledger, runtime, _, _, client = setup(tmp_path)
    provider = Provider(fails=True)
    job_id, _ = configured(runtime, client, provider)
    Worker(runtime, JobQueue(ledger)).run_due(T)
    response = client.get(f"/v1/backtests/{job_id}")
    assert response.status_code == 200, response.text
    final = response.json()["partitions"][2]
    assert (final["planned"], final["failed"], final["matched_count"]) == (2, 2, 0)
    page = client.get(f"/v1/backtests/{job_id}/origins")
    assert {o["reason_code"] for o in page.json()["origins"]} == {"execution_error"}
    assert "secret" not in page.text + response.text
    assert "/private" not in page.text + response.text


@pytest.mark.parametrize("disabled", [False, True])
def test_partial_provider_drift_is_explicit_without_rereading_source(
    tmp_path, monkeypatch, disabled
):
    ledger, runtime, _, revision, client = setup(tmp_path)
    provider = Provider()
    job_id, _ = configured(runtime, client, provider)
    queue = JobQueue(ledger)
    real_put = BacktestStore.put_origin

    def interrupted(self, outcome, **kwargs):
        real_put(self, outcome, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(BacktestStore, "put_origin", interrupted)
    old = queue.claim("old", T, 5)
    with pytest.raises(KeyboardInterrupt):
        Worker(runtime, queue)._execute(old, T)
    Path(revision.spec.location).unlink()
    if disabled:
        del runtime.providers["controlled"]
    else:
        provider.revision = "2"
    monkeypatch.setattr(BacktestStore, "put_origin", real_put)
    runtime.clock = ledger.clock = lambda: T + timedelta(seconds=6)
    Worker(runtime, queue).run_due(runtime.clock(), limit=1)
    assert queue.history(job_id)[0]["error"]["code"] == "provider_contract_changed"
    assert provider.calls == 1
    assert client.get(f"/v1/backtests/{job_id}").status_code == 404


def test_source_read_error_never_exposes_path(tmp_path):
    ledger, runtime, _, revision, client = setup(tmp_path)
    job_id = submit(client, request())
    Path(revision.spec.location).unlink()
    Worker(runtime, JobQueue(ledger)).run_due(T, limit=1)
    error = JobQueue(ledger).history(job_id)[0]["error"]
    assert error == {
        "code": "source_unavailable",
        "details": {"reason": "csv_read_failed"},
    }
    assert "private.csv" not in client.get(f"/v1/jobs/{job_id}").text
