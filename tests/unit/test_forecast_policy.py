import pytest

from forecast_anything.contracts import DomainError, GraphSpec, Node
from forecast_anything.forecast_policy import validate_primary_provider


def graph(primary="timestral", extra=False):
    nodes = [
        Node(node_id="source", kind="source", inputs=(), config={}),
        Node(
            node_id="forecast",
            kind="forecast",
            inputs=("source",),
            config={"provider": primary},
        ),
        Node(
            node_id="reference",
            kind="forecast",
            inputs=("source",),
            config={"provider": "seasonal_naive"},
        ),
        Node(node_id="question", kind="transform", inputs=("forecast",), config={}),
    ]
    if extra:
        nodes.append(
            Node(
                node_id="unused",
                kind="forecast",
                inputs=("source",),
                config={"provider": "timestral"},
            )
        )
    return GraphSpec(graph_id="policy", version=1, nodes=tuple(nodes))


def test_required_provider_accepts_primary_ancestry_and_comparator():
    assert validate_primary_provider(graph(), "timestral") == "question"


def test_unused_timestral_does_not_allow_baseline_primary():
    with pytest.raises(DomainError, match="required_forecast_provider"):
        validate_primary_provider(graph("seasonal_naive", extra=True), "timestral")


def test_library_runtime_policy_is_explicitly_optional():
    assert validate_primary_provider(graph("seasonal_naive"), None) is None


def test_explicit_primary_must_be_terminal():
    with pytest.raises(DomainError, match="invalid_primary_output"):
        validate_primary_provider(graph(), "timestral", "forecast")


def test_ambiguous_raw_graph_requires_primary_output():
    g = graph().model_copy(
        update={
            "nodes": graph().nodes[:3]
            + (
                Node(
                    node_id="model",
                    kind="forecast",
                    inputs=("source",),
                    config={"provider": "timestral"},
                ),
            )
        }
    )
    with pytest.raises(DomainError, match="ambiguous_primary_output"):
        validate_primary_provider(g, "timestral")
    assert validate_primary_provider(g, "timestral", "model") == "model"


def test_baseline_can_only_be_reference_not_a_primary_input():
    candidate = graph()
    nodes = tuple(
        n.model_copy(update={"inputs": ("forecast", "reference")})
        if n.node_id == "question"
        else n
        for n in candidate.nodes
    )
    with pytest.raises(DomainError, match="required_forecast_provider"):
        validate_primary_provider(
            candidate.model_copy(update={"nodes": nodes}), "timestral"
        )
