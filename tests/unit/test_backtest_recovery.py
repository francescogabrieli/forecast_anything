"""Lease fencing and immutable replay through real runtime and SQLite."""

from datetime import timedelta

import pytest
from backtest_fixtures import (
    START,
    ControlledProvider,
    controlled,
    execute,
    outcomes,
    rows,
)

from forecast_anything.contracts import DomainError
from forecast_anything.store import Ledger


@pytest.mark.parametrize("kind", ["registration", "during", "actual"])
def test_contract_drift_is_an_error_without_report_or_scored_wrong_revision(
    tmp_path, kind
):
    provider = ControlledProvider(
        drift_at=2 if kind == "during" else None, wrong_result=kind == "actual"
    )
    runtime, store, plan = controlled(tmp_path, provider)
    if kind == "registration":
        provider.revision = "2"
    with pytest.raises(DomainError) as error:
        execute(runtime, store, plan)
    assert error.value.code == "provider_contract_changed"
    with pytest.raises(DomainError):
        store.get_report(plan.backtest_id)
    if kind == "registration":
        assert provider.calls == 0
    else:
        assert all(
            o.status != "evaluated"
            or runtime.ledger.get_run(o.run_id).results["model"].provider_revision
            == "1"
            for o in outcomes(store, plan)
        )
    if kind == "actual":
        with pytest.raises(DomainError, match="provider_contract_changed"):
            execute(runtime, store, plan)


def test_recover_run_before_outcome_and_partial_outcomes_without_duplicate_inference(
    tmp_path, monkeypatch
):
    provider = ControlledProvider()
    runtime, store, plan = controlled(tmp_path, provider)
    put_origin = store.put_origin

    def crash(outcome, **kwargs):
        if outcome.ordinal == 1:
            raise RuntimeError("process stopped after run/evaluation publication")
        return put_origin(outcome, **kwargs)

    monkeypatch.setattr(store, "put_origin", crash)
    with pytest.raises(RuntimeError):
        execute(runtime, store, plan)
    assert provider.calls == 2
    assert len(outcomes(store, plan)) == 1
    # Reopen the database, as a new worker process would; the source is nonexistent.
    reopened = Ledger(runtime.ledger.path)
    from forecast_anything.backtesting.store import BacktestStore

    runtime.ledger = reopened
    report = execute(runtime, BacktestStore(reopened), store.get_plan("backtest"))
    assert provider.calls == 7
    assert report.partitions[-1].evaluated == 2
    assert len(reopened.events_after(0, 1000)) == 35
    assert (
        sum(
            len(reopened.evaluations_for_run(o.run_id))
            for o in outcomes(BacktestStore(reopened), plan)
        )
        == 7
    )


def test_expired_parent_lease_never_becomes_exclusion_or_publishes_report(tmp_path):
    from forecast_anything.jobs import JobQueue

    provider = ControlledProvider()
    runtime, store, plan = controlled(tmp_path, provider)
    runtime.ledger.clock = lambda: START
    queue = JobQueue(runtime.ledger)
    job = queue.enqueue("parent", {"test": "parent"})
    job = queue.claim("worker", START, 1)
    provider.before_call = lambda _request: setattr(
        runtime.ledger, "clock", lambda: START + timedelta(seconds=2)
    )
    with pytest.raises(DomainError, match="lease_lost"):
        execute(runtime, store, plan, lease_guard=job.guard)
    assert outcomes(store, plan) == ()
    assert runtime.ledger.events_after(0) == ()


def test_ledger_exposes_persisted_failure_event_without_raw_query(tmp_path):
    provider = ControlledProvider(fail_at=1)
    runtime, store, plan = controlled(tmp_path, provider)
    execute(runtime, store, plan)
    failed = outcomes(store, plan)[0]
    events = runtime.ledger.run_events(failed.run_id)
    assert events[-1].kind == "run_failed"
    assert events[-1].payload["error"]["code"] == "execution_error"


def test_runtime_stale_guard_prevents_graph_snapshot_and_provider_writes(tmp_path):
    from forecast_anything.backtesting.planning import build_forecast_graph
    from forecast_anything.jobs import LeaseGuard
    from forecast_anything.temporal import freeze

    provider = ControlledProvider()
    runtime, _store, plan = controlled(tmp_path, provider)
    snapshot = freeze(rows(4), START + timedelta(days=3))
    graph = build_forecast_graph(
        "sales", snapshot, plan.selection, "1d", graph_id="new-graph"
    )
    with pytest.raises(DomainError, match="lease_lost"):
        runtime.run(
            graph,
            {"sales": snapshot},
            snapshot.as_of,
            "stale",
            lease_guard=LeaseGuard("absent", "stale"),
        )
    assert provider.calls == 0
    with pytest.raises(DomainError, match="not_found"):
        runtime.ledger.get_graph("new-graph", 1)
    with pytest.raises(DomainError, match="not_found"):
        runtime.ledger.get_snapshot(snapshot.snapshot_id)


def test_contract_change_after_partial_restart_does_not_mix_revisions(
    tmp_path, monkeypatch
):
    provider = ControlledProvider()
    runtime, store, plan = controlled(tmp_path, provider)
    put_origin = store.put_origin

    def stop_after_first(outcome, **kwargs):
        put_origin(outcome, **kwargs)
        raise RuntimeError("worker stopped")

    monkeypatch.setattr(store, "put_origin", stop_after_first)
    with pytest.raises(RuntimeError):
        execute(runtime, store, plan)
    provider.revision = "2"
    monkeypatch.setattr(store, "put_origin", put_origin)
    with pytest.raises(DomainError, match="provider_contract_changed"):
        execute(runtime, store, store.get_plan(plan.backtest_id))
    assert provider.calls == 1
    assert len(outcomes(store, plan)) == 1
    with pytest.raises(DomainError, match="not_found"):
        store.get_report(plan.backtest_id)


@pytest.mark.parametrize("defect", ["calendar", "lease", "infrastructure"])
def test_provider_calendar_failure_is_retained_but_lease_and_infrastructure_propagate(
    tmp_path, monkeypatch, defect
):
    provider = ControlledProvider()
    runtime, store, plan = controlled(tmp_path, provider)
    if defect == "calendar":
        original = provider.forecast

        def wrong_calendar(request):
            result = original(request)
            result.timestamps = tuple(t + timedelta(hours=1) for t in result.timestamps)
            return result

        monkeypatch.setattr(provider, "forecast", wrong_calendar)
        report = execute(runtime, store, plan)
        assert report.status == "insufficient_evidence"
        assert sum(p.failed for p in report.partitions) == 7
        assert all(
            o.reason_code == "provider_output_invalid" for o in outcomes(store, plan)
        )
    elif defect == "lease":

        def lost(_request):
            raise DomainError("lease_lost", {})

        monkeypatch.setattr(provider, "forecast", lost)
        with pytest.raises(DomainError, match="lease_lost"):
            execute(runtime, store, plan)
        assert outcomes(store, plan) == ()
    else:

        def broken(*args, **kwargs):
            raise OSError("disk unavailable")

        monkeypatch.setattr(runtime.ledger, "append_evaluation", broken)
        with pytest.raises(OSError, match="disk unavailable"):
            execute(runtime, store, plan)
        assert outcomes(store, plan) == ()


def test_completed_report_recovery_does_not_require_optional_provider_registration(
    tmp_path,
):
    provider = ControlledProvider()
    runtime, store, plan = controlled(tmp_path, provider)
    report = execute(runtime, store, plan)
    runtime.providers.clear()
    recovered = execute(runtime, store, store.get_plan(plan.backtest_id))
    assert recovered.report_id == report.report_id
    assert provider.calls == 7


@pytest.mark.parametrize("quantile_defect", ["invalid_level", "crossing"])
def test_invalid_provider_quantiles_recover_completed_child_and_preserve_failed_denominator(
    tmp_path, monkeypatch, quantile_defect
):
    class InvalidQuantilesProvider(ControlledProvider):
        def forecast(self, request):
            result = super().forecast(request)
            if self.calls == 1:
                result.quantiles = (
                    {"not-a-probability-private": result.point}
                    if quantile_defect == "invalid_level"
                    else {"0.1": ((50, 50),), "0.9": ((0, 0),)}
                )
            return result

    provider = InvalidQuantilesProvider()
    runtime, store, plan = controlled(tmp_path, provider)
    put_origin = store.put_origin

    def crash_before_outcome(outcome, **kwargs):
        raise RuntimeError("worker stopped before outcome publication")

    monkeypatch.setattr(store, "put_origin", crash_before_outcome)
    with pytest.raises(RuntimeError, match="worker stopped before outcome publication"):
        execute(runtime, store, plan)
    child = runtime.ledger.get_run_by_key("backtest/backtest/0")
    assert child is not None and child.state == "completed"
    assert provider.calls == 1
    assert outcomes(store, plan) == ()
    assert runtime.ledger.evaluations_for_run(child.run_id) == ()
    with pytest.raises(DomainError, match="not_found"):
        store.get_report(plan.backtest_id)

    monkeypatch.setattr(store, "put_origin", put_origin)
    report = execute(runtime, store, store.get_plan(plan.backtest_id))
    published = outcomes(store, plan)
    failed = published[0]
    assert (failed.status, failed.reason_code, failed.run_id, failed.evaluation_id) == (
        "failed",
        "provider_output_invalid",
        child.run_id,
        None,
    )
    assert failed.matched_count == 0
    assert "private" not in failed.model_dump_json()
    assert all(outcome.status == "evaluated" for outcome in published[1:])
    assert report.status == "completed"
    exploration = report.partitions[0]
    assert (
        exploration.planned,
        exploration.failed,
        exploration.evaluated,
        exploration.matched_count,
    ) == (3, 1, 2, 4)
    assert exploration.model_mae == exploration.baseline_mae == 1.5
    assert report.partitions[-1].evaluated == 2
    assert provider.calls == 7
    events = runtime.ledger.events_after(0, 1000)
    assert len(events) == 35
    assert (
        sum(
            len(runtime.ledger.evaluations_for_run(origin.run_id))
            for origin in published
        )
        == 6
    )
    assert execute(runtime, store, plan).report_id == report.report_id
    assert runtime.ledger.events_after(0, 1000) == events
    assert provider.calls == 7


@pytest.mark.parametrize(
    "error_code", ["lease_lost", "graph_identity_mismatch", "corrupt_backtest_run"]
)
def test_non_provider_evaluation_errors_propagate_without_origin_exclusion(
    tmp_path, monkeypatch, error_code
):
    provider = ControlledProvider()
    runtime, store, plan = controlled(tmp_path, provider)

    def invalid_evaluation(*args, **kwargs):
        raise DomainError(error_code, {})

    monkeypatch.setattr(
        "forecast_anything.backtesting.runner.evaluate_run", invalid_evaluation
    )
    with pytest.raises(DomainError, match=error_code):
        execute(runtime, store, plan)
    assert outcomes(store, plan) == ()
    with pytest.raises(DomainError, match="not_found"):
        store.get_report(plan.backtest_id)
