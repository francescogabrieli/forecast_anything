from datetime import datetime, timedelta, timezone

import pytest

from forecast_anything.contracts import DomainError, ForecastRequest, Observation
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.temporal import freeze

T = datetime(2026, 10, 24, tzinfo=timezone.utc)


def history(values=(10, 20, 10, 20)):
    return freeze(
        tuple(
            Observation(
                series_id="s",
                event_time=T - timedelta(hours=len(values) - i),
                available_at=T,
                revision="1",
                value=v,
                unit="count",
            )
            for i, v in enumerate(values)
        ),
        T,
    )


def test_seasonal_repetition():
    result = SeasonalNaiveProvider(period=2).forecast(
        ForecastRequest(
            snapshot=history(), horizon=3, frequency="1h", known_future=None
        )
    )
    assert list(result.point[0]) == [10, 20, 10]
    assert result.timestamps == (T, T + timedelta(hours=1), T + timedelta(hours=2))
    assert result.provider_id == "seasonal_naive"
    assert result.quantiles is None and result.paths is None


def test_short_history_is_explicit():
    with pytest.raises(DomainError, match="insufficient_history"):
        SeasonalNaiveProvider(period=3).forecast(
            ForecastRequest(
                snapshot=history((1, 2)), horizon=3, frequency="1h", known_future=None
            )
        )


@pytest.mark.parametrize("period", [0, -1, True, 1.5])
def test_invalid_period(period):
    with pytest.raises(DomainError, match="invalid_period"):
        SeasonalNaiveProvider(period=period)


def test_explicit_options_control_period_and_reject_unknown_options():
    request = ForecastRequest(
        snapshot=history((1, 2, 3, 4)),
        horizon=3,
        frequency="1h",
        known_future=None,
        options={"period": 2},
    )
    assert SeasonalNaiveProvider(period=1).forecast(request).point == ((3, 4, 3),)
    with pytest.raises(DomainError, match="unsupported_options"):
        SeasonalNaiveProvider(1).forecast(
            request.model_copy(update={"options": {"typo": 2}})
        )


@pytest.mark.parametrize("values", [(1, None), ()])
def test_unusable_history_is_rejected(values):
    with pytest.raises(DomainError):
        SeasonalNaiveProvider(1).forecast(
            ForecastRequest(
                snapshot=history(values), horizon=2, frequency="1h", known_future=None
            )
        )


def test_multiple_series_share_fixed_utc_calendar_across_dst():
    from zoneinfo import ZoneInfo

    start = datetime(2026, 10, 25, 0, tzinfo=timezone.utc)
    observations = tuple(
        Observation(
            series_id=s,
            event_time=(start + timedelta(hours=i)).astimezone(ZoneInfo("Europe/Rome")),
            available_at=start + timedelta(hours=3),
            revision="1",
            value=v,
            unit=unit,
        )
        for s, unit, numbers in (("a", "count", (10, 20)), ("b", "kWh", (30, 40)))
        for i, v in enumerate(numbers)
    )
    result = SeasonalNaiveProvider(2).forecast(
        ForecastRequest(
            snapshot=freeze(observations, start + timedelta(hours=3)),
            horizon=3,
            frequency="1h",
            known_future=None,
        )
    )
    assert result.point == ((10, 20, 10), (30, 40, 30))
    assert result.units == ("count", "kWh")
    assert result.timestamps == (
        start + timedelta(hours=2),
        start + timedelta(hours=3),
        start + timedelta(hours=4),
    )
    assert "period=2" in result.assumptions[-1]


def test_availability_uses_absolute_time_during_repeated_dst_hour():
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Rome")
    origin = datetime(2026, 10, 25, 2, 30, tzinfo=zone, fold=0)
    data = history((1,))
    data.as_of = origin
    data.observations[0].event_time = datetime(2026, 10, 24, 23, tzinfo=timezone.utc)
    data.observations[0].available_at = datetime(2026, 10, 25, 2, tzinfo=zone, fold=1)
    with pytest.raises(DomainError, match="unavailable_observation"):
        SeasonalNaiveProvider(1).forecast(
            ForecastRequest(snapshot=data, horizon=1, frequency="1h", known_future=None)
        )
