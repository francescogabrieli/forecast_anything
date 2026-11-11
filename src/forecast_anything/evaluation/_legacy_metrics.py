"""Original v1 scoring, retained for verification and recovery of stored work."""

import itertools
from fractions import Fraction
from math import isfinite

from ..contracts import DomainError, ForecastResult, Matrix


def _mean(values, exact_values, count):
    # Preserve established float scores/record identities on the ordinary path.
    # Exact arithmetic is only needed when an intermediate sum/difference fails.
    score = sum(values) / count
    if isfinite(score):
        return score
    try:
        return float(sum(exact_values(), Fraction()) / count)
    except OverflowError:
        raise DomainError("numerical_score_unrepresentable", {}) from None


def forecast_metrics(forecast: ForecastResult, observed: Matrix) -> dict:
    actual = [x for row in observed for x in row]
    scores = {"count": len(actual), "mae": None, "pinball": {}, "intervals": {}}
    if forecast.point is not None:
        points = [x for row in forecast.point for x in row]
        scores["mae"] = _mean(
            (abs(y - p) for y, p in zip(actual, points, strict=False)),
            lambda: (
                abs(Fraction(y) - Fraction(p))
                for y, p in zip(actual, points, strict=False)
            ),
            len(actual),
        )
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
        scores["pinball"][label] = _mean(
            (
                max(level * (y - p), (level - 1) * (y - p))
                for y, p in zip(actual, values, strict=False)
            ),
            lambda level=level, values=values: (
                max(
                    Fraction(level) * (Fraction(y) - Fraction(p)),
                    Fraction(level - 1) * (Fraction(y) - Fraction(p)),
                )
                for y, p in zip(actual, values, strict=False)
            ),
            len(actual),
        )
        levels.append((level, label, values))
    levels.sort()
    for low, high in itertools.pairwise(levels):
        if any(a > b for a, b in zip(low[2], high[2], strict=False)):
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
                "coverage": sum(
                    a <= y <= b for y, a, b in zip(actual, lower, values, strict=False)
                )
                / len(actual),
                "width": _mean(
                    (b - a for a, b in zip(lower, values, strict=False)),
                    lambda lower=lower, values=values: (
                        Fraction(b) - Fraction(a)
                        for a, b in zip(lower, values, strict=False)
                    ),
                    len(actual),
                ),
                "level": high - low,
            }
    return scores
