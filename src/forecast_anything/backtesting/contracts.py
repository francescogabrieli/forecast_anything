"""Frozen backtest records. Raw revision archives are internal plan data only."""

from __future__ import annotations

import json
from datetime import timezone
from hashlib import sha256
from math import isfinite
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    ConfigDict,
    Field,
    FiniteFloat,
    model_validator,
)

from ..contracts import (
    BacktestSettings,
    Capabilities,
    Contract,
    ForecastSelection,
    Identifier,
    Observation,
)

UTCDatetime = Annotated[
    AwareDatetime, AfterValidator(lambda value: value.astimezone(timezone.utc))
]
Partition = Literal["exploration", "selection", "final"]
NonnegativeInt = Annotated[int, Field(ge=0, strict=True)]
NonnegativeFloat = Annotated[FiniteFloat, Field(ge=0)]


def canonical_json(value: object) -> str:
    """Identity encoding: UTF-8, sorted keys, compact JSON, finite numbers."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


class FrozenContract(Contract):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    def _bind_identity(self, field: str) -> None:
        identity = sha256(
            canonical_json(self.model_dump(mode="json", exclude={field})).encode(
                "utf-8"
            )
        ).hexdigest()
        supplied = getattr(self, field)
        if supplied and supplied != identity:
            raise ValueError("content identity mismatch")
        object.__setattr__(self, field, identity)


class ObservationArchive(FrozenContract):
    archive_id: str = ""
    source_id: Identifier
    source_revision: Identifier
    captured_at: UTCDatetime
    observations: Annotated[tuple[Observation, ...], Field(max_length=100000)]
    assumptions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def canonicalize(self) -> ObservationArchive:
        rows = tuple(
            Observation(
                **{
                    **row.model_dump(),
                    "event_time": row.event_time.astimezone(timezone.utc),
                    "available_at": row.available_at.astimezone(timezone.utc),
                    "value": 0.0 if row.value == 0 else row.value,
                }
            )
            for row in self.observations
        )
        object.__setattr__(
            self,
            "observations",
            tuple(
                sorted(
                    rows, key=lambda row: canonical_json(row.model_dump(mode="json"))
                )
            ),
        )
        self._bind_identity("archive_id")
        return self


class PlannedOrigin(FrozenContract):
    ordinal: NonnegativeInt
    partition: Partition
    nominal_origin: UTCDatetime
    issuance_time: UTCDatetime
    target_start: UTCDatetime
    target_end: UTCDatetime

    @model_validator(mode="after")
    def validate_window(self) -> PlannedOrigin:
        if (
            not self.nominal_origin
            <= self.issuance_time
            < self.target_start
            <= self.target_end
        ):
            raise ValueError("origin and target times must be ordered")
        return self


class BacktestPlan(FrozenContract):
    plan_id: str = ""
    backtest_id: Identifier
    watch_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    candidate_id: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    archive: ObservationArchive = Field(repr=False)
    selection: ForecastSelection
    settings: BacktestSettings = Field(default_factory=BacktestSettings)
    provider_contracts: dict[Identifier, Capabilities]
    frequency: Identifier
    calendar: tuple[UTCDatetime, ...]
    origins: Annotated[tuple[PlannedOrigin, ...], Field(max_length=150)]
    actuals_snapshot_id: Identifier
    assumptions: tuple[str, ...] = ()
    protocol_version: Literal["backtest-v1"] = "backtest-v1"

    @model_validator(mode="after")
    def validate_plan(self) -> BacktestPlan:
        if (self.watch_id is None) != (self.candidate_id is None):
            raise ValueError("watch backtest requires both watch and candidate IDs")
        required = {self.selection.provider, "seasonal_naive"}
        if set(self.provider_contracts) != required or any(
            key != value.provider_id for key, value in self.provider_contracts.items()
        ):
            raise ValueError(
                "frozen contracts must identify selected and baseline providers"
            )
        if tuple(sorted(set(self.calendar))) != self.calendar:
            raise ValueError("calendar must be unique and ordered")
        if tuple(origin.ordinal for origin in self.origins) != tuple(
            range(len(self.origins))
        ):
            raise ValueError("origin ordinals must be contiguous from zero")
        for partition in ("exploration", "selection", "final"):
            if (
                sum(origin.partition == partition for origin in self.origins)
                > self.settings.max_origins_per_partition
            ):
                raise ValueError("too many origins in partition")
        if any(
            origin.target_start not in self.calendar
            or origin.target_end not in self.calendar
            for origin in self.origins
        ):
            raise ValueError("origin targets must belong to frozen calendar")
        self._bind_identity("plan_id")
        return self


class OriginOutcome(PlannedOrigin):
    backtest_id: Identifier
    plan_id: Identifier
    status: Literal["evaluated", "excluded", "failed", "insufficient_evidence"]
    reason_code: Identifier | None = None
    run_id: Identifier | None = None
    evaluation_id: Identifier | None = None
    matched_count: NonnegativeInt = 0
    model_mae: NonnegativeFloat | None = None
    baseline_mae: NonnegativeFloat | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> OriginOutcome:
        if self.evaluation_id is not None and self.run_id is None:
            raise ValueError("evaluation requires a run")
        if self.status == "evaluated":
            if (
                self.run_id is None
                or self.evaluation_id is None
                or self.matched_count == 0
                or self.model_mae is None
                or self.baseline_mae is None
                or self.reason_code is not None
            ):
                raise ValueError(
                    "evaluated outcome requires matched numerical evidence"
                )
        elif (
            self.reason_code is None
            or self.matched_count != 0
            or self.model_mae is not None
            or self.baseline_mae is not None
        ):
            raise ValueError("unevaluated outcome requires a reason and no scores")
        return self


class PartitionScore(FrozenContract):
    partition: Partition
    planned: NonnegativeInt
    evaluated: NonnegativeInt = 0
    excluded: NonnegativeInt = 0
    failed: NonnegativeInt = 0
    insufficient: NonnegativeInt = 0
    matched_count: NonnegativeInt = 0
    model_mae: NonnegativeFloat | None = None
    baseline_mae: NonnegativeFloat | None = None
    relative_mae: NonnegativeFloat | None = None
    relative_mae_reason: (
        Literal["no_matched_cells", "zero_baseline_mae", "ratio_unrepresentable"] | None
    ) = "no_matched_cells"

    @model_validator(mode="after")
    def validate_counts(self) -> PartitionScore:
        if (
            self.planned
            != self.evaluated + self.excluded + self.failed + self.insufficient
        ):
            raise ValueError("partition counts must preserve planned denominator")
        if self.matched_count == 0:
            if (
                self.evaluated
                or any(
                    value is not None
                    for value in (self.model_mae, self.baseline_mae, self.relative_mae)
                )
                or self.relative_mae_reason != "no_matched_cells"
            ):
                raise ValueError("no matched cells requires unavailable scores")
        elif not self.evaluated or self.model_mae is None or self.baseline_mae is None:
            raise ValueError("matched cells require evaluated scores")
        elif self.baseline_mae == 0:
            if (
                self.relative_mae is not None
                or self.relative_mae_reason != "zero_baseline_mae"
            ):
                raise ValueError("zero baseline requires explicit unavailable ratio")
        elif self.relative_mae is None:
            if self.relative_mae_reason != "ratio_unrepresentable" or isfinite(
                self.model_mae / self.baseline_mae
            ):
                raise ValueError(
                    "positive baseline requires a representable ratio or explicit overflow"
                )
        elif self.relative_mae_reason is not None:
            raise ValueError("available ratio cannot have an unavailable reason")
        return self


class BacktestReport(FrozenContract):
    report_id: str = ""
    backtest_id: Identifier
    plan_id: Identifier
    archive_id: Identifier
    source_id: Identifier
    source_revision: Identifier
    captured_at: UTCDatetime
    actuals_snapshot_id: Identifier
    selection: ForecastSelection
    settings: BacktestSettings
    provider_contracts: dict[Identifier, Capabilities]
    frequency: Identifier
    status: Literal["completed", "insufficient_evidence"]
    partitions: tuple[PartitionScore, ...]
    assumptions: tuple[str, ...] = ()
    protocol_version: Literal["backtest-v1"] = "backtest-v1"

    @model_validator(mode="after")
    def validate_report(self) -> BacktestReport:
        if tuple(score.partition for score in self.partitions) != (
            "exploration",
            "selection",
            "final",
        ):
            raise ValueError("report requires ordered partition summaries")
        if (self.status == "completed") != (self.partitions[-1].matched_count > 0):
            raise ValueError("report status requires final matched evidence")
        self._bind_identity("report_id")
        return self


class OriginPage(FrozenContract):
    backtest_id: Identifier
    origins: Annotated[tuple[OriginOutcome, ...], Field(max_length=50)]
    offset: NonnegativeInt
    limit: Annotated[int, Field(ge=1, le=50, strict=True)]
    next_offset: NonnegativeInt | None = None
