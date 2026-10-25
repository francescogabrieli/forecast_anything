import pytest

from forecast_anything.contracts import (
    Capabilities,
    DomainError,
    GraphSpec,
    Node,
    OperatorContract,
)
from forecast_anything.graph import affected_nodes, compile_graph


def source(name="s", unit="kWh", frequency="1h"):
    return Node(
        node_id=name,
        kind="source",
        inputs=(),
        config={
            "source_id": name,
            "series_ids": [name],
            "units": [unit],
            "frequency": frequency,
        },
    )


def forecast(name="f", history="s", **config):
    bindings = (history,) + (
        (config["known_future"],) if config.get("known_future") else ()
    )
    return Node(
        node_id=name,
        kind="forecast",
        inputs=bindings,
        config={
            "provider": "p",
            "history": history,
            "horizon": 3,
            "frequency": "1h",
            "relation_type": dict.fromkeys(bindings, "statistical"),
            **config,
        },
    )


def operation(inputs=("f",), kind="transform", **config):
    return Node(
        node_id="op",
        kind=kind,
        inputs=inputs,
        config={
            "operator": "sum",
            "relation_type": dict.fromkeys(inputs, "statistical"),
            **config,
        },
    )


def compile_nodes(
    *nodes,
    representations=("point",),
    known=True,
    requirement="point",
    units_rule="same",
):
    return compile_graph(
        GraphSpec(graph_id="g", version=1, nodes=nodes),
        {
            "p": Capabilities(
                provider_id="p",
                provider_revision="v1",
                representations=representations,
                supports_known_future=known,
            )
        },
        {
            "sum": OperatorContract(
                name="sum", required_representation=requirement, units_rule=units_rule
            )
        },
    )


def fails(code, *nodes, **kwargs):
    with pytest.raises(DomainError) as error:
        compile_nodes(*nodes, **kwargs)
    assert error.value.code == code


def test_cycle_is_rejected():
    node = Node(
        node_id="a", kind="transform", inputs=("a",), config={"operator": "identity"}
    )
    with pytest.raises(DomainError) as error:
        compile_graph(GraphSpec(graph_id="g", version=1, nodes=(node,)), {}, {})
    assert error.value.code == "cycle"


def test_cycle_and_missing_input():
    a = Node(node_id="a", kind="transform", inputs=("b",), config={})
    b = Node(node_id="b", kind="transform", inputs=("a",), config={})
    fails("cycle", a, b)
    fails("missing_input", a)


def test_valid_calendar_forecast_is_deterministic():
    nodes = (forecast(known_future="calendar"), source("calendar", "1"), source())
    graph = compile_nodes(*nodes)
    assert graph.order == ("calendar", "s", "f")
    assert graph.dependencies["f"] == ("s", "calendar")
    assert graph == compile_nodes(*nodes)


def test_changed_branch_only():
    graph = compile_nodes(
        source(), forecast(), source("other"), forecast("other_f", "other"), operation()
    )
    assert affected_nodes(graph, {"s"}) == ("f", "op")
    assert affected_nodes(graph, {"s", "f"}) == ("f", "op")
    assert affected_nodes(graph, set()) == ()


def test_quantile_only_cannot_answer_anytime_event():
    fails(
        "unsupported_representation",
        source(),
        forecast(),
        operation(kind="event"),
        representations=("quantiles",),
        requirement="joint_paths",
        units_rule="dimensionless",
    )


@pytest.mark.parametrize("unit", ["unknown", "?", "USD"])
def test_unknown_or_incompatible_units(unit):
    fails(
        "incompatible_units",
        source(),
        forecast(),
        source("s2", unit),
        forecast("f2", "s2"),
        operation(("f", "f2")),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"relation_type": {"s": "candidate"}},
        {"relation_type": {}},
        {"representations": ["joint_paths"]},
        {"horizon": 0},
        {"frequency": "1w"},
    ],
)
def test_invalid_or_candidate_config(change):
    fails(
        "candidate_relation"
        if change == {"relation_type": {"s": "candidate"}}
        else "invalid_config",
        source(),
        forecast(**change),
    )


def test_known_future_requires_capability_and_source_binding():
    fails(
        "unsupported_known_future",
        source(),
        source("cal", "1"),
        forecast(known_future="cal"),
        known=False,
    )
    fails("invalid_binding", source(), forecast(), forecast("next", history="f"))


def test_calendar_mismatch():
    fails("incompatible_calendar", source(frequency="1d"), forecast())


def test_unregistered_provider_and_operator():
    fails("unknown_provider", source(), forecast(provider="missing"))
    fails("unknown_operator", source(), forecast(), operation(operator="missing"))


def test_duplicate_ids_and_inputs():
    fails("duplicate_node", source(), source())
    node = operation(("f", "f"))
    fails("duplicate_input", source(), forecast(), node)


def test_transform_representation_is_conservative():
    first = operation()
    second = Node(
        node_id="event",
        kind="event",
        inputs=("op",),
        config={"operator": "event", "relation_type": {"op": "statistical"}},
    )
    spec = GraphSpec(
        graph_id="g", version=1, nodes=(source(), forecast(), first, second)
    )
    with pytest.raises(DomainError) as error:
        compile_graph(
            spec,
            {
                "p": Capabilities(
                    provider_id="p",
                    provider_revision="1",
                    representations=("point", "joint_paths"),
                    supports_known_future=False,
                )
            },
            {
                "sum": OperatorContract(
                    name="sum", required_representation="point", units_rule="same"
                ),
                "event": OperatorContract(
                    name="event",
                    required_representation="joint_paths",
                    units_rule="dimensionless",
                ),
            },
        )
    assert error.value.code == "unsupported_representation"


def test_probability_output_is_not_an_input_quantity():
    probability = operation(kind="event")
    downstream = Node(
        node_id="after",
        kind="transform",
        inputs=("op", "f"),
        config={
            "operator": "sum",
            "relation_type": {"op": "accounting", "f": "accounting"},
        },
    )
    spec = GraphSpec(
        graph_id="g", version=1, nodes=(source(), forecast(), probability, downstream)
    )
    with pytest.raises(DomainError) as error:
        compile_graph(
            spec,
            {
                "p": Capabilities(
                    provider_id="p",
                    provider_revision="1",
                    representations=("point",),
                    supports_known_future=False,
                )
            },
            {
                "sum": OperatorContract(
                    name="sum",
                    required_representation="point",
                    units_rule="probability",
                )
            },
        )
    assert error.value.code == "incompatible_units"


def test_public_config_parser_and_explicit_source_binding():
    from forecast_anything.graph import SourceConfig, parse_node_config

    parsed = parse_node_config(source())
    assert isinstance(parsed, SourceConfig)
    assert parsed.source_id == "s"


@pytest.mark.parametrize("relation", ["computational", "causal"])
def test_unapproved_relation_semantics_rejected(relation):
    fails("invalid_config", source(), forecast(relation_type={"s": relation}))


def test_semantic_role_bindings_reference_declared_inputs():
    fails(
        "invalid_binding",
        source(),
        forecast(),
        operation(parameters={"bindings": {"inflow": "missing"}}),
    )
    graph = compile_nodes(
        source(), forecast(), operation(parameters={"bindings": {"inflow": "f"}})
    )
    assert graph.order == ("s", "f", "op")
