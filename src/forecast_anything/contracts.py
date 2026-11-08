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
    computed_field,
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


class ForecastSelection(Contract):
    provider: Identifier
    options: Annotated[dict[str, JsonValue], AfterValidator(_require_finite_nested)] = (
        Field(default_factory=dict)
    )
    horizon: Annotated[int, Field(ge=1, le=366, strict=True)]
    baseline_period: Annotated[int, Field(ge=1, le=10000, strict=True)] = 1


class QuestionForecastSelection(ForecastSelection):
    @model_validator(mode="after")
    def validate_bounded_options(self) -> QuestionForecastSelection:
        import json

        if len(json.dumps(self.options, ensure_ascii=False).encode("utf-8")) > 1024:
            raise ValueError("question selection options exceed 1024 bytes")
        return self


class BacktestSettings(Contract):
    max_origins_per_partition: Annotated[int, Field(ge=1, le=50, strict=True)] = 10
    origin_offset_seconds: Annotated[int, Field(ge=0, strict=True)] = 0


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


class SnapshotSummary(Contract):
    snapshot_id: Identifier
    as_of: AwareDatetime
    observation_count: Annotated[int, Field(ge=0, strict=True)]
    series_count: Annotated[int, Field(ge=0, strict=True)]
    missing_count: Annotated[int, Field(ge=0, strict=True)]
    revision_count: Annotated[int, Field(ge=0, strict=True)]
    event_time_start: AwareDatetime | None
    event_time_end: AwareDatetime | None
    available_at_start: AwareDatetime | None
    available_at_end: AwareDatetime | None
    assumption_count: Annotated[int, Field(ge=0, strict=True)]
    assumptions: Annotated[tuple[str, ...], Field(max_length=16)]
    assumptions_truncated: bool


class SnapshotSeriesSummary(Contract):
    snapshot_id: Identifier
    series_id: Identifier
    observation_count: Annotated[int, Field(ge=0, strict=True)]
    missing_count: Annotated[int, Field(ge=0, strict=True)]
    revision_count: Annotated[int, Field(ge=0, strict=True)]
    unit_count: Annotated[int, Field(ge=0, strict=True)]
    units: Annotated[tuple[str, ...], Field(max_length=8)]
    units_truncated: bool
    event_time_start: AwareDatetime | None
    event_time_end: AwareDatetime | None
    available_at_start: AwareDatetime | None
    available_at_end: AwareDatetime | None


class SnapshotSeriesPage(Contract):
    snapshot_id: Identifier
    series: tuple[SnapshotSeriesSummary, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None


class ResourceIdentity(Contract):
    kind: Literal["run", "question", "report"]
    resource_id: Identifier


class WorkspaceIdentity(Contract):
    workspace_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


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
    source_revision: Identifier | None = None
    fields: dict[str, SourceField]
    proposed_mapping: dict[str, JsonValue]
    unresolved: tuple[str, ...]
    assumptions: tuple[str, ...]
    sample_rows: Annotated[
        tuple[dict[str, SourceSampleValue], ...], Field(max_length=100)
    ] = ()


class CsvPreviewRequest(Contract):
    spec: SourceSpec
    as_of: AwareDatetime


class CsvConfirmation(Contract):
    adapter_session: (
        Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")] | None
    ) = None
    key: Identifier
    spec: SourceSpec
    proposal_version: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    as_of: AwareDatetime


class CsvPreview(Contract):
    suggestions: dict[str, str] = Field(default_factory=dict)
    profile: SourceProfile
    content_digest: str
    proposal_version: str


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


class DiscoveryBudget(Contract):
    max_candidates: Annotated[int, Field(ge=0, strict=True)] = 10
    max_tool_calls: Annotated[int, Field(ge=0, strict=True)] = 20


class VerificationProtocol(Contract):
    """Frozen before final evaluation; no post-selection correction is assumed."""

    criterion: Literal["mae", "brier"] = "mae"
    target_node_id: Identifier = "question"
    reference_node_id: Identifier = "reference"
    selection_method: Literal["prespecified_holdout", "exploratory", "corrected"] = (
        "prespecified_holdout"
    )


class CandidateCostEstimate(Contract):
    """Static execution work, not a latency or monetary quote.

    Unknown/unsupported execution has no numeric value; zero is never a stand-in
    for an unavailable estimate. The compiler owns the estimate and its basis.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    status: Literal["known", "unavailable"] = "unavailable"
    value: Annotated[int, Field(ge=0, strict=True)] | None = None
    unit: Literal["provider_calls_per_run"] = "provider_calls_per_run"
    basis: Identifier = "not_estimated"

    @model_validator(mode="after")
    def validate_availability(self) -> CandidateCostEstimate:
        if (self.status == "known") != (self.value is not None):
            raise ValueError(
                "known cost requires a value; unavailable cost requires null"
            )
        return self


class Candidate(Contract):
    candidate_id: Identifier
    template_id: Identifier
    source_ids: tuple[Identifier, ...]
    graph: GraphSpec
    reason: Identifier
    protocol_id: Identifier
    epoch_id: Identifier
    protocol: VerificationProtocol = Field(default_factory=VerificationProtocol)
    estimated_cost: CandidateCostEstimate = Field(default_factory=CandidateCostEstimate)
    source_profiles: tuple[SourceProfile, ...] = ()
    executable: bool = False
    unresolved: tuple[str, ...] = ()


class DiscoveryEpoch(Contract):
    epoch_id: Identifier
    source_snapshot_ids: tuple[Identifier, ...]
    explored_candidate_ids: tuple[Identifier, ...]
    final_origin_ids: tuple[Identifier, ...]
    final_candidate_id: Identifier | None = None
    tuning_origin_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_partitions(self) -> DiscoveryEpoch:
        for values in (
            self.source_snapshot_ids,
            self.explored_candidate_ids,
            self.final_origin_ids,
            self.tuning_origin_ids,
        ):
            if len(set(values)) != len(values):
                raise ValueError("discovery identities must be unique")
        if set(self.final_origin_ids) & set(self.tuning_origin_ids):
            raise ValueError("final origins cannot be used for tuning")
        if self.final_candidate_id is not None and (
            self.final_candidate_id not in self.explored_candidate_ids
        ):
            raise ValueError("final block owner must be a declared candidate")
        return self


class EligibilityDecision(Contract):
    action: Literal["activate", "provisional", "reject"]
    reason_codes: tuple[Identifier, ...]
    candidate_id: Identifier | None = None
    protocol_id: Identifier | None = None
    epoch_id: Identifier | None = None
    evaluation_ids: tuple[Identifier, ...] = ()
    backtest_id: Identifier | None = None
    policy_version: Identifier = "discovery-v1"


class Watch(Contract):
    """Current relevance state; Candidate and decision retain their issued lineage.

    Evidence applicability is current metadata, independent of immutable scores.
    A minimal watch can be displayed without lineage, but cannot be qualified.
    """

    migration_reason: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    watch_id: Identifier
    candidate_id: Identifier
    lifecycle: Literal["candidate", "evaluating", "active", "paused", "unsupported"]
    quality: Literal["provisional", "usable", "stale", "degraded"]
    graph_id: Identifier
    graph_version: int
    policy_version: Identifier
    next_due_at: AwareDatetime
    muted: bool
    priority: Annotated[int, Field(ge=0, le=5, strict=True)] = 3
    candidate: Candidate | None = None
    eligibility_decision: EligibilityDecision | None = None
    source_snapshot_ids: tuple[Identifier, ...] = ()
    evidence_applicable: bool = False
    reevaluation_required: bool = True
    invalidated_evaluation_ids: tuple[Identifier, ...] = ()
    candidate_invalidated: bool = False
    supersedes_watch_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_lineage(self) -> Watch:
        if self.supersedes_watch_id == self.watch_id:
            raise ValueError("watch cannot supersede itself")
        if self.candidate is not None and (
            self.candidate_id != self.candidate.candidate_id
            or (self.graph_id, self.graph_version)
            != (self.candidate.graph.graph_id, self.candidate.graph.version)
        ):
            raise ValueError("watch candidate lineage mismatch")
        if self.eligibility_decision is not None and (
            self.eligibility_decision.candidate_id != self.candidate_id
            or self.eligibility_decision.policy_version != self.policy_version
            or self.candidate is None
            or (
                self.eligibility_decision.protocol_id,
                self.eligibility_decision.epoch_id,
            )
            != (self.candidate.protocol_id, self.candidate.epoch_id)
        ):
            raise ValueError("watch decision lineage mismatch")
        return self

    @property
    def operational(self) -> bool:
        """Only current, qualified, unmuted watches may emit operational alerts."""
        return (
            self.lifecycle == "active"
            and self.quality == "usable"
            and not self.muted
            and self.evidence_applicable
            and not self.reevaluation_required
            and not self.candidate_invalidated
            and self.eligibility_decision is not None
            and self.eligibility_decision.action == "activate"
        )


class EvaluationContext(Contract):
    """Trusted evaluator attestation, never accepted as an agent proposal.

    Origin IDs identify the frozen target window, independently of model/config.
    The caller establishes temporal/semantic validity using Plan 02 evaluation.
    Defaults fail closed when that verification has not been performed.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    candidate_id: Identifier
    protocol_id: Identifier
    epoch_id: Identifier
    origin_id: Identifier
    partition: Literal["exploration", "selection", "final"]
    source_snapshot_ids: tuple[Identifier, ...]
    target_start: AwareDatetime
    target_end: AwareDatetime
    temporal_valid: bool = False
    semantic_valid: bool = False

    @model_validator(mode="after")
    def validate_window(self) -> EvaluationContext:
        if self.target_end < self.target_start:
            raise ValueError("target window must be ordered")
        return self


class EvaluationRecord(Contract):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    evaluation_id: Identifier
    run_id: Identifier
    actuals_snapshot_id: Identifier
    status: Literal["pending", "evaluated", "insufficient_evidence"]
    metrics: Annotated[OpaqueDictionary, AfterValidator(_immutable)]
    origin_count: Annotated[int, Field(ge=0, strict=True)]
    assumptions: tuple[str, ...]
    discovery: EvaluationContext | None = None


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


class SourceView(Contract):
    source_id: Identifier
    revision: Identifier
    kind: Literal["csv", "http_json"]
    refresh_seconds: int


class SourceConfiguration(Contract):
    source_id: Identifier
    kind: Literal["csv", "http_json"]
    location: str = Field(repr=False)
    mapping: dict[str, JsonValue]
    refresh_seconds: int
    has_secret_ref: bool


class SourceRegistration(SourceView):
    profile: SourceProfile
    job_id: Identifier
    epoch_id: Identifier


class CsvConfirmationResult(SourceRegistration):
    replayed: bool
    session_grant: bool = False


class SourceRefreshRequest(Contract):
    key: Identifier


class CandidateRequest(Contract):
    template_id: Identifier
    source_ids: tuple[Identifier, ...]
    reason: Identifier
    selection_method: Literal["prespecified_holdout", "exploratory", "corrected"] = (
        "prespecified_holdout"
    )


class WatchRequest(Contract):
    candidate_id: Identifier
    next_due_at: AwareDatetime


class WatchPatch(Contract):
    muted: Annotated[bool, Field(strict=True)] | None = None
    priority: Annotated[int, Field(ge=0, le=5, strict=True)] | None = None

    @model_validator(mode="after")
    def require_control(self):
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set
        ):
            raise ValueError("at least one non-null control is required")
        return self


class WatchView(Watch):
    @model_validator(mode="before")
    @classmethod
    def discard_derived_operational(cls, value):
        if isinstance(value, dict) and "operational" in value:
            value = dict(value)
            value.pop("operational")
        return value

    @computed_field
    @property
    def operational(self) -> bool:
        return super().operational


class WatchHistoryEntry(Contract):
    sequence: Annotated[int, Field(ge=1, strict=True)]
    event_id: Identifier
    occurred_at: AwareDatetime
    event: OpaqueDictionary
    watch: WatchView


class WatchHistoryPage(Contract):
    entries: tuple[WatchHistoryEntry, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None


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


QuestionTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
QuestionMeaning = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
QuestionSourceId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
QuestionFact = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]


class QuestionCreateRequest(Contract):
    key: Identifier
    title: QuestionTitle
    meaning: QuestionMeaning
    source_ids: Annotated[tuple[QuestionSourceId, ...], Field(max_length=16)] = ()
    selection: QuestionForecastSelection


class QuestionRevisionRequest(Contract):
    key: Identifier
    expected_revision: Annotated[int, Field(ge=1, strict=True)]
    meaning: QuestionMeaning
    source_ids: Annotated[tuple[QuestionSourceId, ...], Field(max_length=16)] = ()
    selection: QuestionForecastSelection


class QuestionTitlePatch(Contract):
    title: QuestionTitle | None = None
    status: Literal["open", "paused", "resolved"] | None = None

    @model_validator(mode="after")
    def require_update(self) -> QuestionTitlePatch:
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("at least one non-null question field is required")
        return self


class QuestionRevision(Contract):
    question_id: Identifier
    revision: Annotated[int, Field(ge=1, strict=True)]
    meaning: QuestionMeaning
    source_ids: Annotated[tuple[QuestionSourceId, ...], Field(max_length=16)]
    selection: QuestionForecastSelection
    created_at: AwareDatetime


class QuestionView(Contract):
    question_id: Identifier
    title: Identifier
    status: Literal["open", "paused", "resolved"]
    current_revision: Annotated[int, Field(ge=1, strict=True)]
    revision: QuestionRevision
    revision_count: Annotated[int, Field(ge=1, strict=True)]
    reference_count: Annotated[int, Field(ge=0, strict=True)]
    created_at: AwareDatetime
    updated_at: AwareDatetime


class QuestionReferenceRequest(Contract):
    key: Identifier
    revision: Annotated[int, Field(ge=1, strict=True)]
    target_type: Literal[
        "candidate", "run", "backtest", "watch", "evaluation", "operation"
    ]
    target_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    note: Annotated[str, StringConstraints(max_length=800)] = ""


class QuestionReference(Contract):
    reference_id: Identifier
    question_id: Identifier
    revision: Annotated[int, Field(ge=1, strict=True)]
    target_type: Literal[
        "candidate", "run", "backtest", "watch", "evaluation", "operation"
    ]
    target_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    note: Annotated[str, StringConstraints(max_length=800)]
    created_at: AwareDatetime


class QuestionPage(Contract):
    questions: tuple[QuestionView, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None


class QuestionRevisionPage(Contract):
    revisions: tuple[QuestionRevision, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None


class QuestionReferencePage(Contract):
    references: tuple[QuestionReference, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None


class OperationCreateRequest(Contract):
    key: Identifier
    question_id: Identifier | None = None
    question_revision: Annotated[int, Field(ge=1, strict=True)] | None = None
    phase: Literal["collecting", "ready"] = "collecting"
    missing_data: Annotated[tuple[QuestionFact, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def validate_question_revision(self) -> OperationCreateRequest:
        if (self.question_id is None) != (self.question_revision is None):
            raise ValueError(
                "question_id and question_revision must be supplied together"
            )
        if self.phase == "ready" and self.missing_data:
            raise ValueError("ready operations cannot have missing_data")
        return self


class OperationUpdateRequest(Contract):
    key: Identifier
    expected_version: Annotated[int, Field(ge=1, strict=True)]
    phase: Literal["collecting", "ready"]
    missing_data: Annotated[tuple[QuestionFact, ...], Field(max_length=32)] = ()

    @model_validator(mode="after")
    def validate_readiness(self) -> OperationUpdateRequest:
        if self.phase == "ready" and self.missing_data:
            raise ValueError("ready operations cannot have missing_data")
        return self


class OperationSubmitRequest(Contract):
    expected_version: Annotated[int, Field(ge=1, strict=True)]
    request: JobRequest
    candidate_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_candidate_binding(self) -> OperationSubmitRequest:
        if (self.request.kind == "run") != (self.candidate_id is not None):
            raise ValueError("run operations require candidate_id")
        return self


class OperationView(Contract):
    operation_id: Identifier
    question_id: Identifier | None
    question_revision: Annotated[int, Field(ge=1, strict=True)] | None
    version: Annotated[int, Field(ge=1, strict=True)]
    phase: Literal["collecting", "ready"]
    state: Literal["open", "reserved", "submitted", "completed", "failed"]
    missing_data: tuple[Identifier, ...]
    request_kind: Identifier | None
    request_digest: Identifier | None
    source_ids: Annotated[tuple[QuestionSourceId, ...], Field(max_length=16)]
    job_id: Identifier | None
    job_state: Identifier | None
    job_error: OpaqueDictionary | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class OperationPage(Contract):
    operations: tuple[OperationView, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None


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


class ErrorResponse(Contract):
    code: Identifier
    details: OpaqueDictionary
