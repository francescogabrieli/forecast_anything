from datetime import datetime, timedelta, timezone

from forecast_anything.contracts import ForecastResult, RunRecord
from forecast_anything.presentations import present_run


def test_long_forecast_keeps_primary_and_aligned_baseline():
    now = datetime(2026, 11, 7, tzinfo=timezone.utc)
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
        graph_id="graph",
        graph_version=1,
        as_of=now,
        snapshot_ids=(),
        requested_provider={"baseline": "baseline", "model": "model"},
        actual_provider={"baseline": "baseline", "model": "model"},
        state="succeeded",
        results={"baseline": forecast("baseline"), "model": forecast("model")},
        evidence_ids=(),
        scenario_id=None,
        parent_run_id=None,
    )
    presentation = present_run(run)
    assert presentation.primary_node_id == "model"
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
