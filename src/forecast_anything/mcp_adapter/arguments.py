"""Strict MCP argument contracts, independent of the optional SDK."""

from typing import Annotated

from pydantic import AwareDatetime, Field, StringConstraints

from ..contracts import BacktestSettings, Contract, ForecastSelection, SourceSpec

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


class BacktestReadArguments(Contract):
    backtest_id: ToolIdentifier


class BacktestOriginsArguments(BacktestReadArguments):
    offset: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=50, strict=True)] = 25


class EventsArguments(Contract):
    after: NonNegative = 0
    limit: Annotated[int, Field(ge=1, le=1000, strict=True)] = 100
