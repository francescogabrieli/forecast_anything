"""Deterministic seasonal repetition with explicit period and no imputation."""
from datetime import timezone

from ..contracts import Capabilities, DomainError, ForecastRequest, ForecastResult
from .base import frequency_step, observation_grid


def _period(value):
    if type(value) is not int or value <= 0:
        raise DomainError("invalid_period", {"period": value})
    return value


class SeasonalNaiveProvider:
    def __init__(self, period: int):
        self.period = _period(period)

    def capabilities(self) -> Capabilities:
        return Capabilities(provider_id="seasonal_naive", provider_revision="1",
                            representations=("point",), supports_known_future=False)

    def forecast(self, request: ForecastRequest) -> ForecastResult:
        request = ForecastRequest.model_validate(request.model_dump())
        if request.known_future is not None:
            raise DomainError("unsupported_known_future", {})
        if set(request.options) - {"period"}:
            raise DomainError("unsupported_options", {"options": sorted(request.options)})
        period = _period(request.options.get("period", self.period))
        groups, calendar = observation_grid(request.snapshot, request.frequency)
        if calendar[-1] > request.snapshot.as_of.astimezone(timezone.utc):
            raise DomainError("future_history", {})
        if len(calendar) < period:
            raise DomainError("insufficient_history", {"required": period, "actual": len(calendar)})
        series_ids = tuple(sorted(groups))
        point = []
        for series_id in series_ids:
            values = [o.value for o in groups[series_id]]
            if any(value is None for value in values):
                raise DomainError("missing_observation", {"series_id": series_id})
            point.append(tuple(values[-period:][i % period] for i in range(request.horizon)))
        capability = self.capabilities()
        step = frequency_step(request.frequency)
        return ForecastResult(provider_id=capability.provider_id,
            provider_revision=capability.provider_revision, series_ids=series_ids,
            timestamps=tuple(calendar[-1]+step*(i+1) for i in range(request.horizon)),
            units=tuple(groups[s][0].unit for s in series_ids), point=tuple(point),
            quantiles=None, paths=None, sample_group_id=None,
            assumptions=(*request.snapshot.assumptions, f"seasonal_naive period={period}; fixed UTC calendar; no imputation"))
