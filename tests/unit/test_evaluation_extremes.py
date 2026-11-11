"""Finite inputs must not poison scoring through intermediate float overflow."""

import pytest
from evaluation_fixtures import result

from forecast_anything.contracts import DomainError
from forecast_anything.evaluation.metrics import forecast_metrics, relative_mae


def test_extreme_point_mean_avoids_sum_and_subtraction_overflow():
    assert forecast_metrics(result((1e308, 1e308)), ((0.0, 0.0),))["mae"] == 1e308
    assert forecast_metrics(result((-1e308, 0.0)), ((1e308, 0.0),))["mae"] == 1e308


def test_extreme_pinball_and_interval_width_keep_representable_means():
    scores = forecast_metrics(
        result(point=None, quantiles={"0.1": ((-1e308, 0.0),), "0.9": ((1e308, 0.0),)}),
        ((1e308, 0.0),),
    )
    assert scores["pinball"]["0.1"] == pytest.approx(1e307)
    assert scores["intervals"]["0.1:0.9"]["width"] == 1e308


def test_genuinely_unrepresentable_score_has_explicit_numeric_error():
    with pytest.raises(DomainError, match="numerical_score_unrepresentable"):
        forecast_metrics(result((-1e308, -1e308)), ((1e308, 1e308),))


def test_unrepresentable_ratio_is_unavailable_without_discarding_scores():
    assert relative_mae(1e308, 1e-308) == (None, "ratio_unrepresentable")


@pytest.mark.parametrize("observed", [((1.0,),), ((float("inf"), 1.0),), ((),)])
def test_scoring_rejects_misaligned_nonfinite_or_empty_inputs(observed):
    with pytest.raises(DomainError, match="invalid_score_input"):
        forecast_metrics(result((1.0, 2.0)), observed)
