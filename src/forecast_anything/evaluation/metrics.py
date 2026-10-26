"""Numerical scores for already aligned complete observed target matrices."""

from math import isfinite

from ..contracts import DomainError, ForecastResult, Matrix


def forecast_metrics(forecast: ForecastResult, observed: Matrix) -> dict:
    actual = [x for row in observed for x in row]
    scores = {"count": len(actual), "mae": None, "pinball": {}, "intervals": {}}
    if forecast.point is not None:
        scores["mae"] = sum(
            abs(y - p)
            for y, p in zip(actual, (x for row in forecast.point for x in row))
        ) / len(actual)
    levels = []
    for label, matrix in (forecast.quantiles or {}).items():
        try:
            level = float(label)
        except ValueError as error:
            raise DomainError("invalid_quantiles", {"level": label}) from error
        if (
            not isfinite(level)
            or not 0 < level < 1
            or any(q == level for q, _, _ in levels)
        ):
            raise DomainError("invalid_quantiles", {"level": label})
        values = [x for row in matrix for x in row]
        scores["pinball"][label] = sum(
            max(level * (y - p), (level - 1) * (y - p)) for y, p in zip(actual, values)
        ) / len(actual)
        levels.append((level, label, values))
    levels.sort()
    for low, high in zip(levels, levels[1:]):
        if any(a > b for a, b in zip(low[2], high[2])):
            raise DomainError("invalid_quantiles", {"reason": "crossing quantiles"})
    for low, label, lower in levels:
        if low >= 0.5:
            continue
        upper = next(
            (
                (high, name, values)
                for high, name, values in levels
                if abs(high - (1 - low)) < 1e-12
            ),
            None,
        )
        if upper is not None:
            high, name, values = upper
            scores["intervals"][f"{label}:{name}"] = {
                "coverage": sum(a <= y <= b for y, a, b in zip(actual, lower, values))
                / len(actual),
                "width": sum(b - a for a, b in zip(lower, values)) / len(actual),
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
    return model / baseline, None


def event_metrics(probability: float, observed: float) -> dict:
    if not 0 <= probability <= 1 or observed not in (0, 1):
        raise DomainError("invalid_event_outcome", {})
    return {
        "brier": (probability - observed) ** 2,
        "count": 1,
        "observed_outcome": observed,
    }
