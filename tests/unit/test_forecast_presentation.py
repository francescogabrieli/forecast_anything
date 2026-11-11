from datetime import UTC, datetime, timedelta

from forecast_anything.contracts import ForecastResult, RunRecord
from forecast_anything.presentations import present_run


def test_long_forecast_keeps_primary_and_aligned_baseline():
    now = datetime(2026, 11, 7, tzinfo=UTC)
    times = tuple(now + timedelta(days=i) for i in range(80))

    def forecast(provider):
        return ForecastResult(
            provider_id=provider,
            provider_revision="1",
            series_ids=("sales",),
            timestamps=times,
            units=("count",),
            point=(tuple(range(80)),),
            quantiles=None,
            paths=None,
            sample_group_id=None,
            assumptions=(),
        )

    run = RunRecord(
        primary_node_id="model",
        run_id="run",
        graph_id="configured-example",
        graph_version=1,
        as_of=now,
        snapshot_ids=(),
        requested_provider={"baseline": "seasonal_naive", "model": "model"},
        actual_provider={"baseline": "seasonal_naive", "model": "model"},
        state="succeeded",
        results={"baseline": forecast("seasonal_naive"), "model": forecast("model")},
        evidence_ids=(),
        scenario_id=None,
        parent_run_id=None,
    )
    presentation = present_run(run)
    assert presentation.primary_node_id == "model"
    assert presentation.baseline_node_id == "baseline"
    unrelated = run.model_copy(update={"primary_node_id": "other"})
    assert present_run(unrelated).baseline_node_id is None
    without_baseline = run.model_copy(
        update={"results": {"model": run.results["model"]}}
    )
    assert present_run(without_baseline).baseline_node_id is None
    arbitrary_graph = run.model_copy(update={"graph_id": "user-defined"})
    assert present_run(arbitrary_graph).baseline_node_id is None
    missing_primary = run.model_copy(
        update={"results": {"baseline": run.results["baseline"]}}
    )
    assert present_run(missing_primary).baseline_node_id is None
    assert len(presentation.points) == 64
    assert presentation.total_point_count == 160
    assert presentation.truncated
    primary = {
        (p.series_id, p.timestamp, p.unit)
        for p in presentation.points
        if p.node_id == "model"
    }
    baseline = {
        (p.series_id, p.timestamp, p.unit)
        for p in presentation.points
        if p.node_id == "baseline"
    }
    assert len(primary) == 32
    assert primary == baseline
