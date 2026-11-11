"""Vectorized scores for aligned, complete observed target matrices."""

import itertools
from math import isfinite

import numpy as np

from ..contracts import DomainError, ForecastResult, Matrix

LEGACY_SCORING = "v1"
CURRENT_SCORING = "v2"


def scoring_version_from_assumptions(assumptions: tuple[str, ...]) -> str:
    if assumptions and assumptions[0].split(";", 1)[0] == "evaluation=v2":
        return CURRENT_SCORING
    return LEGACY_SCORING


def _matrix(values: Matrix, field: str, shape: tuple[int, int]) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float64)
    except (ValueError, TypeError, OverflowError):
        raise DomainError("invalid_score_input", {"field": field}) from None
    if array.shape != shape or not array.size or not np.isfinite(array).all():
        raise DomainError("invalid_score_input", {"field": field})
    return array


def _mean_error(actual: np.ndarray, predicted: np.ndarray, level=None) -> float:
    with np.errstate(over="ignore", under="ignore"):
        delta = actual - predicted
        scaled = not np.isfinite(delta).all()
        if scaled:
            # Halve before subtracting when a finite pair would overflow.
            delta = actual * 0.5 - predicted * 0.5
        losses = (
            np.abs(delta)
            if level is None
            else np.abs(delta) * np.where(delta >= 0, level, 1 - level)
        )
        score = np.mean(losses)
        if not np.isfinite(score):
            # A nonnegative mean cannot exceed its largest input.
            peak = np.max(losses)
            score = np.mean(losses / peak) * peak
        if scaled:
            score *= 2
    if not np.isfinite(score):
        raise DomainError("numerical_score_unrepresentable", {})
    return float(score)


def forecast_metrics(forecast: ForecastResult, observed: Matrix) -> dict:
    shape = (len(forecast.series_ids), len(forecast.timestamps))
    actual = _matrix(observed, "observed", shape)
    points = None if forecast.point is None else _matrix(forecast.point, "point", shape)
    levels = {}
    for label, matrix in (forecast.quantiles or {}).items():
        try:
            level = float(label)
        except ValueError as error:
            raise DomainError("invalid_quantiles", {"level": label}) from error
        if not 0 < level < 1 or level in levels:
            raise DomainError("invalid_quantiles", {"level": label})
        levels[level] = (label, _matrix(matrix, f"quantiles.{label}", shape))

    ordered = sorted(levels)
    for low, high in itertools.pairwise(ordered):
        if np.any(levels[low][1] > levels[high][1]):
            raise DomainError("invalid_quantiles", {"reason": "crossing quantiles"})
    scores = {
        "count": actual.size,
        "mae": None if points is None else _mean_error(actual, points),
        "pinball": {
            label: _mean_error(actual, values, level)
            for level, (label, values) in levels.items()
        },
        "intervals": {},
    }
    for low in ordered:
        if low >= 0.5:
            break
        high = next((q for q in ordered if abs(q - (1 - low)) < 1e-12), None)
        if high is None:
            continue
        low_label, lower = levels[low]
        high_label, upper = levels[high]
        scores["intervals"][f"{low_label}:{high_label}"] = {
            "coverage": float(np.mean((lower <= actual) & (actual <= upper))),
            "width": _mean_error(upper, lower),
            "level": high - low,
        }
    return scores


def relative_mae(
    model: float | None, baseline: float | None
) -> tuple[float | None, str | None]:
    if model is None:
        return None, "point_unavailable"
    if baseline is None:
        return None, "unmatched_baseline"
    if baseline == 0:
        return None, "zero_baseline_mae"
    ratio = model / baseline
    return (ratio, None) if isfinite(ratio) else (None, "ratio_unrepresentable")


def event_metrics(probability: float, observed: float) -> dict:
    if not 0 <= probability <= 1 or observed not in (0, 1):
        raise DomainError("invalid_event_outcome", {})
    return {
        "brier": (probability - observed) ** 2,
        "count": 1,
        "observed_outcome": observed,
    }
