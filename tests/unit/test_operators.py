from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from forecast_anything.contracts import (
    Capabilities,
    DomainError,
    ForecastResult,
    GraphSpec,
    Node,
    OperatorContract,
)
from forecast_anything.graph import compile_graph

T = datetime(2026, 10, 24, tzinfo=UTC)


def registry():
    from forecast_anything.operators import register_builtin_operators

    return register_builtin_operators()


def result(point=((1, 1),), paths=None, group="world", **changes):
    return ForecastResult.model_validate(
        dict(
            provider_id="fixture",
            provider_revision="1",
            series_ids=("s",),
            timestamps=(T, T + timedelta(hours=1)),
            units=("count",),
            point=point,
            quantiles=None,
            paths=paths,
            sample_group_id=group if paths is not None else None,
            assumptions=("fixture assumption",),
        )
        | changes
    )


def test_anytime_uses_complete_paths():
    value = result(paths=(((2, 0),), ((0, 2),)))
    answer = registry()["any_exceed"].apply(
        {"value": value}, {"threshold": 1, "comparator": "gt"}
    )
    assert answer.point == ((1.0,),)
    assert answer.units == ("probability",)
    assert answer.timestamps == (T + timedelta(hours=1),)
    assert answer.series_ids == ("event:any_exceed",)
    assert (
        answer.paths is None
        and answer.quantiles is None
        and answer.sample_group_id is None
    )
    assert "fixture assumption" in answer.assumptions
    assert any("gt" in a and "1.0" in a for a in answer.assumptions)
    assert any(
        T.isoformat() in a and (T + timedelta(hours=1)).isoformat() in a
        for a in answer.assumptions
    )


@pytest.mark.parametrize(
    "comparator, threshold, expected",
    [("gt", 2, 0), ("lt", 1, 1), ("lt", 0, 0), ("gt", 0, 1)],
)
def test_event_strict_comparators(comparator, threshold, expected):
    answer = registry()["any_exceed"].apply(
        {"value": result(paths=(((2, 0),), ((0, 2),)))},
        {"threshold": threshold, "comparator": comparator},
    )
    assert answer.point == ((expected,),)


def test_event_probability_is_sample_frequency():
    value = result(point=None, paths=(((2, 0),), ((0, 0),), ((0, 0),), ((0, 2),)))
    assert registry()["any_exceed"].apply(
        {"value": value}, {"threshold": 1, "comparator": "gt"}
    ).point == ((0.5,),)


def test_sum_preserves_point_and_paths_without_summing_quantiles():
    left = result(point=((2, 3),), paths=(((1, 2),), ((3, 4),)))
    right = result(point=((5, 7),), paths=(((4, 6),), ((6, 8),)))
    answer = registry()["sum_aligned"].apply({"a": left, "b": right}, {})
    assert answer.point == ((7, 10),)
    assert answer.paths == (((5, 8),), ((9, 12),))
    assert answer.sample_group_id == "world"
    assert answer.quantiles is None
    assert answer.timestamps == left.timestamps


def test_quantiles_cannot_be_summed_probabilistically():
    value = result(point=None, quantiles={"0.5": ((1, 1),)})
    with pytest.raises(DomainError, match="unsupported_representation"):
        registry()["sum_aligned"].apply({"a": value}, {})
    with pytest.raises(DomainError, match="unsupported_representation"):
        registry()["any_exceed"].apply(
            {"value": value}, {"threshold": 1, "comparator": "gt"}
        )


@pytest.mark.parametrize("difference", ["group", "count"])
def test_independent_sample_groups(difference):
    left = result(paths=(((2, 0),), ((0, 2),)))
    right = result(
        paths=(((2, 0),),) if difference == "count" else left.paths,
        group="other" if difference == "group" else "world",
    )
    with pytest.raises(DomainError, match="incompatible_samples"):
        registry()["sum_aligned"].apply({"a": left, "b": right}, {})


@pytest.mark.parametrize("paths_only", [False, True])
def test_balance_point_and_paths(paths_only):
    inflow = result(
        point=None if paths_only else ((0, 5),), paths=(((0, 5),), ((2, 2),))
    )
    outflow = result(
        point=None if paths_only else ((3, 4),), paths=(((3, 4),), ((1, 4),))
    )
    answer = registry()["cumulative_balance"].apply(
        {"inflow": inflow, "outflow": outflow}, {"initial_value": 10, "unit": "count"}
    )
    assert answer.point == (None if paths_only else ((7, 8),))
    assert answer.paths == (((7, 8),), ((11, 9),))
    assert answer.sample_group_id == "world"


@pytest.mark.parametrize(
    "operator, inputs, config, code",
    [
        ("sum_aligned", {}, {}, "invalid_binding"),
        (
            "any_exceed",
            {"wrong": result()},
            {"threshold": 1, "comparator": "gt"},
            "invalid_binding",
        ),
        (
            "any_exceed",
            {"value": result()},
            {"threshold": 1, "comparator": "gt"},
            "unsupported_representation",
        ),
        (
            "any_exceed",
            {"value": result(paths=(((1, 1),),))},
            {"threshold": float("inf"), "comparator": "gt"},
            "invalid_config",
        ),
        (
            "any_exceed",
            {"value": result(paths=(((1, 1),),))},
            {"threshold": 1, "comparator": "gte"},
            "invalid_config",
        ),
        (
            "cumulative_balance",
            {"inflow": result(), "outflow": result()},
            {"initial_value": 10, "unit": "USD"},
            "incompatible_units",
        ),
    ],
)
def test_operator_boundaries(operator, inputs, config, code):
    with pytest.raises(DomainError, match=code):
        registry()[operator].apply(inputs, config)


@pytest.mark.parametrize(
    "change,code",
    [
        ({"timestamps": (T, T + timedelta(hours=2))}, "incompatible_calendar"),
        ({"units": ("USD",)}, "incompatible_units"),
        ({"series_ids": ("other",)}, "incompatible_series"),
    ],
)
def test_no_implicit_alignment_or_conversion(change, code):
    with pytest.raises(DomainError, match=code):
        registry()["sum_aligned"].apply(
            {"a": result(), "b": result().model_copy(update=change)}, {}
        )


def spec_for_chain():
    return GraphSpec(
        graph_id="g",
        version=1,
        nodes=(
            Node(
                node_id="s",
                kind="source",
                inputs=(),
                config={
                    "source_id": "s",
                    "series_ids": ["s"],
                    "units": ["count"],
                    "frequency": "1h",
                },
            ),
            Node(
                node_id="f",
                kind="forecast",
                inputs=("s",),
                config={
                    "provider": "p",
                    "history": "s",
                    "horizon": 2,
                    "frequency": "1h",
                    "relation_type": {"s": "statistical"},
                },
            ),
            Node(
                node_id="sum",
                kind="transform",
                inputs=("f",),
                config={
                    "operator": "sum_aligned",
                    "relation_type": {"f": "accounting"},
                },
            ),
            Node(
                node_id="event",
                kind="event",
                inputs=("sum",),
                config={
                    "operator": "any_exceed",
                    "relation_type": {"sum": "statistical"},
                    "parameters": {
                        "bindings": {"value": "sum"},
                        "threshold": 1,
                        "comparator": "gt",
                    },
                },
            ),
        ),
    )


@pytest.mark.parametrize(
    "representations, succeeds",
    [
        (("point", "joint_paths"), True),
        (("paths",), True),
        (("point",), False),
        (("quantiles",), False),
    ],
)
def test_graph_negotiates_only_guaranteed_representations(representations, succeeds):
    capabilities = {
        "p": Capabilities(
            provider_id="p",
            provider_revision="1",
            representations=representations,
            supports_known_future=False,
        )
    }
    contracts = {name: op.contract() for name, op in registry().items()}
    if succeeds:
        assert compile_graph(spec_for_chain(), capabilities, contracts).order == (
            "s",
            "f",
            "sum",
            "event",
        )
    else:
        with pytest.raises(DomainError, match="unsupported_representation"):
            compile_graph(spec_for_chain(), capabilities, contracts)


def test_extended_contract_validates_required_fallback():
    with pytest.raises(ValidationError):
        OperatorContract(
            name="bad",
            required_representation="point",
            accepted_representations=("joint_paths",),
            output_representation="preserve",
            units_rule="same",
        )


def test_event_calendar_is_scalar_at_window_end_in_compiler():
    spec = spec_for_chain()
    first_event = spec.nodes[-1]
    second_event = first_event.model_copy(deep=True)
    second_event.node_id = "event2"
    second_event.inputs = ("f",)
    second_event.config["relation_type"] = {"f": "statistical"}
    second_event.config["parameters"]["bindings"] = {"value": "f"}
    combined = Node(
        node_id="probabilities",
        kind="transform",
        inputs=("event", "event2"),
        config={
            "operator": "sum_aligned",
            "relation_type": {"event": "accounting", "event2": "accounting"},
        },
    )
    capabilities = {
        "p": Capabilities(
            provider_id="p",
            provider_revision="1",
            representations=("joint_paths",),
            supports_known_future=False,
        )
    }
    contracts = {name: op.contract() for name, op in registry().items()}
    # Both scalar probabilities cover the same window, so the sum is well typed.
    assert (
        compile_graph(
            spec.model_copy(update={"nodes": (*spec.nodes, second_event, combined)}),
            capabilities,
            contracts,
        ).order[-1]
        == "probabilities"
    )
    # A full probability-valued forecast is not the scalar end-window calendar.
    direct = Node(
        node_id="full",
        kind="transform",
        inputs=("f",),
        config={"operator": "probability_grid", "relation_type": {"f": "statistical"}},
    )
    contracts["probability_grid"] = OperatorContract(
        name="probability_grid",
        required_representation="joint_paths",
        units_rule="probability",
        output_representation="point",
    )
    combined.inputs = ("event", "full")
    combined.config["relation_type"] = {"event": "accounting", "full": "accounting"}
    with pytest.raises(DomainError, match="incompatible_calendar"):
        compile_graph(
            spec.model_copy(update={"nodes": (*spec.nodes, direct, combined)}),
            capabilities,
            contracts,
        )
