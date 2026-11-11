"""Forecast selections, graph execution, jobs, and scenarios."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BeforeValidator,
    Field,
    FiniteFloat,
    JsonValue,
    model_validator,
)

from .common import Contract, Identifier, OpaqueDictionary, _require_finite_nested
from .sources import Snapshot

Matrix = tuple[tuple[FiniteFloat, ...], ...]


def canonical_representation(value: Any) -> Any:
    """Accept historical result-field aliases at the registration boundary."""
    return (
        {"quantiles": "marginal_quantiles", "paths": "joint_paths"}.get(value, value)
        if isinstance(value, str)
        else value
    )


Representation = Annotated[
    Literal["point", "marginal_quantiles", "joint_paths"],
    BeforeValidator(canonical_representation),
]
REPRESENTATION_FIELDS = {
    "point": "point",
    "marginal_quantiles": "quantiles",
    "joint_paths": "paths",
}


class ForecastSelection(Contract):
    provider: Identifier
    options: Annotated[dict[str, JsonValue], AfterValidator(_require_finite_nested)] = (
        Field(default_factory=dict)
    )
    horizon: Annotated[int, Field(ge=1, le=366, strict=True)]
    baseline_period: Annotated[int, Field(ge=1, le=10000, strict=True)] = 1


class BacktestSettings(Contract):
    max_origins_per_partition: Annotated[int, Field(ge=1, le=50, strict=True)] = 10
    origin_offset_seconds: Annotated[int, Field(ge=0, strict=True)] = 0


class Node(Contract):
    node_id: Identifier
    kind: Literal["source", "forecast", "transform", "event"]
    inputs: tuple[Identifier, ...]
    config: OpaqueDictionary


class GraphSpec(Contract):
    graph_id: Identifier
    version: int
    nodes: tuple[Node, ...]


class CompiledGraph(Contract):
    spec: GraphSpec
    order: tuple[Identifier, ...]
    dependencies: dict[Identifier, tuple[Identifier, ...]]


class Capabilities(Contract):
    provider_id: Identifier
    provider_revision: Identifier
    representations: tuple[Representation, ...]
    supports_known_future: bool


class OperatorContract(Contract):
    name: Identifier
    required_representation: Representation
    units_rule: Identifier
    # Optional v1 additions: omission retains Plan 01 negotiation and wire meaning.
    accepted_representations: tuple[Representation, ...] | None = None
    output_representation: Representation | Literal["preserve"] | None = None

    @model_validator(mode="after")
    def validate_negotiation(self) -> OperatorContract:
        accepted = self.accepted_representations
        if accepted is not None and (
            not accepted
            or len(set(accepted)) != len(accepted)
            or self.required_representation not in accepted
        ):
            raise ValueError(
                "accepted representations must be unique and include required fallback"
            )
        return self

    def accepted_inputs(self) -> set[str]:
        return set(self.accepted_representations or (self.required_representation,))

    def output_representations(self, common: set[str], kind: str) -> set[str]:
        if self.output_representation == "preserve":
            return common
        if self.output_representation is not None:
            return {self.output_representation}
        return {"point" if kind == "event" else self.required_representation}


class ForecastRequest(Contract):
    snapshot: Snapshot
    horizon: Annotated[int, Field(gt=0)]
    frequency: Identifier
    known_future: Snapshot | None
    options: OpaqueDictionary = Field(default_factory=dict)


class ForecastResult(Contract):
    provider_id: Identifier
    provider_revision: Identifier
    series_ids: tuple[Identifier, ...]
    timestamps: tuple[AwareDatetime, ...]
    units: tuple[Identifier, ...]
    point: Matrix | None
    quantiles: dict[str, Matrix] | None
    paths: tuple[Matrix, ...] | None
    sample_group_id: Identifier | None
    assumptions: tuple[str, ...]

    @model_validator(mode="after")
    def validate_dimensions(self) -> ForecastResult:
        series_count, horizon = len(self.series_ids), len(self.timestamps)
        if len(self.units) != series_count:
            raise ValueError("units must have one entry per series")

        def check_matrix(matrix: Matrix) -> None:
            if len(matrix) != series_count or any(
                len(row) != horizon for row in matrix
            ):
                raise ValueError("representation must have shape series by horizon")

        if self.point is not None:
            check_matrix(self.point)
        if self.quantiles is not None:
            for matrix in self.quantiles.values():
                check_matrix(matrix)
        if self.paths is not None:
            if self.sample_group_id is None:
                raise ValueError("paths require sample_group_id")
            for matrix in self.paths:
                check_matrix(matrix)
        return self


NodeValue = Snapshot | ForecastResult


class ModelSelectionEvidence(Contract):
    report_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=2)]
    series_id: Identifier
    provider: Identifier
    provider_revision: Identifier
    reason: Literal["confirmed_lower_mae", "default_retained"]


class RunRecord(Contract):
    model_selection: ModelSelectionEvidence | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    primary_node_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    run_id: Identifier
    graph_id: Identifier
    graph_version: int
    as_of: AwareDatetime
    snapshot_ids: tuple[Identifier, ...]
    requested_provider: dict[Identifier, Identifier]
    actual_provider: dict[Identifier, Identifier]
    state: Identifier
    results: dict[Identifier, ForecastResult]
    evidence_ids: tuple[Identifier, ...]
    scenario_id: Identifier | None
    parent_run_id: Identifier | None


class EventRecord(Contract):
    cursor: int
    event_id: Identifier
    kind: Identifier
    run_id: Identifier
    payload: OpaqueDictionary


class RunJobRequest(Contract):
    primary_node_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    kind: Literal["run"]
    key: Identifier
    graph: GraphSpec
    snapshot_ids: dict[Identifier, Identifier]
    as_of: AwareDatetime
    previous_run_id: Identifier | None = None


class ConfiguredRunJobRequest(Contract):
    kind: Literal["configured_run"]
    key: Identifier
    source_id: Identifier
    snapshot_id: Identifier
    selection: ForecastSelection
    selection_report_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    challenger_report_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class BacktestJobRequest(Contract):
    kind: Literal["backtest"]
    key: Identifier
    source_id: Identifier
    selection: ForecastSelection
    settings: BacktestSettings = Field(default_factory=BacktestSettings)
    watch_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


class EvaluationJobRequest(Contract):
    kind: Literal["evaluation"]
    key: Identifier
    run_id: Identifier
    actuals_snapshot_id: Identifier


class ResumeJobRequest(Contract):
    kind: Literal["watch_resume"]
    key: Identifier
    watch_id: Identifier


JobRequest = Annotated[
    RunJobRequest
    | ConfiguredRunJobRequest
    | BacktestJobRequest
    | EvaluationJobRequest
    | ResumeJobRequest,
    Field(discriminator="kind"),
]


class JobView(Contract):
    job_id: Identifier
    state: Identifier
    attempt: int
    result: OpaqueDictionary | None = None
    error: OpaqueDictionary | None = None


class ScenarioRequest(Contract):
    base_graph_id: Identifier
    base_version: Annotated[int, Field(gt=0, strict=True)]
    label: Identifier
    source_overrides: dict[Identifier, Snapshot]


class ScenarioRecord(Contract):
    primary_node_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    scenario_id: Identifier
    graph_id: Identifier
    version: int
    parent_run_id: Identifier
    label: Identifier
    snapshot_ids: dict[Identifier, Identifier]


class ScenarioView(ScenarioRecord):
    job_id: Identifier


class CapabilitiesView(Contract):
    required_provider: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    model_status: dict[str, JsonValue] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    providers: dict[str, Capabilities]
    operators: dict[str, OperatorContract]
    templates: tuple[str, ...]
