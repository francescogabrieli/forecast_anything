"""Replay numerical extremes through real Runtime and immutable SQLite writes."""

import pytest
from backtest_fixtures import (
    ControlledProvider,
    controlled,
    execute,
    outcomes,
    prepare,
    rows,
)

from forecast_anything.contracts import ForecastSelection


@pytest.mark.parametrize(
    "actual_scale,points",
    [
        (1.0, (1e308, 1e308)),
        (1e-308, (1e308, 1e308)),
        (-1e308, (1e308, 1e308)),
        (1.0, (1e308, 0.0)),
    ],
)
@pytest.mark.parametrize("horizon", [1, 2])
def test_extreme_child_replay_and_report_regeneration(
    tmp_path, monkeypatch, actual_scale, points, horizon
):
    class ExtremeProvider(ControlledProvider):
        def forecast(self, request):
            result = super().forecast(request)
            result.point = (points[: request.horizon],)
            return result

    provider = ExtremeProvider()
    data = tuple(
        o.model_copy(
            update={
                "value": (i + 1) * actual_scale if actual_scale > 0 else actual_scale
            }
        )
        for i, o in enumerate(rows())
    )
    runtime, store, plan = controlled(tmp_path, provider, data=data)
    plan = prepare(
        data,
        selection=ForecastSelection(provider="controlled", horizon=horizon),
        contracts=plan.provider_contracts,
    )
    put_origin, put_report = store.put_origin, store.put_report

    def before_outcome(*args, **kwargs):
        raise KeyboardInterrupt("after child")

    monkeypatch.setattr(store, "put_origin", before_outcome)
    with pytest.raises(KeyboardInterrupt):
        execute(runtime, store, plan)
    child = runtime.ledger.get_run_by_key("backtest/backtest/0")
    assert child.state == "completed"
    assert provider.calls == 1
    assert outcomes(store, plan) == ()
    monkeypatch.setattr(store, "put_origin", put_origin)

    def before_report(*args, **kwargs):
        raise KeyboardInterrupt("after all outcomes")

    monkeypatch.setattr(store, "put_report", before_report)
    with pytest.raises(KeyboardInterrupt):
        execute(runtime, store, plan)
    saved = outcomes(store, plan)
    assert len(saved) == (15 if horizon == 1 else 7)
    assert saved[0].run_id == child.run_id
    assert provider.calls == len(saved)
    monkeypatch.setattr(store, "put_report", put_report)
    report = execute(runtime, store, store.get_plan(plan.backtest_id))
    assert outcomes(store, plan) == saved
    assert provider.calls == len(saved)
    for score in report.partitions:
        assert score.planned == score.evaluated + score.failed
        if actual_scale < 0:
            assert score.failed == score.planned
            assert {o.reason_code for o in saved} == {"numerical_score_unrepresentable"}
        else:
            assert score.model_mae == (1e308 if horizon == 1 or points[1] else 5e307)
            assert score.relative_mae_reason == (
                "ratio_unrepresentable" if actual_scale < 1 else None
            )
    assert execute(runtime, store, plan) == report
