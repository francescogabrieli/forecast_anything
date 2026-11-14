"""Benchmark-only scale-free scores and paired-origin inference."""

from __future__ import annotations

import math
import random
from statistics import fmean

from forecast_anything.contracts import ForecastResult, Matrix
from forecast_anything.evaluation.metrics import forecast_metrics


def score_origin(
    forecast: ForecastResult,
    *,
    actual: Matrix,
    history: Matrix,
    period: int,
    core_metrics: dict | None = None,
) -> dict:
    """Return MASE, sMAPE and WQL for one aligned forecast window.

    MAE, pinball loss and interval coverage remain owned by the core evaluator.
    ``core_metrics`` may pass its already computed result to avoid recalculating
    pinball loss; it is derived from ``forecast_metrics`` when omitted.
    """
    if type(period) is not int or period < 1:
        raise ValueError("period must be a positive integer")
    if len(actual) != len(forecast.series_ids) or len(history) != len(actual):
        raise ValueError("actual and history must align with forecast series")
    horizon = len(forecast.timestamps)
    if any(len(row) != horizon for row in actual):
        raise ValueError("actual rows must align with forecast horizon")
    if any(len(row) < period + 1 for row in history):
        mase, mase_reason = None, "insufficient_seasonal_history"
    elif forecast.point is None:
        mase, mase_reason = None, "point_unavailable"
    else:
        scaled_errors = []
        undefined_scale = False
        for actual_row, history_row, point_row in zip(
            actual, history, forecast.point, strict=True
        ):
            scale = fmean(
                abs(history_row[i] - history_row[i - period])
                for i in range(period, len(history_row))
            )
            if scale == 0:
                undefined_scale = True
                break
            scaled_errors.extend(
                abs(observed - predicted) / scale
                for observed, predicted in zip(actual_row, point_row, strict=True)
            )
        if undefined_scale:
            mase, mase_reason = None, "zero_seasonal_scale"
        else:
            mase, mase_reason = fmean(scaled_errors), None

    if forecast.point is None:
        smape, smape_reason = None, "point_unavailable"
    else:
        smape_values = [
            0.0
            if observed == 0 and predicted == 0
            else 200.0 * abs(observed - predicted) / (abs(observed) + abs(predicted))
            for actual_row, point_row in zip(actual, forecast.point, strict=True)
            for observed, predicted in zip(actual_row, point_row, strict=True)
        ]
        smape, smape_reason = fmean(smape_values), None

    quantile_scores = core_metrics or forecast_metrics(forecast, actual)
    pinball = quantile_scores.get("pinball", {})
    actual_scale = sum(abs(value) for row in actual for value in row)
    if not forecast.quantiles:
        wql, wql_reason = None, "quantiles_unavailable"
    elif actual_scale == 0:
        wql, wql_reason = None, "zero_actual_scale"
    elif not pinball:
        wql, wql_reason = None, "pinball_unavailable"
    else:
        cell_count = sum(map(len, actual))
        wql = (
            2.0
            * sum(value * cell_count for value in pinball.values())
            / (len(pinball) * actual_scale)
        )
        wql_reason = None

    return {
        "mase": mase,
        "mase_reason": mase_reason,
        "smape": smape,
        "smape_reason": smape_reason,
        "wql": wql,
        "wql_reason": wql_reason,
    }


def _paired_losses(model_losses, baseline_losses):
    model = tuple(float(value) for value in model_losses)
    baseline = tuple(float(value) for value in baseline_losses)
    if len(model) != len(baseline):
        raise ValueError("model and baseline losses must be paired")
    if any(not math.isfinite(value) or value < 0 for value in model + baseline):
        raise ValueError("losses must be finite and non-negative")
    return model, baseline


def _skill(model_losses, baseline_losses):
    baseline_mean = fmean(baseline_losses)
    if baseline_mean == 0:
        return None
    return 1.0 - fmean(model_losses) / baseline_mean


def _percentile(values, probability):
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def bootstrap_skill_interval(
    model_losses,
    baseline_losses,
    *,
    horizon: int,
    stride: int = 1,
    samples: int = 2_000,
    seed: int = 0,
) -> dict:
    """Paired circular moving-block bootstrap for relative MAE skill."""
    model, baseline = _paired_losses(model_losses, baseline_losses)
    if type(horizon) is not int or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    if type(stride) is not int or stride < 1:
        raise ValueError("stride must be a positive integer")
    if type(samples) is not int or samples < 1:
        raise ValueError("samples must be a positive integer")
    estimate = _skill(model, baseline) if model else None
    if not model:
        return {
            "estimate": None,
            "lower": None,
            "upper": None,
            "count": 0,
            "block_size": 0,
            "samples": samples,
            "reason": "no_matched_origins",
        }
    if estimate is None:
        return {
            "estimate": None,
            "lower": None,
            "upper": None,
            "count": len(model),
            "block_size": min(len(model), math.ceil(horizon / stride)),
            "samples": samples,
            "reason": "zero_baseline_mae",
        }

    count = len(model)
    block_size = min(count, math.ceil(horizon / stride))
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        indices = []
        while len(indices) < count:
            start = rng.randrange(count)
            indices.extend((start + offset) % count for offset in range(block_size))
        selected = indices[:count]
        sample_skill = _skill(
            tuple(model[index] for index in selected),
            tuple(baseline[index] for index in selected),
        )
        if sample_skill is not None:
            estimates.append(sample_skill)
    if not estimates:
        lower = upper = None
        reason = "zero_baseline_mae_in_resamples"
    else:
        lower, upper = _percentile(estimates, 0.025), _percentile(estimates, 0.975)
        reason = None
    return {
        "estimate": estimate,
        "lower": lower,
        "upper": upper,
        "count": count,
        "block_size": block_size,
        "samples": samples,
        "reason": reason,
    }


def diebold_mariano(
    model_losses,
    baseline_losses,
    *,
    horizon: int,
    stride: int = 1,
) -> dict:
    """Two-sided Diebold-Mariano test with Newey-West overlap correction."""
    model, baseline = _paired_losses(model_losses, baseline_losses)
    if type(horizon) is not int or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    if type(stride) is not int or stride < 1:
        raise ValueError("stride must be a positive integer")
    count = len(model)
    lag = min(max(0, math.ceil(horizon / stride) - 1), max(0, count - 1))
    if not count:
        return {
            "statistic": None,
            "p_value": None,
            "count": 0,
            "lag": lag,
            "reason": "no_matched_origins",
        }

    differences = tuple(m - b for m, b in zip(model, baseline, strict=True))
    mean_difference = fmean(differences)
    centered = tuple(value - mean_difference for value in differences)
    gamma_zero = sum(value * value for value in centered) / count
    long_run_variance = gamma_zero
    for offset in range(1, lag + 1):
        covariance = (
            sum(
                centered[index] * centered[index - offset]
                for index in range(offset, count)
            )
            / count
        )
        weight = 1.0 - offset / (lag + 1)
        long_run_variance += 2.0 * weight * covariance

    variance_of_mean = long_run_variance / count
    if variance_of_mean <= 0:
        return {
            "statistic": None,
            "p_value": None,
            "count": count,
            "lag": lag,
            "reason": "zero_loss_difference_variance",
        }
    statistic = mean_difference / math.sqrt(variance_of_mean)
    return {
        "statistic": statistic,
        "p_value": math.erfc(abs(statistic) / math.sqrt(2.0)),
        "count": count,
        "lag": lag,
        "reason": None,
    }
