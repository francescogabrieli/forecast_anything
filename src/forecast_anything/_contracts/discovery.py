"""Discovery candidates, qualification, watches, and evaluations."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)

from .common import Contract, Identifier, OpaqueDictionary
from .forecasts import GraphSpec
from .sources import SourceProfile


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
    requalification_due_at: AwareDatetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    requalification_reason: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    requalification_new_origins: Annotated[int, Field(ge=0, strict=True)] = 0
    qualification_snapshot_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    last_run_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    forecast_horizon_end: AwareDatetime | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    quality_reason: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
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
