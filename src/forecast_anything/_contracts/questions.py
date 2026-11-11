"""Persistent questions, their references, and guided operations."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from .common import Contract, Identifier, OpaqueDictionary
from .forecasts import ForecastSelection, JobRequest


class QuestionForecastSelection(ForecastSelection):
    @model_validator(mode="after")
    def validate_bounded_options(self) -> QuestionForecastSelection:
        import json

        if len(json.dumps(self.options, ensure_ascii=False).encode("utf-8")) > 1024:
            raise ValueError("question selection options exceed 1024 bytes")
        return self


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
    muted: bool | None = None
    priority: Annotated[int, Field(ge=0, le=5, strict=True)] | None = None

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
    muted: bool = False
    priority: Annotated[int, Field(ge=0, le=5, strict=True)] = 3
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
