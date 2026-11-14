from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from forecast_anything.contracts import DomainError, ForecastRequest, Observation
from forecast_anything.providers.classical import (
    AutoARIMAProvider,
    ETSProvider,
    ThetaProvider,
)
from forecast_anything.temporal import freeze

ORIGIN = datetime(2026, 11, 1, tzinfo=UTC)


def _request(values, *, horizon=4, known_future=None):
    observations = tuple(
        Observation(
            series_id="series",
            event_time=ORIGIN - timedelta(days=len(values) - index),
            available_at=ORIGIN,
            revision="1",
            value=value,
            unit="count",
        )
        for index, value in enumerate(values)
    )
    return ForecastRequest(
        snapshot=freeze(observations, ORIGIN),
        horizon=horizon,
        frequency="1d",
        known_future=known_future,
    )


@pytest.mark.parametrize(
    "provider_type",
    (ETSProvider, ThetaProvider, AutoARIMAProvider),
)
def test_classical_provider_emits_finite_point_forecast(provider_type):
    provider = provider_type()
    result = provider.forecast(_request(tuple(20 + i * 0.5 for i in range(24))))

    assert result.provider_id == provider.capabilities().provider_id
    assert result.provider_revision == provider.capabilities().provider_revision
    assert result.series_ids == ("series",)
    assert len(result.point[0]) == 4
    assert all(value > 0 for value in result.point[0])
    assert result.quantiles is None and result.paths is None
    assert result.timestamps[0] == ORIGIN


def test_ets_level_forecast_preserves_a_constant_series():
    result = ETSProvider().forecast(_request((7.0,) * 12, horizon=3))
    assert result.point == ((7.0, 7.0, 7.0),)
    assert "ETS(A,N,N)" in result.assumptions[-1]


def test_autoarima_order_search_is_reproducible():
    values = tuple(20 + 0.25 * i + (i % 4) for i in range(36))
    provider = AutoARIMAProvider()
    first = provider.forecast(_request(values))
    second = provider.forecast(_request(values))

    assert first.point == second.point
    assert "AIC" in first.assumptions[-1]
    assert "q0" in first.provider_revision


def test_autoarima_aic_candidates_share_a_common_response_window():
    values = np.asarray(tuple(10 + i * 0.2 + (i % 3) for i in range(30)))
    candidate_counts = []
    for difference_order in (0, 1):
        transformed = np.diff(values, n=difference_order)
        response_start = 4 - difference_order
        candidate_counts.append(
            [
                AutoARIMAProvider._fit_ar(transformed, order, response_start)[2]
                for order in range(4)
            ]
        )

    assert candidate_counts == [[26] * 4, [26] * 4]


@pytest.mark.parametrize(
    "provider_type", (ETSProvider, ThetaProvider, AutoARIMAProvider)
)
def test_classical_providers_reject_missing_history(provider_type):
    with pytest.raises(DomainError, match="missing_observation"):
        provider_type().forecast(_request((1.0, None, 3.0)))
