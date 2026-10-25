"""Version-one wire contracts shared by graph, providers, and execution."""
from __future__ import annotations

from math import isfinite
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Matrix = tuple[tuple[FiniteFloat, ...], ...]


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
    representations: tuple[Identifier, ...]
    supports_known_future: bool


class OperatorContract(Contract):
    name: Identifier
    required_representation: Identifier
    units_rule: Identifier


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
            if len(matrix) != series_count or any(len(row) != horizon for row in matrix):
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
