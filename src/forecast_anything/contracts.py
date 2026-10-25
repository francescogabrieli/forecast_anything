"""Version-one wire contracts shared by graph, providers, and execution."""

from __future__ import annotations

from math import isfinite
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    FiniteFloat,
    JsonValue,
    StringConstraints,
    model_validator,
)

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
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


def _require_finite_nested(value: Any) -> Any:
    """Validate opaque JSON-like data without changing its structure."""
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("opaque dictionary numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            _require_finite_nested(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _require_finite_nested(item)
    return value


OpaqueDictionary = Annotated[dict[str, Any], AfterValidator(_require_finite_nested)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Observation(Contract):
    series_id: Identifier
    event_time: AwareDatetime
    available_at: AwareDatetime
    revision: Identifier
    value: FiniteFloat | None
    unit: Identifier


class Snapshot(Contract):
    snapshot_id: Identifier
    as_of: AwareDatetime
    observations: tuple[Observation, ...]
    assumptions: tuple[str, ...]


class SourceSpec(Contract):
    """Registered source configuration. Mapping is explicit; see profiling module.

    secret_ref names a source-scoped injected credential, never a literal token.
    Locations and secret references must not be passed to agents or logs.
    """

    source_id: Identifier
    kind: Literal["csv", "http_json"]
    location: Annotated[str, StringConstraints(min_length=1)] = Field(repr=False)
    secret_ref: Identifier | None = Field(default=None, repr=False)
    mapping: dict[str, JsonValue] = Field(default_factory=dict)
    refresh_seconds: Annotated[int, Field(gt=0, strict=True)]


class SourceField(Contract):
    data_type: Literal[
        "string", "integer", "number", "boolean", "datetime", "null", "mixed"
    ]
    nullable: bool


SourceSampleValue = str | bool | int | FiniteFloat | None


class SourceProfile(Contract):
    """Sanitized agent-facing view, bounded independently of source size."""

    source_id: Identifier
    fields: dict[str, SourceField]
    proposed_mapping: dict[str, JsonValue]
    unresolved: tuple[str, ...]
    assumptions: tuple[str, ...]
    sample_rows: Annotated[
        tuple[dict[str, SourceSampleValue], ...], Field(max_length=100)
    ] = ()


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
                raise ValueError("representation must have shape series × horizon")

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


class RunRecord(Contract):
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


class _ImmutableDict(dict):
    def _deny(self, *args, **kwargs):
        raise TypeError("evaluation metrics are immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = (
        __ior__
    ) = _deny


def _immutable(value):
    if isinstance(value, dict):
        return _ImmutableDict({key: _immutable(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_immutable(item) for item in value)
    return value


class EvaluationRecord(Contract):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    evaluation_id: Identifier
    run_id: Identifier
    actuals_snapshot_id: Identifier
    status: Literal["pending", "evaluated", "insufficient_evidence"]
    metrics: Annotated[OpaqueDictionary, AfterValidator(_immutable)]
    origin_count: Annotated[int, Field(ge=0, strict=True)]
    assumptions: tuple[str, ...]


class _ErrorPayload(Contract):
    code: Identifier
    details: OpaqueDictionary


class DomainError(Exception):
    """Structured domain failure; serializable through its validated payload."""

    def __init__(self, code: str, details: dict[str, Any]) -> None:
        self._payload = _ErrorPayload(code=code, details=details)
        self.code = self._payload.code
        self.details = self._payload.details
        super().__init__(self.code)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return self._payload.model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        return self._payload.model_dump_json(**kwargs)
