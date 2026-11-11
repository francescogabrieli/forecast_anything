"""Validate forecast representations and evaluate graph operator outputs."""

from copy import deepcopy
from datetime import UTC

from .contracts import (
    REPRESENTATION_FIELDS,
    DomainError,
    ForecastResult,
    Node,
    OperatorContract,
    Snapshot,
)
from .graph import OperatorConfig
from .operators.base import Operator


def _result(value) -> ForecastResult:
    # Revalidation catches mutable models and malicious adapters using model_copy.
    result = ForecastResult.model_validate(value.model_dump())
    # Compare absolute instants: same-ZoneInfo datetime comparisons ignore fold.
    result.timestamps = tuple(
        timestamp.astimezone(UTC) for timestamp in result.timestamps
    )
    if not result.series_ids or len(set(result.series_ids)) != len(result.series_ids):
        raise DomainError(
            "invalid_result", {"reason": "series IDs must be nonempty and unique"}
        )
    if not result.timestamps or any(
        b <= a for a, b in zip(result.timestamps, result.timestamps[1:], strict=False)
    ):
        raise DomainError(
            "invalid_result", {"reason": "timestamps must be nonempty and ordered"}
        )
    if result.paths is not None and not result.paths:
        raise DomainError("invalid_result", {"reason": "paths must contain samples"})
    if all(getattr(result, rep) is None for rep in ("point", "quantiles", "paths")):
        raise DomainError(
            "invalid_result", {"reason": "missing numerical representation"}
        )
    return result


def _require_representations(result, representations):
    if any(
        rep not in REPRESENTATION_FIELDS
        or not getattr(result, REPRESENTATION_FIELDS[rep])
        for rep in representations
    ):
        raise DomainError(
            "unsupported_representation", {"required": list(representations)}
        )


def apply_operator(
    node: Node,
    config: OperatorConfig,
    operators: dict[str, Operator],
    contract: OperatorContract,
    values: dict[str, Snapshot | ForecastResult],
    guaranteed: dict[str, set[str]],
    reusable: ForecastResult | None,
) -> tuple[ForecastResult, dict[str, str], set[str]]:
    node_id = node.node_id
    bindings = config.parameters.get("bindings") or {name: name for name in node.inputs}
    inputs = {role: values[parent] for role, parent in bindings.items()}
    forecasts = [
        value for value in inputs.values() if isinstance(value, ForecastResult)
    ]
    common = contract.accepted_inputs().intersection(
        *(guaranteed[parent] for parent in node.inputs)
    )
    if not common or len(forecasts) != len(inputs):
        raise DomainError("unsupported_representation", {"node_id": node_id})
    for value in forecasts:
        _require_representations(value, common)
    if forecasts and any(
        value.timestamps != forecasts[0].timestamps for value in forecasts
    ):
        raise DomainError("incompatible_calendar", {"node_id": node_id})
    if (
        "joint_paths" in common
        and forecasts
        and any(
            value.sample_group_id != forecasts[0].sample_group_id
            or len(value.paths) != len(forecasts[0].paths)
            for value in forecasts
        )
    ):
        raise DomainError("incompatible_samples", {"node_id": node_id})
    parameters = {k: v for k, v in config.parameters.items() if k != "bindings"}
    result = _result(
        reusable
        if reusable is not None
        else operators[config.operator].apply(deepcopy(inputs), deepcopy(parameters))
    )
    output_reps = contract.output_representations(common, node.kind)
    _require_representations(result, output_reps)
    if (
        "joint_paths" in output_reps
        and "joint_paths" in common
        and (
            result.sample_group_id != forecasts[0].sample_group_id
            or len(result.paths) != len(forecasts[0].paths)
        )
    ):
        raise DomainError("incompatible_samples", {"node_id": node_id})
    if contract.output_representation == "preserve" and any(
        result.series_ids != value.series_ids for value in forecasts
    ):
        raise DomainError("incompatible_series", {"node_id": node_id})
    if (
        node.kind == "event"
        and contract.output_representation == "point"
        and contract.units_rule == "probability"
    ) and (
        len(result.series_ids) != 1
        or result.timestamps != (forecasts[0].timestamps[-1],)
        or result.paths is not None
        or result.quantiles is not None
        or result.sample_group_id is not None
        or not 0 <= result.point[0][0] <= 1
    ):
        raise DomainError("invalid_event_output", {"node_id": node_id})
    input_units = {
        unit
        for value in inputs.values()
        for unit in (
            value.units
            if isinstance(value, ForecastResult)
            else tuple(o.unit for o in value.observations)
        )
    }
    expected_units = (
        {"1"}
        if contract.units_rule == "dimensionless"
        else {"probability"}
        if contract.units_rule == "probability"
        else input_units
    )
    if set(result.units) != expected_units:
        raise DomainError("incompatible_units", {"node_id": node_id})
    if (
        node.kind == "transform"
        and forecasts
        and result.timestamps != forecasts[0].timestamps
    ):
        raise DomainError("incompatible_calendar", {"node_id": node_id})
    return result, bindings, output_reps
