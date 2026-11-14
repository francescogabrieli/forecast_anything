"""Small, deterministic CPU reference forecasters for benchmark comparison.

The implementations intentionally use NumPy only and expose their restricted
specifications in provider revisions: ETS(A,N,N), the nonseasonal Theta method,
and AIC-selected ARIMA(p,d,0) with p <= 3 and d in {0, 1}.
"""

from datetime import UTC

import numpy as np

from ..contracts import Capabilities, DomainError, ForecastRequest, ForecastResult
from .base import frequency_step, observation_grid


def _ses_level(values: np.ndarray) -> float:
    """Fit simple exponential smoothing by one-step SSE over a fixed alpha grid."""
    best_error = float("inf")
    best_level = float(values[-1])
    for alpha in np.linspace(0.05, 0.95, 19):
        level = float(values[0])
        error = 0.0
        for value in values[1:]:
            residual = float(value) - level
            error += residual * residual
            level += float(alpha) * residual
        if error < best_error:
            best_error, best_level = error, level
    return best_level


class _ClassicalProvider:
    provider_id = "classical"
    provider_revision = "classical-v1"
    min_history = 2
    assumption: str

    def capabilities(self) -> Capabilities:
        return Capabilities(
            provider_id=self.provider_id,
            provider_revision=self.provider_revision,
            representations=("point",),
            supports_known_future=False,
        )

    def _forecast(self, values: np.ndarray, horizon: int) -> np.ndarray:
        raise NotImplementedError

    def forecast(self, request: ForecastRequest) -> ForecastResult:
        request = ForecastRequest.model_validate(request.model_dump())
        if request.known_future is not None:
            raise DomainError("unsupported_known_future", {})
        if request.options:
            raise DomainError(
                "unsupported_options", {"options": sorted(request.options)}
            )
        groups, calendar = observation_grid(request.snapshot, request.frequency)
        if calendar[-1] > request.snapshot.as_of.astimezone(UTC):
            raise DomainError("future_history", {})
        series_ids = tuple(sorted(groups))
        forecasts = []
        for series_id in series_ids:
            raw_values = [observation.value for observation in groups[series_id]]
            if any(value is None for value in raw_values):
                raise DomainError("missing_observation", {"series_id": series_id})
            values = np.asarray(raw_values, dtype=np.float64)
            if len(values) < self.min_history:
                raise DomainError(
                    "insufficient_history",
                    {"required": self.min_history, "actual": len(values)},
                )
            if not np.isfinite(values).all():
                raise DomainError("invalid_model_output", {})
            point = np.asarray(
                self._forecast(values, request.horizon), dtype=np.float64
            )
            if point.shape != (request.horizon,) or not np.isfinite(point).all():
                raise DomainError("invalid_model_output", {})
            forecasts.append(tuple(float(value) for value in point))

        capability = self.capabilities()
        step = frequency_step(request.frequency)
        return ForecastResult(
            provider_id=capability.provider_id,
            provider_revision=capability.provider_revision,
            series_ids=series_ids,
            timestamps=tuple(
                calendar[-1] + step * (index + 1) for index in range(request.horizon)
            ),
            units=tuple(groups[series_id][0].unit for series_id in series_ids),
            point=tuple(forecasts),
            quantiles=None,
            paths=None,
            sample_group_id=None,
            assumptions=(*request.snapshot.assumptions, self.assumption),
        )


class ETSProvider(_ClassicalProvider):
    """Additive-error, no-trend, no-seasonality ETS (simple exponential smoothing)."""

    provider_id = "ets"
    provider_revision = "ets-a-n-n-ses-grid-v1"
    assumption = "ETS(A,N,N); alpha selected by one-step SSE on a fixed grid"

    def _forecast(self, values: np.ndarray, horizon: int) -> np.ndarray:
        return np.full(horizon, _ses_level(values), dtype=np.float64)


class ThetaProvider(_ClassicalProvider):
    """Nonseasonal Theta method using an SSE-fitted SES level and linear trend."""

    provider_id = "theta"
    provider_revision = "theta-nonseasonal-ses-drift-v1"
    assumption = (
        "Theta method; mean of fitted trend and SES forecast of the theta=2 line"
    )

    def _forecast(self, values: np.ndarray, horizon: int) -> np.ndarray:
        indexes = np.arange(len(values), dtype=np.float64)
        centered_indexes = indexes - indexes.mean()
        denominator = float(np.dot(centered_indexes, centered_indexes))
        slope = float(np.dot(centered_indexes, values - values.mean()) / denominator)
        intercept = float(values.mean() - slope * indexes.mean())
        fitted_trend = intercept + slope * indexes
        future_indexes = np.arange(len(values), len(values) + horizon, dtype=np.float64)
        trend = intercept + slope * future_indexes
        theta_two = 2 * values - fitted_trend
        return 0.5 * _ses_level(theta_two) + 0.5 * trend


class AutoARIMAProvider(_ClassicalProvider):
    """AIC search over conditional ARIMA(p,d,0), p=0..3 and d=0..1."""

    provider_id = "autoarima"
    provider_revision = "autoarima-css-aic-p0-3-d0-1-q0-v1"
    assumption = "AutoARIMA CSS/AIC search over p=0..3,d=0..1 with q fixed at 0"
    min_history = 8

    @staticmethod
    def _fit_ar(values: np.ndarray, order: int, response_start: int):
        target = values[response_start:]
        if order:
            rows = [
                values[index - order : index][::-1]
                for index in range(response_start, len(values))
            ]
            design = np.column_stack((np.ones(len(target)), np.asarray(rows)))
        else:
            design = np.ones((len(target), 1), dtype=np.float64)
        coefficients = np.linalg.lstsq(design, target, rcond=None)[0]
        residuals = target - design @ coefficients
        variance = max(float(np.mean(residuals * residuals)), np.finfo(float).tiny)
        parameter_count = len(coefficients) + 1
        aic = len(target) * np.log(variance) + 2 * parameter_count
        return float(aic), coefficients, len(target)

    def _forecast(self, values: np.ndarray, horizon: int) -> np.ndarray:
        values = values[-512:]
        best = None
        common_original_start = 4
        for difference_order in (0, 1):
            transformed = np.diff(values, n=difference_order)
            response_start = common_original_start - difference_order
            for autoregressive_order in range(4):
                if len(transformed) <= response_start + 2:
                    continue
                aic, coefficients, _ = self._fit_ar(
                    transformed, autoregressive_order, response_start
                )
                if best is None or aic < best[0]:
                    best = (aic, autoregressive_order, difference_order, coefficients)
        if best is None:
            raise DomainError("insufficient_history", {"required": self.min_history})

        _, autoregressive_order, difference_order, coefficients = best
        state = list(float(value) for value in np.diff(values, n=difference_order))
        forecasts = []
        for _ in range(horizon):
            prediction = float(coefficients[0])
            for lag in range(autoregressive_order):
                prediction += float(coefficients[lag + 1]) * state[-lag - 1]
            state.append(prediction)
            forecasts.append(prediction)

        if difference_order:
            level = float(values[-1])
            for index, increment in enumerate(forecasts):
                level += increment
                forecasts[index] = level
        return np.asarray(forecasts, dtype=np.float64)
