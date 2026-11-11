from datetime import UTC, datetime, timedelta

import pytest

from forecast_anything.contracts import (
    DomainError,
    QuestionCreateRequest,
    QuestionTitlePatch,
)
from forecast_anything.store import Ledger

NOW = datetime(2026, 11, 8, tzinfo=UTC)


def _request(key: str, title: str = "Revenue outlook"):
    return QuestionCreateRequest(
        key=key,
        title=title,
        meaning="Forecast monthly revenue",
        source_ids=("sales",),
        selection={"provider": "seasonal_naive", "horizon": 3},
    )


def test_question_mute_and_priority_are_persisted(tmp_path):
    ledger = Ledger(tmp_path / "questions.db", clock=lambda: NOW)
    question = ledger.create_question(_request("controls"))

    updated = ledger.patch_question(
        question.question_id, QuestionTitlePatch(muted=True, priority=1)
    )

    assert (updated.muted, updated.priority) == (True, 1)
    assert (
        ledger.get_question(question.question_id).muted,
        ledger.get_question(question.question_id).priority,
    ) == (True, 1)


def test_inbox_event_identity_includes_type_and_transition_and_is_idempotent(tmp_path):
    ledger = Ledger(tmp_path / "inbox.db", clock=lambda: NOW)
    question = ledger.create_question(_request("events"))
    fields = {
        "question_id": question.question_id,
        "revision": 1,
        "transition_id": "source-snapshot-2",
        "summary": "A new forecast is provisional.",
        "payload": {"state": "provisional"},
    }

    issued = ledger.record_inbox_event(event_kind="forecast_issued", **fields)
    replay = ledger.record_inbox_event(event_kind="forecast_issued", **fields)
    qualified = ledger.record_inbox_event(
        event_kind="evidence_qualified", **(fields | {"summary": "Evidence qualified."})
    )
    next_transition = ledger.record_inbox_event(
        event_kind="forecast_issued",
        **(fields | {"transition_id": "source-snapshot-3"}),
    )

    assert replay == issued
    assert len({issued.event_id, qualified.event_id, next_transition.event_id}) == 3
    assert issued.muted is False


def test_inbox_is_durable_and_pages_by_priority_then_recency(tmp_path):
    now = [NOW]
    ledger = Ledger(tmp_path / "inbox.db", clock=lambda: now[0])
    later = ledger.create_question(_request("later", "Later priority"))
    urgent = ledger.create_question(_request("urgent", "Urgent priority"))
    ledger.patch_question(urgent.question_id, QuestionTitlePatch(priority=0))

    for question, transition in ((later, "t1"), (urgent, "t2")):
        ledger.record_inbox_event(
            question_id=question.question_id,
            revision=1,
            event_kind="forecast_issued",
            transition_id=transition,
            summary=transition,
            payload={},
        )
    now[0] += timedelta(minutes=1)
    ledger.record_inbox_event(
        question_id=urgent.question_id,
        revision=1,
        event_kind="evidence_qualified",
        transition_id="t3",
        summary="t3",
        payload={},
    )

    first = ledger.list_inbox_events(offset=0, limit=1)
    second = ledger.list_inbox_events(offset=1, limit=2)

    assert first.events[0].question_id == urgent.question_id
    assert first.events[0].event_kind == "evidence_qualified"
    assert first.total_count == 3
    assert first.next_offset == 1
    assert [event.question_id for event in second.events] == [
        urgent.question_id,
        later.question_id,
    ]
    assert second.next_offset is None


def test_inbox_rejects_unknown_question_revision(tmp_path):
    ledger = Ledger(tmp_path / "inbox.db", clock=lambda: NOW)
    question = ledger.create_question(_request("events"))

    with pytest.raises(DomainError, match="not_found"):
        ledger.record_inbox_event(
            question_id=question.question_id,
            revision=2,
            event_kind="forecast_issued",
            transition_id="run-1",
            summary="A forecast was issued.",
            payload={},
        )
