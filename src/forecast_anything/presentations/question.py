"""Question timeline and inbox projections."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..contracts import (
    Contract,
    InboxEvent,
    QuestionReference,
    QuestionView,
)


class QuestionPresentationReference(Contract):
    reference: QuestionReference
    applies_to_current_revision: bool


class QuestionPresentation(Contract):
    schema_version: Literal["question-presentation-v1"] = "question-presentation-v1"
    visual_destination: Literal["question_timeline"] = "question_timeline"
    question: QuestionView
    references: Annotated[
        tuple[QuestionPresentationReference, ...], Field(max_length=3)
    ]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None
    inbox_events: Annotated[tuple[InboxEvent, ...], Field(max_length=10)]
    inbox_total_count: Annotated[int, Field(ge=0, strict=True)]


def present_question(
    question: QuestionView,
    references: tuple[QuestionReference, ...],
    *,
    next_offset: int | None,
    inbox_events: tuple[InboxEvent, ...] = (),
    inbox_total_count: int = 0,
) -> QuestionPresentation:
    return QuestionPresentation(
        question=question,
        references=tuple(
            QuestionPresentationReference(
                reference=reference,
                applies_to_current_revision=(
                    reference.revision == question.current_revision
                ),
            )
            for reference in references
        ),
        next_offset=next_offset,
        inbox_events=inbox_events,
        inbox_total_count=inbox_total_count,
    )
