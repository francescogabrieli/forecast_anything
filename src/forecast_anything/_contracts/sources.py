"""Source configuration, profiling, observations, and snapshots."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, FiniteFloat, JsonValue, StringConstraints

from .common import Contract, Identifier


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
