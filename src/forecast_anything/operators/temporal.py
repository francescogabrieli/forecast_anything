"""Point scenarios and common-world path arithmetic, without implicit resampling."""

from datetime import timezone
from itertools import accumulate

from pydantic import FiniteFloat, ValidationError

from ..contracts import (
    Contract,
    DomainError,
    ForecastResult,
    Identifier,
    OperatorContract,
)


def parse_parameters(schema, config):
    try:
        return schema.model_validate(config)
    except ValidationError as error:
        raise DomainError(
            "invalid_config",
            {
                "errors": error.errors(
                    include_context=False, include_url=False, include_input=False
                )
            },
        ) from error


def aligned_inputs(inputs, *, roles=None):
    if not inputs or (roles is not None and set(inputs) != set(roles)):
        raise DomainError("invalid_binding", {"roles": list(roles or ())})
    if any(not isinstance(value, ForecastResult) for value in inputs.values()):
        raise DomainError(
            "unsupported_representation", {"reason": "forecast results required"}
        )
    values = []
    for value in inputs.values():
        value = ForecastResult.model_validate(value.model_dump())
        value.timestamps = tuple(t.astimezone(timezone.utc) for t in value.timestamps)
        if (
            not value.series_ids
            or len(set(value.series_ids)) != len(value.series_ids)
            or not value.timestamps
            or any(b <= a for a, b in zip(value.timestamps, value.timestamps[1:]))
            or value.paths == ()
        ):
            raise DomainError(
                "invalid_result",
                {"reason": "nonempty series, ordered timestamps and samples required"},
            )
        values.append(value)
    first = values[0]
    if any(value.timestamps != first.timestamps for value in values):
        raise DomainError("incompatible_calendar", {})
    if any(value.series_ids != first.series_ids for value in values):
        raise DomainError(
            "incompatible_series", {"reason": "explicit series alignment required"}
        )
    units = {unit for value in values for unit in value.units}
    if len(units) != 1 or any(unit.lower() in {"unknown", "?"} for unit in units):
        raise DomainError("incompatible_units", {})
    common = {
        rep
        for rep, field in (("point", "point"), ("joint_paths", "paths"))
        if all(getattr(value, field) is not None for value in values)
    }
    if not common:
        raise DomainError(
            "unsupported_representation", {"accepted": ["point", "joint_paths"]}
        )
    if "joint_paths" in common and any(
        value.sample_group_id != first.sample_group_id
        or len(value.paths) != len(first.paths)
        for value in values
    ):
        raise DomainError("incompatible_samples", {})
    return values, common


def transformed(name, values, common, transform):
    first = values[0]
    point = transform([value.point for value in values]) if "point" in common else None
    paths = (
        tuple(
            transform([value.paths[i] for value in values])
            for i in range(len(first.paths))
        )
        if "joint_paths" in common
        else None
    )
    return ForecastResult(
        provider_id=f"operator:{name}",
        provider_revision="1",
        series_ids=first.series_ids,
        timestamps=first.timestamps,
        units=first.units,
        point=point,
        paths=paths,
        quantiles=None,
        sample_group_id=first.sample_group_id if paths is not None else None,
        assumptions=tuple(
            dict.fromkeys(a for value in values for a in value.assumptions)
        )
        + (
            f"operator={name}; exact timestamp/series/unit alignment; no marginal quantile arithmetic",
        ),
    )


def transform_contract(name):
    return OperatorContract(
        name=name,
        required_representation="point",
        units_rule="same",
        accepted_representations=("point", "joint_paths"),
        output_representation="preserve",
    )


class SumAligned:
    def contract(self):
        return transform_contract("sum_aligned")

    def apply(self, inputs, config):
        parse_parameters(Contract, config)
        values, common = aligned_inputs(inputs)

        def total(matrices):
            return tuple(
                tuple(sum(items) for items in zip(*rows)) for rows in zip(*matrices)
            )

        return transformed("sum_aligned", values, common, total)


class BalanceConfig(Contract):
    initial_value: FiniteFloat
    unit: Identifier


class CumulativeBalance:
    def contract(self):
        return transform_contract("cumulative_balance")

    def apply(self, inputs, config):
        parameters = parse_parameters(BalanceConfig, config)
        ordered = {
            role: inputs[role] for role in ("inflow", "outflow") if role in inputs
        }
        if set(inputs) != {"inflow", "outflow"}:
            raise DomainError("invalid_binding", {"roles": ["inflow", "outflow"]})
        values, common = aligned_inputs(ordered, roles=("inflow", "outflow"))
        if any(unit != parameters.unit for value in values for unit in value.units):
            raise DomainError("incompatible_units", {"unit": parameters.unit})

        def balance(matrices):
            return tuple(
                tuple(
                    accumulate(
                        (a - b for a, b in zip(inflow, outflow)),
                        initial=parameters.initial_value,
                    )
                )[1:]
                for inflow, outflow in zip(*matrices)
            )

        answer = transformed("cumulative_balance", values, common, balance)
        answer.assumptions += (
            f"initial_value={parameters.initial_value}; unit={parameters.unit}; inflow/outflow are per-step quantities",
        )
        return answer
