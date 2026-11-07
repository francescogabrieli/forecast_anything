"""Strict MCP argument contracts, independent of the optional SDK."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from ..contracts import (
    BacktestSettings,
    Contract,
    ForecastSelection,
    OperationCreateRequest,
    OperationSubmitRequest,
    OperationUpdateRequest,
    QuestionForecastSelection,
    QuestionMeaning,
    QuestionSourceId,
    QuestionTitle,
    SourceSpec,
)

# Unlike contract Identifiers, tool arguments never silently trim a replay key
# or a route identity. The core still validates its existing request contracts.
ToolIdentifier = Annotated[
    str, StringConstraints(min_length=1, pattern=r"^\S(?:.*\S)?$")
]
NonNegative = Annotated[int, Field(ge=0, strict=True)]


class NoArguments(Contract):
    pass


class SourcePageArguments(Contract):
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=100, strict=True)] = 25


class RegisterArguments(Contract):
    spec: SourceSpec


class SourceArguments(Contract):
    source_id: ToolIdentifier


class RefreshArguments(SourceArguments):
    key: ToolIdentifier


class JobArguments(Contract):
    job_id: ToolIdentifier


class CandidateArguments(Contract):
    candidate_id: ToolIdentifier


class ForecastArguments(CandidateArguments):
    primary_node_id: ToolIdentifier | None = None
    snapshot_ids: Annotated[dict[ToolIdentifier, ToolIdentifier], Field(min_length=1)]
    as_of: AwareDatetime
    key: ToolIdentifier


class RunArguments(Contract):
    run_id: ToolIdentifier


class GraphArguments(Contract):
    graph_id: ToolIdentifier
    version: Annotated[int, Field(gt=0, strict=True)]


class SnapshotArguments(Contract):
    snapshot_id: ToolIdentifier


class SnapshotSeriesArguments(SnapshotArguments):
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=5, strict=True)] = 5


class EvaluationArguments(Contract):
    evaluation_id: ToolIdentifier


class SubmitEvaluationArguments(RunArguments):
    actuals_snapshot_id: ToolIdentifier
    key: ToolIdentifier


class ConfiguredForecastArguments(Contract):
    key: ToolIdentifier
    source_id: ToolIdentifier
    snapshot_id: ToolIdentifier
    selection: ForecastSelection


class BacktestArguments(Contract):
    key: ToolIdentifier
    source_id: ToolIdentifier
    selection: ForecastSelection
    settings: BacktestSettings = Field(default_factory=BacktestSettings)
    watch_id: ToolIdentifier | None = None

    @model_validator(mode="after")
    def require_qualification_budget(self):
        if self.watch_id is not None and self.settings.max_origins_per_partition < 30:
            raise ValueError(
                "watch backtests require at least 30 origins per partition"
            )
        return self


class BacktestReadArguments(Contract):
    backtest_id: ToolIdentifier


class BacktestSummaryArguments(BacktestReadArguments):
    watch_id: ToolIdentifier | None = None


class BacktestPresentationArguments(BacktestReadArguments):
    watch_id: ToolIdentifier | None = None


class BacktestOriginsArguments(BacktestReadArguments):
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=50, strict=True)] = 25


class EventsArguments(Contract):
    after: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=1000, strict=True)] = 100


class WatchListArguments(Contract):
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=100, strict=True)] = 25


class WatchArguments(Contract):
    watch_id: ToolIdentifier


class CreateWatchArguments(Contract):
    candidate_id: ToolIdentifier
    next_due_at: AwareDatetime


class UpdateWatchArguments(WatchArguments):
    muted: Annotated[bool, Field(strict=True)] | None = None
    priority: Annotated[int, Field(ge=0, le=5, strict=True)] | None = None

    @model_validator(mode="after")
    def require_control(self):
        controls = self.model_fields_set & {"muted", "priority"}
        if not controls or any(getattr(self, name) is None for name in controls):
            raise ValueError("at least one non-null watch control is required")
        return self


class WatchHistoryArguments(Contract):
    watch_id: ToolIdentifier
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=100, strict=True)] = 25


class WatchChangeArguments(WatchArguments):
    previous_run_id: ToolIdentifier
    current_run_id: ToolIdentifier


class QuestionCreateArguments(Contract):
    key: ToolIdentifier
    title: QuestionTitle
    meaning: QuestionMeaning
    source_ids: Annotated[tuple[QuestionSourceId, ...], Field(max_length=16)] = ()
    selection: QuestionForecastSelection


class QuestionListArguments(Contract):
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=2, strict=True)] = 2


class QuestionIdArguments(Contract):
    question_id: ToolIdentifier


class QuestionPatchArguments(QuestionIdArguments):
    title: QuestionTitle | None = None
    status: Literal["open", "paused", "resolved"] | None = None

    @model_validator(mode="after")
    def require_update(self):
        controls = self.model_fields_set & {"title", "status"}
        if not controls or any(getattr(self, field) is None for field in controls):
            raise ValueError("at least one non-null question field is required")
        return self


class QuestionReviseArguments(Contract):
    question_id: ToolIdentifier
    key: ToolIdentifier
    expected_revision: Annotated[int, Field(ge=1, strict=True)]
    meaning: QuestionMeaning
    source_ids: Annotated[tuple[QuestionSourceId, ...], Field(max_length=16)] = ()
    selection: QuestionForecastSelection


class QuestionRevisionPageArguments(QuestionIdArguments):
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=2, strict=True)] = 2


class QuestionRevisionArguments(QuestionIdArguments):
    revision: Annotated[int, Field(ge=1, strict=True)]


class QuestionReferenceLinkArguments(QuestionIdArguments):
    key: ToolIdentifier
    revision: Annotated[int, Field(ge=1, strict=True)]
    target_type: Literal[
        "candidate", "run", "backtest", "watch", "evaluation", "operation"
    ]
    target_id: ToolIdentifier
    note: Annotated[str, StringConstraints(max_length=800)] = ""


class QuestionReferencePageArguments(QuestionIdArguments):
    revision: Annotated[int, Field(ge=1, strict=True)] | None = None
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=5, strict=True)] = 5


class QuestionPresentationArguments(QuestionIdArguments):
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=3, strict=True)] = 3


class OperationIdArguments(Contract):
    operation_id: ToolIdentifier


class OperationCreateArguments(OperationCreateRequest):
    key: ToolIdentifier
    question_id: ToolIdentifier | None = None


class OperationListArguments(Contract):
    question_id: ToolIdentifier | None = None
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=5, strict=True)] = 5


class OperationUpdateArguments(OperationUpdateRequest):
    operation_id: ToolIdentifier
    key: ToolIdentifier


class OperationSubmitArguments(OperationSubmitRequest):
    operation_id: ToolIdentifier
