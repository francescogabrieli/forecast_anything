"""Real runtime/SQLite replay with independently checked numerical evidence."""

from datetime import timedelta

import pytest
from backtest_fixtures import (
    START,
    ControlledProvider,
    controlled,
    execute,
    outcomes,
    prepare,
    rows,
    setup,
)

from forecast_anything.contracts import BacktestSettings, ForecastSelection


def test_explicit_periods_manual_maes_denominators_and_idempotent_replay(tmp_path):
    runtime, store, plan = setup(tmp_path)
    report = execute(runtime, store, plan)
    exploration, selection, final = report.partitions
    assert report.status == "completed"
    assert (
        exploration.planned,
        exploration.evaluated,
        exploration.excluded,
        exploration.matched_count,
    ) == (3, 2, 1, 4)
    for score in report.partitions:
        assert score.model_mae == 2
        assert score.baseline_mae == 1.5
        assert score.relative_mae == pytest.approx(4 / 3)
    assert (
        selection.planned,
        selection.matched_count,
        final.planned,
        final.matched_count,
    ) == (2, 4, 2, 4)
    for origin in outcomes(store, plan)[1:]:
        run = runtime.ledger.get_run(origin.run_id)
        evaluation = runtime.ledger.get_evaluation(origin.evaluation_id)
        assert evaluation.metrics["model"]["baseline_node_id"] == "baseline"
        assert run.results["model"].timestamps == (
            origin.target_start,
            origin.target_end,
        )
        assert origin.model_mae == evaluation.metrics["model"]["mae"]
    events = runtime.ledger.events_after(0, limit=1000)
    assert execute(runtime, store, plan).report_id == report.report_id
    assert runtime.ledger.events_after(0, limit=1000) == events


def test_revision_availability_and_future_history_have_literal_forecasts(tmp_path):
    original = rows()
    revised = original[2].model_copy(
        update={"available_at": START + timedelta(days=3), "revision": "b", "value": 30}
    )
    future = original[0].model_copy(
        update={"event_time": START + timedelta(days=99), "value": 999}
    )
    plan = prepare(
        (*original, revised, future),
        selection=ForecastSelection(
            provider="seasonal_naive", horizon=1, options={"period": 2}
        ),
    )
    runtime, store, _ = setup(tmp_path, plan)
    execute(runtime, store, plan)
    origins = outcomes(store, plan)
    day2 = next(o for o in origins if o.nominal_origin == START + timedelta(days=2))
    day3 = next(o for o in origins if o.nominal_origin == START + timedelta(days=3))
    assert runtime.ledger.get_run(day2.run_id).results["model"].point == ((2.0,),)
    # On day 3, period 2 now uses the late revision available that day.
    binding = runtime.ledger.run_bindings(day3.run_id)["sales"]
    history = runtime.ledger.get_snapshot(binding)
    assert [o.value for o in history.observations] == [1, 2, 30, 4]
    assert runtime.ledger.get_run(day3.run_id).results["model"].point == ((30.0,),)
    assert max(o.event_time for o in history.observations) == day3.nominal_origin


def test_publication_offset_changes_history_without_moving_targets(tmp_path):
    delayed = tuple(
        row.model_copy(update={"available_at": row.available_at + timedelta(hours=1)})
        for row in rows()
    )
    zero = prepare(delayed, captured_at=START + timedelta(days=16))
    offset = prepare(
        delayed,
        settings=BacktestSettings(origin_offset_seconds=3600),
        captured_at=START + timedelta(days=16),
    )
    assert [(o.target_start, o.target_end) for o in zero.origins] == [
        (o.target_start, o.target_end) for o in offset.origins
    ]
    runtime, store, _ = setup(tmp_path, zero)
    assert execute(runtime, store, zero).status == "insufficient_evidence"
    assert all(o.status == "excluded" for o in outcomes(store, zero))
    other = tmp_path / "offset"
    other.mkdir()
    runtime, store, _ = setup(other, offset)
    assert execute(runtime, store, offset).partitions[-1].model_mae == 2


def test_missing_calendar_cell_excludes_history_and_incomplete_actuals_remain_insufficient(
    tmp_path,
):
    data = tuple(row for i, row in enumerate(rows()) if i != 14)
    plan = prepare(data)
    runtime, store, _ = setup(tmp_path, plan)
    report = execute(runtime, store, plan)
    final = report.partitions[-1]
    assert (
        final.planned,
        final.evaluated,
        final.excluded,
        final.insufficient,
        final.matched_count,
    ) == (2, 1, 0, 1, 2)
    last = outcomes(store, plan)[-1]
    assert (last.status, last.reason_code) == (
        "insufficient_evidence",
        "incomplete_actuals",
    )
    assert last.evaluation_id is not None
    # Removing an earlier cell must not produce compressed histories/shifted runs.
    other = tmp_path / "missing"
    other.mkdir()
    runtime, store, plan = setup(
        other, prepare(tuple(r for i, r in enumerate(rows()) if i != 3))
    )
    report = execute(runtime, store, plan)
    assert report.status == "insufficient_evidence"
    assert report.partitions[-1].excluded == 2


def test_zero_baseline_has_explicit_null_ratio(tmp_path):
    data = tuple(r.model_copy(update={"value": 5}) for r in rows())
    runtime, store, plan = setup(tmp_path, prepare(data))
    final = execute(runtime, store, plan).partitions[-1]
    assert final.model_mae == final.baseline_mae == 0
    assert final.relative_mae is None
    assert final.relative_mae_reason == "zero_baseline_mae"


def test_plan_actuals_and_membership_are_persisted_before_provider_and_failure_is_counted(
    tmp_path,
):
    provider = ControlledProvider(fail_at=2)
    runtime, store, plan = controlled(tmp_path, provider)

    def check(_request):
        assert store.get_plan("backtest").plan_id == plan.plan_id
        assert (
            runtime.ledger.get_snapshot(plan.actuals_snapshot_id).as_of
            == plan.archive.captured_at
        )
        assert len(store.get_plan("backtest").origins) == 7

    provider.before_call = check
    report = execute(runtime, store, plan)
    exploration = report.partitions[0]
    assert (
        exploration.planned,
        exploration.evaluated,
        exploration.failed,
        exploration.matched_count,
    ) == (3, 2, 1, 4)
    failed = outcomes(store, plan)[1]
    assert failed.status == "failed" and failed.run_id and not failed.evaluation_id
    assert failed.reason_code == "execution_error"
    assert "controlled failure" not in report.model_dump_json()


def test_partition_reducer_is_count_weighted_and_retains_unscored_denominator():
    from forecast_anything.backtesting.contracts import OriginOutcome
    from forecast_anything.backtesting.runner import partition_score

    plan = prepare()
    common = dict(
        backtest_id=plan.backtest_id,
        plan_id=plan.plan_id,
        **plan.origins[-1].model_dump(),
    )
    small = OriginOutcome(
        **common,
        status="evaluated",
        run_id="run1",
        evaluation_id="eval1",
        matched_count=1,
        model_mae=10,
        baseline_mae=2,
    )
    large = OriginOutcome(
        **{**common, "ordinal": 9},
        status="evaluated",
        run_id="run2",
        evaluation_id="eval2",
        matched_count=3,
        model_mae=2,
        baseline_mae=6,
    )
    failed = OriginOutcome(
        **{**common, "ordinal": 10}, status="failed", reason_code="execution_error"
    )
    excluded = OriginOutcome(
        **{**common, "ordinal": 11}, status="excluded", reason_code="missing_history"
    )
    score = partition_score("final", (small, large, failed, excluded))
    assert (
        score.planned,
        score.evaluated,
        score.failed,
        score.excluded,
        score.matched_count,
    ) == (4, 2, 1, 1, 4)
    assert (score.model_mae, score.baseline_mae, score.relative_mae) == (4, 5, 0.8)


def test_every_final_target_missing_produces_insufficient_final_without_dropping_origins(
    tmp_path,
):
    data = tuple(
        row.model_copy(update={"value": None}) if 12 <= i <= 15 else row
        for i, row in enumerate(rows())
    )
    runtime, store, plan = setup(tmp_path, prepare(data))
    report = execute(runtime, store, plan)
    final = report.partitions[-1]
    assert report.status == "insufficient_evidence"
    assert (final.planned, final.evaluated, final.insufficient, final.excluded) == (
        2,
        0,
        1,
        1,
    )
    assert final.model_mae is final.baseline_mae is final.relative_mae is None
    assert final.relative_mae_reason == "no_matched_cells"


def test_path_only_provider_is_insufficient_score_representation_not_missing_actuals(
    tmp_path,
):
    class PathsProvider(ControlledProvider):
        def capabilities(self):
            return (
                super()
                .capabilities()
                .model_copy(update={"representations": ("joint_paths",)})
            )

        def forecast(self, request):
            result = super().forecast(request)
            return result.model_copy(
                update={
                    "point": None,
                    "paths": (result.point,),
                    "sample_group_id": "paths",
                }
            )

    runtime, store, plan = controlled(tmp_path, PathsProvider())
    report = execute(runtime, store, plan)
    assert report.status == "insufficient_evidence"
    assert all(
        origin.reason_code == "unsupported_score_representation"
        for origin in outcomes(store, plan)
    )
    assert all(
        partition.insufficient == partition.planned for partition in report.partitions
    )


def test_selected_seasonal_default_is_explicit_and_independent_of_adapter_instance_default(
    tmp_path,
):
    plan = prepare(selection=ForecastSelection(provider="seasonal_naive", horizon=2))
    runtime, store, _ = setup(tmp_path, plan)
    report = execute(runtime, store, plan)
    assert all(score.evaluated == score.planned for score in report.partitions)
    assert all(
        score.model_mae == score.baseline_mae == 1.5 for score in report.partitions
    )
    first = outcomes(store, plan)[0]
    run = runtime.ledger.get_run(first.run_id)
    assert run.results["model"].point == ((1, 1),)
    assert any("default period=1" in assumption for assumption in report.assumptions)
    graph = runtime.ledger.get_graph(run.graph_id, run.graph_version)
    assert graph.nodes[-1].config["options"] == {"period": 1}
