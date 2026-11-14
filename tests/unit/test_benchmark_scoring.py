import sys
from datetime import UTC, datetime
from pathlib import Path

from forecast_anything.contracts import ForecastResult

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.scoring import (
    bootstrap_skill_interval,
    diebold_mariano,
    score_origin,
)


def forecast(point, quantiles=None):
    return ForecastResult(
        provider_id="fixture",
        provider_revision="1",
        series_ids=("series",),
        timestamps=tuple(
            datetime(2020, 1, day, tzinfo=UTC) for day in range(1, len(point[0]) + 1)
        ),
        units=("units",),
        point=point,
        quantiles=quantiles,
        paths=None,
        sample_group_id=None,
        assumptions=(),
    )


def test_origin_scores_mase_smape_and_weighted_quantile_loss():
    result = forecast(
        ((1.0, 5.0, 4.0, 9.0),),
        {"0.1": ((1.0, 2.0, 3.0, 4.0),), "0.9": ((3.0, 4.0, 5.0, 6.0),)},
    )

    scores = score_origin(
        result,
        actual=((2.0, 4.0, 6.0, 8.0),),
        history=((1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0),),
        period=2,
    )

    assert scores["mase"] == 0.625
    assert scores["smape"] == 35.16339869281046
    assert scores["wql"] == 0.19
    assert scores["mase_reason"] is None
    assert scores["wql_reason"] is None


def test_mase_reports_zero_seasonal_scale_as_undefined():
    scores = score_origin(
        forecast(((2.0, 2.0),)),
        actual=((2.0, 2.0),),
        history=((2.0, 2.0, 2.0, 2.0),),
        period=1,
    )

    assert scores["mase"] is None
    assert scores["mase_reason"] == "zero_seasonal_scale"


def test_weighted_quantile_loss_is_undefined_for_point_only_forecasts():
    scores = score_origin(
        forecast(((1.0, 2.0),)),
        actual=((2.0, 3.0),),
        history=((1.0, 2.0, 3.0),),
        period=1,
    )

    assert scores["wql"] is None
    assert scores["wql_reason"] == "quantiles_unavailable"


def test_moving_block_bootstrap_is_paired_and_deterministic():
    first = bootstrap_skill_interval(
        (1.0, 2.0, 1.0), (2.0, 2.0, 4.0), horizon=2, samples=200, seed=17
    )
    second = bootstrap_skill_interval(
        (1.0, 2.0, 1.0), (2.0, 2.0, 4.0), horizon=2, samples=200, seed=17
    )

    assert first == second
    assert first["estimate"] == 0.5
    assert first["block_size"] == 2
    assert first["lower"] <= first["estimate"] <= first["upper"]


def test_diebold_mariano_accounts_for_overlapping_origins():
    result = diebold_mariano(
        (1.0, 1.0, 2.0, 1.0),
        (2.0, 3.0, 2.0, 3.0),
        horizon=3,
        stride=1,
    )

    assert result["lag"] == 2
    assert result["count"] == 4
    assert result["statistic"] < 0
    assert 0 <= result["p_value"] <= 1
