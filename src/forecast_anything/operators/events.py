"""Window events evaluated once per complete joint path."""

from typing import Literal

from pydantic import FiniteFloat

from ..contracts import Contract, DomainError, ForecastResult, OperatorContract
from .temporal import aligned_inputs, parse_parameters


class ExceedConfig(Contract):
    threshold: FiniteFloat
    comparator: Literal["gt", "lt"]


class AnyExceed:
    def contract(self):
        return OperatorContract(
            name="any_exceed",
            required_representation="joint_paths",
            units_rule="probability",
            accepted_representations=("joint_paths",),
            output_representation="point",
        )

    def apply(self, inputs, config):
        parameters = parse_parameters(ExceedConfig, config)
        values, common = aligned_inputs(inputs, roles=("value",))
        if "joint_paths" not in common:
            raise DomainError("unsupported_representation", {"required": "joint_paths"})
        value = values[0]
        hits = sum(
            any(
                x > parameters.threshold
                if parameters.comparator == "gt"
                else x < parameters.threshold
                for row in path
                for x in row
            )
            for path in value.paths
        )
        return ForecastResult(
            provider_id="operator:any_exceed",
            provider_revision="1",
            series_ids=("event:any_exceed",),
            timestamps=(value.timestamps[-1],),
            units=("probability",),
            point=((hits / len(value.paths),),),
            quantiles=None,
            paths=None,
            sample_group_id=None,
            assumptions=value.assumptions
            + (
                f"event=any_exceed; comparator={parameters.comparator}; threshold={parameters.threshold}; scope=any series at any timestamp",
                f"window=[{value.timestamps[0].isoformat()}, {value.timestamps[-1].isoformat()}]; inclusive forecast grid",
                f"empirical frequency; samples={len(value.paths)}; sample_group_id={value.sample_group_id}",
            ),
        )
