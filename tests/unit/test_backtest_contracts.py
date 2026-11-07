"""Backtest identity and validation boundaries, independent of numerical planning."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from forecast_anything import contracts


def test_forecast_selection_requires_provider_and_strict_bounded_integers():
    assert hasattr(contracts, "ForecastSelection"), (
        "configurable forecasts need a contract"
    )
    selection = contracts.ForecastSelection(provider="seasonal_naive", horizon=1)
    assert selection.options == {}
    assert selection.baseline_period == 1
    for field, values in {
        "horizon": (0, 367, True, "2"),
        "baseline_period": (0, 10001, False),
    }.items():
        for value in values:
            with pytest.raises(ValidationError):
                contracts.ForecastSelection(
                    **{"provider": "seasonal_naive", "horizon": 1, field: value}
                )
    with pytest.raises(ValidationError):
        contracts.ForecastSelection(horizon=1)
    with pytest.raises(ValidationError):
        contracts.ForecastSelection(
            provider="p", horizon=1, options={"bad": float("nan")}
        )


def test_backtest_settings_bounds_and_defaults():
    assert hasattr(contracts, "BacktestSettings"), "backtests need bounded settings"
    assert contracts.BacktestSettings().max_origins_per_partition == 10
    assert contracts.BacktestSettings().origin_offset_seconds == 0
    for values in (
        {"max_origins_per_partition": 0},
        {"max_origins_per_partition": 51},
        {"max_origins_per_partition": True},
        {"origin_offset_seconds": -1},
        {"origin_offset_seconds": 0.5},
    ):
        with pytest.raises(ValidationError):
            contracts.BacktestSettings(**values)


def test_archive_hash_normalizes_utc_order_and_signed_zero():
    from forecast_anything.backtesting.contracts import ObservationArchive
    from forecast_anything.contracts import Observation

    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = Observation(
        series_id="s",
        event_time=instant,
        available_at=instant,
        revision="a",
        value=-0.0,
        unit="count",
    )
    revised = row.model_copy(
        update={
            "revision": "b",
            "available_at": instant + timedelta(days=1),
            "value": 2.0,
        }
    )
    first = ObservationArchive(
        source_id="s",
        source_revision="rev",
        captured_at=instant,
        observations=(row, revised),
    )
    alternate = row.model_copy(
        update={
            "event_time": instant.astimezone(timezone(timedelta(hours=2))),
            "value": 0.0,
        }
    )
    second = ObservationArchive(
        source_id="s",
        source_revision="rev",
        captured_at=instant,
        observations=(revised, alternate),
    )
    assert first.archive_id == second.archive_id
    assert first.model_dump_json() == second.model_dump_json()
    assert len(first.observations) == 2
    assert (
        first.archive_id
        != ObservationArchive(
            source_id="s",
            source_revision="other",
            captured_at=instant,
            observations=(row, revised),
        ).archive_id
    )
    with pytest.raises(ValidationError):
        ObservationArchive.model_validate(
            {**first.model_dump(), "archive_id": "forged"}
        )


def test_partition_score_preserves_denominators_and_explicit_unavailable_ratio():
    from forecast_anything.backtesting.contracts import PartitionScore

    with pytest.raises(ValidationError):
        PartitionScore(partition="final", planned=2, excluded=1)
    with pytest.raises(ValidationError):
        PartitionScore(
            partition="final",
            planned=1,
            evaluated=1,
            matched_count=2,
            model_mae=1,
            baseline_mae=0,
            relative_mae=0.0,
            relative_mae_reason=None,
        )
    score = PartitionScore(
        partition="final",
        planned=1,
        evaluated=1,
        matched_count=2,
        model_mae=1,
        baseline_mae=0,
        relative_mae_reason="zero_baseline_mae",
    )
    assert score.relative_mae is None


def test_archive_limit_and_naive_capture_are_rejected():
    from forecast_anything.backtesting.contracts import ObservationArchive
    from forecast_anything.contracts import Observation

    row = Observation(
        series_id="s",
        event_time="2026-01-01T00:00:00Z",
        available_at="2026-01-01T00:00:00Z",
        revision="r",
        value=1,
        unit="count",
    )
    with pytest.raises(ValidationError):
        ObservationArchive(
            source_id="s",
            source_revision="r",
            captured_at="2026-01-01",
            observations=(row,),
        )
    with pytest.raises(ValidationError):
        ObservationArchive(
            source_id="s",
            source_revision="r",
            captured_at="2026-01-01T00:00:00Z",
            observations=(row,) * 100001,
        )


def test_forecast_options_are_json_values_for_reproducible_identity():
    with pytest.raises(ValidationError):
        contracts.ForecastSelection(provider="p", horizon=1, options={"bad": object()})
