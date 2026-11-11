"""Frozen calendar and trusted graph boundaries, with literal target membership."""

from datetime import UTC, datetime, timedelta

import pytest
from backtest_fixtures import START, prepare, revision, rows

from forecast_anything.contracts import (
    BacktestSettings,
    DomainError,
    ForecastSelection,
)
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.temporal import freeze


def test_plan_preserves_missing_cell_and_earliest_nonoverlapping_partition_membership():
    plan = prepare(
        tuple(r for i, r in enumerate(rows()) if i != 3),
        settings=BacktestSettings(max_origins_per_partition=2),
    )
    assert plan.calendar == tuple(START + timedelta(days=i) for i in range(16))
    assert [
        (
            o.partition,
            (o.nominal_origin - START).days,
            (o.target_start - START).days,
            (o.target_end - START).days,
        )
        for o in plan.origins
    ] == [
        ("exploration", 0, 1, 2),
        ("exploration", 2, 3, 4),
        ("selection", 7, 8, 9),
        ("selection", 9, 10, 11),
        ("final", 11, 12, 13),
        ("final", 13, 14, 15),
    ]


def test_requalification_plan_keeps_final_targets_strictly_after_qualification_floor():
    floor = START + timedelta(days=12)
    plan = prepare(
        tuple(
            r.model_copy(update={"event_time": START + timedelta(days=i)})
            for i, r in enumerate(rows(40))
        ),
        captured_at=START + timedelta(days=39),
        origin_target_after=floor,
    )

    final = [origin for origin in plan.origins if origin.partition == "final"]
    assert plan.origin_target_after == floor
    assert final
    assert all(origin.target_start > floor for origin in final)


def test_known_future_and_unavailable_rows_do_not_change_bounds_or_metadata():
    foreign = rows()[0].model_copy(
        update={
            "series_id": "future",
            "unit": "USD",
            "event_time": START + timedelta(days=100),
        }
    )
    unavailable = foreign.model_copy(
        update={
            "event_time": START - timedelta(days=10),
            "available_at": START + timedelta(days=100),
        }
    )
    plan = prepare((*rows(), foreign, unavailable))
    assert len(plan.archive.observations) == 18
    assert plan.calendar[0] == START
    assert plan.calendar[-1] == START + timedelta(days=15)
    from forecast_anything.backtesting.planning import actuals_from_archive

    actuals = actuals_from_archive(plan.archive)
    assert actuals.snapshot_id == plan.actuals_snapshot_id
    assert len(actuals.observations) == 16
    assert actuals.assumptions[0] == "source_revision=revision-1"


def test_planning_detaches_options_contracts_and_raw_rows():
    selection = ForecastSelection(
        provider="seasonal_naive", horizon=2, options={"nested": {"values": [1]}}
    )
    caps = SeasonalNaiveProvider(1).capabilities()
    original = rows()
    plan = prepare(original, selection=selection, contracts={"seasonal_naive": caps})
    selection.options["nested"]["values"].append(2)
    caps.provider_revision = "changed"
    original[0].value = 999
    assert plan.selection.options == {"nested": {"values": [1]}}
    assert plan.provider_contracts["seasonal_naive"].provider_revision == "1"
    assert (
        next(o for o in plan.archive.observations if o.event_time == START).value == 1
    )


@pytest.mark.parametrize(
    "change,code",
    [
        ("offgrid", "off_grid_observation"),
        ("series", "unsupported_source_metadata"),
        ("unit", "unsupported_source_metadata"),
        ("assumed", "assumed_backtest_input"),
        ("offset", "invalid_origin_offset"),
        ("huge_offset", "invalid_origin_offset"),
        ("huge_gap", "backtest_calendar_limit"),
        ("frequency", "unsupported_frequency"),
        ("integer_limit_frequency", "unsupported_frequency"),
    ],
)
def test_rejects_unsupported_or_unbounded_inputs(change, code):
    data, source, settings = rows(), revision(), BacktestSettings()
    if change == "offgrid":
        data = (
            *data,
            data[0].model_copy(update={"event_time": START + timedelta(hours=12)}),
        )
    elif change in {"series", "unit"}:
        data = (
            *data,
            data[0].model_copy(
                update={
                    "series_id" if change == "series" else "unit": "other",
                    "revision": "b",
                }
            ),
        )
    elif change == "assumed":
        source = revision(assumptions=("assumed:scenario",))
    elif change in {"offset", "huge_offset"}:
        settings = BacktestSettings(
            origin_offset_seconds=86400 if change == "offset" else 10**100
        )
    elif change == "huge_gap":
        data = (
            data[0],
            data[-1].model_copy(
                update={
                    "event_time": START + timedelta(days=100000),
                    "available_at": START,
                }
            ),
        )
    elif change in {"frequency", "integer_limit_frequency"}:
        source = revision("9" * (100 if change == "frequency" else 5000) + "d")
    capture = datetime(2500, 1, 1, tzinfo=UTC) if change == "huge_gap" else None
    with pytest.raises(DomainError) as error:
        prepare(data, source=source, settings=settings, captured_at=capture)
    assert error.value.code == code


def test_graph_has_explicit_comparator_and_selected_options():
    from forecast_anything.backtesting.planning import build_forecast_graph

    graph = build_forecast_graph(
        "sales",
        freeze(rows(4), START + timedelta(days=3)),
        ForecastSelection(
            provider="seasonal_naive",
            horizon=3,
            options={"period": 2},
            baseline_period=1,
        ),
        "1d",
        graph_id="configured",
    )
    source, baseline, model = graph.nodes
    assert (source.node_id, baseline.node_id, model.node_id) == (
        "source",
        "baseline",
        "model",
    )
    assert source.config == {
        "source_id": "sales",
        "series_ids": ("sales",),
        "units": ("count",),
        "frequency": "1d",
    }
    assert baseline.config["options"] == {"period": 1}
    assert model.config["options"] == {"period": 2}
    assert model.config["horizon"] == baseline.config["horizon"] == 3
