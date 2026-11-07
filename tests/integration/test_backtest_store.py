"""Immutable evidence survives reopening, validates linkage and obeys parent fencing."""

import json
import sqlite3
from datetime import datetime, timezone
from importlib.resources import files

import pytest
from pydantic import ValidationError

from forecast_anything.contracts import DomainError, Snapshot
from forecast_anything.jobs import JobQueue, LeaseGuard
from forecast_anything.store import MIGRATIONS, Ledger

NOW = datetime(2026, 1, 10, tzinfo=timezone.utc)


def plan_fixture(ledger, backtest_id="bt"):
    from forecast_anything.backtesting.contracts import (
        BacktestPlan,
        ObservationArchive,
        PlannedOrigin,
    )
    from forecast_anything.contracts import Capabilities, ForecastSelection

    snapshot = Snapshot(
        snapshot_id="actuals", as_of=NOW, observations=(), assumptions=()
    )
    ledger.put_snapshot(snapshot)
    archive = ObservationArchive(
        source_id="s", source_revision="rev", captured_at=NOW, observations=()
    )
    return BacktestPlan(
        backtest_id=backtest_id,
        archive=archive,
        selection=ForecastSelection(provider="seasonal_naive", horizon=1),
        provider_contracts={
            "seasonal_naive": Capabilities(
                provider_id="seasonal_naive",
                provider_revision="v1",
                representations=("point",),
                supports_known_future=False,
            )
        },
        frequency="D",
        calendar=("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"),
        origins=(
            PlannedOrigin(
                ordinal=0,
                partition="final",
                nominal_origin="2026-01-01T00:00:00Z",
                issuance_time="2026-01-01T00:00:00Z",
                target_start="2026-01-02T00:00:00Z",
                target_end="2026-01-02T00:00:00Z",
            ),
        ),
        actuals_snapshot_id="actuals",
        assumptions=("declared",),
    )


def outcome_fixture(plan, **updates):
    from forecast_anything.backtesting.contracts import OriginOutcome

    return OriginOutcome(
        backtest_id=plan.backtest_id,
        plan_id=plan.plan_id,
        **plan.origins[0].model_dump(),
        status="excluded",
        reason_code="missing_history",
        **updates,
    )


def report_fixture(plan):
    from forecast_anything.backtesting.contracts import BacktestReport, PartitionScore

    return BacktestReport(
        backtest_id=plan.backtest_id,
        plan_id=plan.plan_id,
        archive_id=plan.archive.archive_id,
        source_id="s",
        source_revision="rev",
        captured_at=NOW,
        actuals_snapshot_id="actuals",
        selection=plan.selection,
        settings=plan.settings,
        provider_contracts=plan.provider_contracts,
        frequency="D",
        status="insufficient_evidence",
        partitions=(
            PartitionScore(partition="exploration", planned=0),
            PartitionScore(partition="selection", planned=0),
            PartitionScore(partition="final", planned=1, excluded=1),
        ),
        assumptions=plan.assumptions,
    )


def test_plan_hash_covers_provider_revision_and_rejects_missing_contracts(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    plan = plan_fixture(ledger)
    changed = plan.model_dump(exclude={"plan_id"})
    changed["provider_contracts"]["seasonal_naive"]["provider_revision"] = "v2"
    assert type(plan)(**changed).plan_id != plan.plan_id
    with pytest.raises(ValidationError):
        type(plan)(**{**plan.model_dump(), "provider_contracts": {}})


def test_immutable_storage_reopens_and_paginates_without_private_archive(tmp_path):
    from forecast_anything.backtesting.store import BacktestStore

    path = tmp_path / "state.db"
    ledger = Ledger(path)
    store = BacktestStore(ledger)
    plan = plan_fixture(ledger)
    assert store.put_plan(plan) == plan.plan_id
    assert store.put_plan(plan) == plan.plan_id
    assert store.get_plan("bt") == plan
    outcome = outcome_fixture(plan)
    assert store.put_origin(outcome) == 0
    assert store.put_origin(outcome) == 0
    page = store.list_origins("bt", offset=0, limit=1)
    assert page.origins == (outcome,)
    assert page.next_offset is None
    for offset in (2**63 - 1, 2**63, 10**100):
        empty = store.list_origins("bt", offset=offset, limit=1)
        assert empty.offset == offset
        assert empty.origins == ()
        assert empty.next_offset is None
    assert store.get_origin("bt", 0) == outcome
    report = report_fixture(plan)
    assert store.put_report(report) == report.report_id
    assert store.put_report(report) == report.report_id
    assert BacktestStore(Ledger(path)).get_report("bt") == report
    assert "observations" not in json.loads(report.model_dump_json())
    assert "archive" not in json.loads(report.model_dump_json())
    for offset, limit in ((-1, 1), (0, 0), (0, 51), (True, 1)):
        with pytest.raises(DomainError):
            store.list_origins("bt", offset=offset, limit=limit)
    with pytest.raises(DomainError, match="not_found"):
        store.list_origins("absent")
    with pytest.raises(DomainError, match="not_found"):
        store.list_origins("absent", offset=10**100)


def test_store_rejects_changed_identities_and_missing_or_mismatched_references(
    tmp_path,
):
    from forecast_anything.backtesting.store import BacktestStore

    ledger = Ledger(tmp_path / "state.db")
    store = BacktestStore(ledger)
    plan = plan_fixture(ledger)
    with pytest.raises(DomainError, match="invalid_backtest_record"):
        store.put_plan(plan.model_copy(update={"plan_id": "forged"}))
    store.put_plan(plan)
    changed = type(plan)(
        **{**plan.model_dump(exclude={"plan_id"}), "assumptions": ("different",)}
    )
    with pytest.raises(DomainError, match="immutable_identity"):
        store.put_plan(changed)
    for changes in (
        {"backtest_id": "absent"},
        {"plan_id": "absent"},
        {"ordinal": 4},
        {"target_end": NOW},
        {"run_id": "absent"},
    ):
        with pytest.raises(DomainError):
            store.put_origin(outcome_fixture(plan).model_copy(update=changes))
    with pytest.raises(DomainError):
        store.put_report(report_fixture(plan))  # planned outcome not yet published
    store.put_origin(outcome_fixture(plan))
    with pytest.raises(DomainError, match="invalid_backtest_reference"):
        bad = report_fixture(plan).model_dump(exclude={"report_id"})
        bad["source_revision"] = "other"
        store.put_report(type(report_fixture(plan))(**bad))
    with pytest.raises(DomainError, match="immutable_identity"):
        store.put_origin(
            outcome_fixture(plan).model_copy(update={"reason_code": "other"})
        )


def test_parent_lease_fences_all_writes_including_identical_retries(tmp_path):
    from forecast_anything.backtesting.store import BacktestStore

    ledger = Ledger(tmp_path / "state.db", clock=lambda: NOW)
    store = BacktestStore(ledger)
    plan = plan_fixture(ledger)
    queue = JobQueue(ledger)
    queue.enqueue("parent", {})
    job = queue.claim("owner", NOW, 60)
    assert job is not None
    store.put_plan(plan, lease_guard=job.guard)
    store.put_origin(outcome_fixture(plan), lease_guard=job.guard)
    report = report_fixture(plan)
    store.put_report(report, lease_guard=job.guard)
    stale = LeaseGuard(job.job_id, "stale")
    for write, record in (
        (store.put_plan, plan),
        (store.put_origin, outcome_fixture(plan)),
        (store.put_report, report),
    ):
        with pytest.raises(DomainError, match="lease_lost"):
            write(record, lease_guard=stale)


def test_migration_preserves_existing_ledger_and_blocks_raw_rewrites(tmp_path):
    from forecast_anything.backtesting.store import BacktestStore

    path = tmp_path / "state.db"
    with sqlite3.connect(path) as connection:
        for name in MIGRATIONS[:7]:
            connection.executescript(
                files("forecast_anything").joinpath("migrations", name).read_text()
            )
        connection.execute("INSERT INTO snapshots VALUES ('old', '{}')")
    ledger = Ledger(path)
    store = BacktestStore(ledger)
    plan = plan_fixture(ledger)
    store.put_plan(plan)
    store.put_origin(outcome_fixture(plan))
    store.put_report(report_fixture(plan))
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT content FROM snapshots WHERE snapshot_id='old'"
        ).fetchone() == ("{}",)
        assert connection.execute("PRAGMA user_version").fetchone() == (9,)
        for table in ("backtest_plans", "backtest_origins", "backtest_reports"):
            for mutation in (
                f"DELETE FROM {table}",
                f"UPDATE {table} SET content = '{{}}'",
            ):
                with pytest.raises(sqlite3.IntegrityError):
                    connection.execute(mutation)


def test_store_detects_corrupt_archive_on_read(tmp_path):
    from forecast_anything.backtesting.store import BacktestStore

    ledger = Ledger(tmp_path / "state.db")
    store = BacktestStore(ledger)
    plan = plan_fixture(ledger)
    store.put_plan(plan)
    with ledger._connection() as connection:
        connection.execute("DROP TRIGGER backtest_plans_no_update")
        payload = plan.model_dump(mode="json")
        payload["archive"]["source_revision"] = "tampered"
        connection.execute(
            "UPDATE backtest_plans SET content=?", (json.dumps(payload),)
        )
    with pytest.raises(DomainError, match="invalid_backtest_record") as error:
        store.get_plan("bt")
    assert str(tmp_path) not in error.value.model_dump_json()


def test_evaluated_outcome_requires_published_matching_evaluation(tmp_path):
    from forecast_anything.backtesting.contracts import OriginOutcome
    from forecast_anything.backtesting.store import BacktestStore
    from forecast_anything.contracts import EvaluationRecord, RunRecord

    ledger = Ledger(tmp_path / "state.db")
    store = BacktestStore(ledger)
    plan = plan_fixture(ledger)
    store.put_plan(plan)
    run = RunRecord(
        run_id="run",
        graph_id="g",
        graph_version=1,
        as_of=NOW,
        snapshot_ids=(),
        requested_provider={},
        actual_provider={},
        state="succeeded",
        results={},
        evidence_ids=(),
        scenario_id=None,
        parent_run_id=None,
    )
    ledger.append_run(run, (), "key")
    evaluation = EvaluationRecord(
        evaluation_id="eval",
        run_id="run",
        actuals_snapshot_id="actuals",
        status="evaluated",
        metrics={
            "model": {"status": "evaluated", "count": 1, "mae": 2.0},
            "baseline": {"status": "evaluated", "count": 1, "mae": 4.0},
        },
        origin_count=1,
        assumptions=(),
    )
    outcome = OriginOutcome(
        backtest_id="bt",
        plan_id=plan.plan_id,
        **plan.origins[0].model_dump(),
        status="evaluated",
        run_id="run",
        evaluation_id="eval",
        matched_count=1,
        model_mae=2.0,
        baseline_mae=4.0,
    )
    with pytest.raises(DomainError, match="invalid_backtest_reference"):
        store.put_origin(outcome)
    ledger.append_evaluation(evaluation)
    with pytest.raises(DomainError, match="invalid_backtest_reference"):
        store.put_origin(outcome.model_copy(update={"matched_count": 2}))
    assert store.put_origin(outcome) == 0
    other = run.model_copy(update={"run_id": "other"})
    ledger.append_run(other, (), "other")
    with pytest.raises(DomainError, match="invalid_backtest_reference"):
        store.put_origin(outcome.model_copy(update={"run_id": "other"}))


def test_origin_pagination_is_stable_and_marks_only_remaining_rows(tmp_path):
    from forecast_anything.backtesting.contracts import PlannedOrigin
    from forecast_anything.backtesting.store import BacktestStore

    ledger = Ledger(tmp_path / "state.db")
    store = BacktestStore(ledger)
    plan = plan_fixture(ledger)
    first = plan.origins[0]
    origins = tuple(
        PlannedOrigin(**{**first.model_dump(), "ordinal": ordinal})
        for ordinal in range(3)
    )
    plan = type(plan)(**{**plan.model_dump(exclude={"plan_id"}), "origins": origins})
    store.put_plan(plan)
    for origin in reversed(origins):
        store.put_origin(outcome_fixture(plan).model_copy(update=origin.model_dump()))
    first_page = store.list_origins("bt", limit=2)
    assert tuple(outcome.ordinal for outcome in first_page.origins) == (0, 1)
    assert first_page.next_offset == 2
    final_page = store.list_origins("bt", offset=first_page.next_offset, limit=2)
    assert tuple(outcome.ordinal for outcome in final_page.origins) == (2,)
    assert final_page.next_offset is None
