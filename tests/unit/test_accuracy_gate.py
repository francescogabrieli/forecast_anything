"""Small, offline regression gate for CPU inference and point-in-time backtests."""

from datetime import timedelta

import pytest
from backtest_fixtures import START, execute, outcomes, prepare, rows
from timestral import TimestralConfig, TimestralForecaster, TimestralModel
from torch import get_num_threads, manual_seed, random, set_num_threads

from forecast_anything.backtesting.store import BacktestStore
from forecast_anything.contracts import BacktestSettings, ForecastSelection
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.providers.timestral import TimestralProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger


@pytest.fixture
def cpu_provider():
    previous = get_num_threads()
    set_num_threads(1)
    try:
        with random.fork_rng(devices=[]):
            manual_seed(41)
            model = TimestralModel(
                TimestralConfig(
                    patch_size=2,
                    d_model=16,
                    num_heads=2,
                    mlp_hidden_dim=32,
                    block_schedule=("time",),
                    quantile_knots=(0.1, 0.5, 0.9),
                    block_size=2,
                    context_length=32,
                )
            ).eval()
        provider = TimestralProvider("synthetic-ci-checkpoint", "seed-41", "ci")
        provider._forecaster = TimestralForecaster(model)
        yield provider
    finally:
        set_num_threads(previous)


def test_cpu_forecast_accuracy_and_frozen_windows(tmp_path, cpu_provider):
    baseline = SeasonalNaiveProvider(4)
    ledger = Ledger(tmp_path / "accuracy.db")
    runtime = Runtime(
        ledger,
        {"timestral": cpu_provider, "seasonal_naive": baseline},
        {},
        lambda: START,
    )
    observed = tuple(
        row.model_copy(update={"value": 20 + 2 * (i % 4) + i // 8})
        for i, row in enumerate(rows(32))
    )
    captured_at = START + timedelta(days=31)
    # This revision is visible to the archive, but to none of the tested origins.
    archived_revision = observed[0].model_copy(
        update={"revision": "archived", "available_at": captured_at}
    )
    late = tuple(
        row.model_copy(
            update={
                "available_at": captured_at + timedelta(days=1),
                "revision": "late",
                "value": 999_999,
            }
        )
        for row in observed
    )
    settings = dict(
        selection=ForecastSelection(provider="timestral", horizon=2, baseline_period=4),
        settings=BacktestSettings(max_origins_per_partition=3),
        captured_at=captured_at,
        contracts={
            "timestral": cpu_provider.capabilities(),
            "seasonal_naive": baseline.capabilities(),
        },
    )
    archive_rows = (*observed, archived_revision)
    plan = prepare((*archive_rows, *late), **settings)
    clean = prepare(archive_rows, **settings)
    assert plan.origins == clean.origins
    assert plan.actuals_snapshot_id == clean.actuals_snapshot_id
    assert tuple(
        (
            origin.partition,
            (origin.target_start - START).days,
            (origin.target_end - START).days,
        )
        for origin in plan.origins
    ) == (
        ("exploration", 1, 2),
        ("exploration", 3, 4),
        ("exploration", 5, 6),
        ("selection", 16, 17),
        ("selection", 18, 19),
        ("selection", 20, 21),
        ("final", 24, 25),
        ("final", 26, 27),
        ("final", 28, 29),
    )

    store = BacktestStore(ledger)
    report = execute(runtime, store, plan)
    assert report.status == "completed"
    for outcome in outcomes(store, plan):
        if outcome.run_id is None:
            continue
        for snapshot_id in ledger.run_bindings(outcome.run_id).values():
            history = ledger.get_snapshot(snapshot_id)
            assert all(
                row.event_time <= outcome.nominal_origin
                and row.available_at <= outcome.issuance_time
                and row.revision == "a"
                for row in history.observations
            )
    exploration, selection, final = report.partitions
    assert [p.evaluated for p in report.partitions] == [1, 3, 3]
    assert [p.failed for p in report.partitions] == [0, 0, 0]
    assert [p.baseline_mae for p in report.partitions] == pytest.approx(
        [0, 2 / 3, 2 / 3]
    )
    # Reference scores from the pinned CPU fixture plus floating-point tolerance.
    for partition, reference in zip(
        report.partitions, (1.05286884, 1.94465033, 2.11136977), strict=True
    ):
        assert partition.model_mae is not None
        assert partition.model_mae <= reference + 1e-4
    assert exploration.relative_mae is None
    assert selection.relative_mae is not None and selection.relative_mae <= 2.9172
    assert final.relative_mae is not None and final.relative_mae <= 3.1673
