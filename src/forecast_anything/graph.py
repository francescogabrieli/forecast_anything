"""Structural and typed compilation; no providers or numerical operators execute here.

Relations are declared per input in ``config.relation_type``. Operator-specific
values and semantic role bindings belong to ``parameters``; runtime passes direct
parameters and, when supplied, complete role-keyed input bindings to apply. Calendar checks establish declared compatibility,
not actual timestamp or joint-sample alignment, which execution must also verify.
"""

from __future__ import annotations

import heapq
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationError

from .contracts import (
    Capabilities,
    CompiledGraph,
    Contract,
    DomainError,
    GraphSpec,
    Identifier,
    Node,
    OpaqueDictionary,
    OperatorContract,
)

Frequency = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*[hd]$")]


class SourceConfig(Contract):
    source_id: Identifier
    series_ids: tuple[Identifier, ...] = Field(min_length=1)
    units: tuple[Identifier, ...] = Field(min_length=1)
    frequency: Frequency


class DependentConfig(Contract):
    relation_type: dict[
        Identifier, Literal["accounting", "physical", "statistical", "candidate"]
    ]


class ForecastConfig(DependentConfig):
    provider: Identifier
    history: Identifier
    known_future: Identifier | None = None
    horizon: int = Field(gt=0, strict=True)
    frequency: Frequency
    options: OpaqueDictionary = Field(default_factory=dict)


class OperatorConfig(DependentConfig):
    operator: Identifier
    parameters: OpaqueDictionary = Field(default_factory=dict)


CONFIG_SCHEMAS = {
    "source": SourceConfig,
    "forecast": ForecastConfig,
    "transform": OperatorConfig,
    "event": OperatorConfig,
}


def _fail(code: str, node_id: str, **details: object) -> None:
    raise DomainError(code, {"node_id": node_id, **details})


def parse_node_config(node: Node) -> SourceConfig | ForecastConfig | OperatorConfig:
    """Parse registered shape; compilation additionally validates graph bindings."""
    try:
        return CONFIG_SCHEMAS[node.kind].model_validate(node.config)
    except ValidationError as error:
        _fail(
            "invalid_config",
            node.node_id,
            errors=error.errors(include_context=False, include_url=False),
        )


def compile_graph(
    spec: GraphSpec,
    capabilities: dict[str, Capabilities],
    operator_contracts: dict[str, OperatorContract],
) -> CompiledGraph:
    """Reject structural faults first, then validate all declared execution types.

    Ready nodes are ordered lexically, independent of the input node ordering.
    Trusted units rules ``same``, ``dimensionless``, and ``probability`` require
    known equal input units; outputs respectively retain units, ``1``, or
    ``probability``. Transforms guarantee
    their common accepted representations only when explicitly declared to preserve
    them; legacy transforms retain the required representation and events point.
    """
    # Revalidate registrations, including adapters using mutable models/model_copy.
    capabilities = {
        name: Capabilities.model_validate(value.model_dump())
        for name, value in capabilities.items()
    }
    operator_contracts = {
        name: OperatorContract.model_validate(value.model_dump())
        for name, value in operator_contracts.items()
    }
    nodes = {}
    for node in spec.nodes:
        if node.node_id in nodes:
            _fail("duplicate_node", node.node_id)
        nodes[node.node_id] = node
    children = {key: [] for key in nodes}
    remaining = {}
    for node in spec.nodes:
        if len(set(node.inputs)) != len(node.inputs):
            _fail("duplicate_input", node.node_id)
        for parent in node.inputs:
            if parent not in nodes:
                _fail("missing_input", node.node_id, input=parent)
            children[parent].append(node.node_id)
        remaining[node.node_id] = len(node.inputs)
    ready = [key for key in nodes if remaining[key] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        key = heapq.heappop(ready)
        order.append(key)
        for child in children[key]:
            remaining[child] -= 1
            if remaining[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(nodes):
        raise DomainError(
            "cycle", {"nodes": sorted(key for key in nodes if remaining[key])}
        )

    # Metadata is compiler-local: CompiledGraph retains the original wire spec.
    units, calendars, representations = {}, {}, {}
    for key in order:
        node = nodes[key]
        config = parse_node_config(node)
        if isinstance(config, SourceConfig):
            if (
                node.inputs
                or len(config.series_ids) != len(config.units)
                or len(set(config.series_ids)) != len(config.series_ids)
            ):
                _fail("invalid_config", key)
            units[key] = config.units
            calendars[key] = (config.frequency, None)
            representations[key] = {"observations"}
            continue
        if set(config.relation_type) != set(node.inputs):
            _fail(
                "invalid_config",
                key,
                reason="relation_type must cover exactly the inputs",
            )
        if "candidate" in config.relation_type.values():
            _fail("candidate_relation", key)
        if isinstance(config, ForecastConfig):
            bindings = {config.history}
            if config.known_future is not None:
                bindings.add(config.known_future)
            if bindings != set(node.inputs) or any(
                nodes[parent].kind != "source" for parent in bindings
            ):
                _fail("invalid_binding", key)
            capability = capabilities.get(config.provider)
            if capability is None or capability.provider_id != config.provider:
                _fail("unknown_provider", key, provider=config.provider)
            if config.known_future is not None and not capability.supports_known_future:
                _fail("unsupported_known_future", key)
            if any(calendars[parent][0] != config.frequency for parent in bindings):
                _fail("incompatible_calendar", key)
            units[key] = units[config.history]
            calendars[key] = (config.frequency, (0, config.horizon))
            representations[key] = set(capability.representations)
            continue
        bindings = config.parameters.get("bindings", {})
        if not isinstance(bindings, dict) or any(
            not isinstance(role, str)
            or not role.strip()
            or not isinstance(parent, str)
            or parent not in node.inputs
            for role, parent in bindings.items()
        ):
            _fail("invalid_binding", key)
        if "bindings" in config.parameters and (
            len(set(bindings.values())) != len(bindings)
            or set(bindings.values()) != set(node.inputs)
        ):
            _fail(
                "invalid_binding", key, reason="bindings must cover inputs exactly once"
            )
        contract = operator_contracts.get(config.operator)
        if contract is None or contract.name != config.operator:
            _fail("unknown_operator", key, operator=config.operator)
        if not node.inputs:
            _fail("invalid_config", key, reason="operator requires inputs")
        common = contract.accepted_inputs().intersection(
            *(representations[parent] for parent in node.inputs)
        )
        if not common:
            _fail(
                "unsupported_representation",
                key,
                required=contract.required_representation,
            )
        if len({calendars[parent] for parent in node.inputs}) != 1:
            _fail("incompatible_calendar", key)
        input_units = {unit for parent in node.inputs for unit in units[parent]}
        if contract.units_rule not in {"same", "dimensionless", "probability"}:
            _fail("unsupported_units_rule", key, units_rule=contract.units_rule)
        if len(input_units) != 1 or any(
            unit.lower() in {"unknown", "?"} for unit in input_units
        ):
            _fail("incompatible_units", key, units=sorted(input_units))
        units[key] = {"dimensionless": ("1",), "probability": ("probability",)}.get(
            contract.units_rule, tuple(input_units)
        )
        calendars[key] = calendars[node.inputs[0]]
        if (
            node.kind == "event"
            and contract.output_representation == "point"
            and contract.units_rule == "probability"
        ):
            frequency, (start, horizon) = calendars[key]
            calendars[key] = (frequency, (start + horizon - 1, 1))
        representations[key] = contract.output_representations(common, node.kind)
    return CompiledGraph(
        spec=spec,
        order=tuple(order),
        dependencies={key: nodes[key].inputs for key in order},
    )


def affected_nodes(graph: CompiledGraph, changed: set[str]) -> tuple[str, ...]:
    """Return ordered strict descendants of the changed nodes (not the seeds)."""
    reached = set(changed)
    affected = []
    for key in graph.order:
        if any(parent in reached for parent in graph.dependencies[key]):
            reached.add(key)
            affected.append(key)
    return tuple(affected)
