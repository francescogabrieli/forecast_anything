"""Persistence for question inbox events and source subscriptions."""

from __future__ import annotations

import json
from hashlib import sha256

from ..contracts import (
    DomainError,
    InboxEvent,
    InboxPage,
    SourceSubscription,
    SourceSubscriptionPage,
)
from .encoding import _json


class InboxStorageMixin:
    def set_source_subscription(
        self, source_id: str, *, active: bool
    ) -> SourceSubscription:
        if (
            not isinstance(source_id, str)
            or not source_id.strip()
            or type(active) is not bool
        ):
            raise DomainError("invalid_source_subscription", {})
        now = self._question_time()
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO source_subscriptions
                (source_id, active, created_at, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    active = excluded.active, updated_at = excluded.updated_at""",
                (source_id, int(active), now, now),
            )
            row = connection.execute(
                "SELECT source_id, active, created_at, updated_at FROM source_subscriptions WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return SourceSubscription(
            source_id=row[0],
            active=bool(row[1]),
            created_at=row[2],
            updated_at=row[3],
        )

    def get_source_subscription(self, source_id: str) -> SourceSubscription:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT source_id, active, created_at, updated_at FROM source_subscriptions WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            raise DomainError("not_found", {"source_id": source_id})
        return SourceSubscription(
            source_id=row[0],
            active=bool(row[1]),
            created_at=row[2],
            updated_at=row[3],
        )

    def list_source_subscriptions(self, *, offset: int = 0, limit: int = 25):
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError("invalid_page", {})
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT source_id, active, created_at, updated_at FROM source_subscriptions ORDER BY source_id LIMIT ? OFFSET ?",
                (limit + 1, offset),
            ).fetchall()
        items = tuple(
            SourceSubscription(
                source_id=row[0],
                active=bool(row[1]),
                created_at=row[2],
                updated_at=row[3],
            )
            for row in rows[:limit]
        )
        return SourceSubscriptionPage(
            subscriptions=items,
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def record_inbox_event(
        self,
        *,
        question_id: str,
        revision: int,
        event_kind: str,
        transition_id: str,
        summary: str,
        payload: dict,
        run_id: str | None = None,
        decision_id: str | None = None,
        watch_id: str | None = None,
        lease_guard=None,
    ) -> InboxEvent:
        """Persist one deterministic question transition without rewriting history."""
        if not isinstance(payload, dict):
            raise DomainError("invalid_inbox_event", {"field": "payload"})
        payload_content = _json(payload)
        if len(payload_content.encode("utf-8")) > 4096:
            raise DomainError("inbox_payload_too_large", {"max_bytes": 4096})
        if not isinstance(summary, str) or len(summary.encode("utf-8")) > 1000:
            raise DomainError("invalid_inbox_summary", {})
        event_id = sha256(
            _json(
                [
                    question_id,
                    revision,
                    event_kind,
                    transition_id,
                    run_id,
                    decision_id,
                ]
            ).encode("utf-8")
        ).hexdigest()
        occurred_at = self._question_time()
        with self._transaction(lease_guard) as connection:
            question = connection.execute(
                "SELECT muted, priority FROM questions WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if (
                question is None
                or connection.execute(
                    "SELECT 1 FROM question_revisions WHERE question_id = ? AND revision = ?",
                    (question_id, revision),
                ).fetchone()
                is None
            ):
                raise DomainError(
                    "not_found", {"question_id": question_id, "revision": revision}
                )
            event = InboxEvent(
                event_id=event_id,
                question_id=question_id,
                revision=revision,
                event_kind=event_kind,
                transition_id=transition_id,
                run_id=run_id,
                decision_id=decision_id,
                watch_id=watch_id,
                occurred_at=occurred_at,
                muted=bool(question[0]),
                summary=summary,
                payload=payload,
            )
            existing = connection.execute(
                """SELECT question_id, revision, event_kind, transition_id, run_id,
                    decision_id, watch_id, occurred_at, muted, summary, payload
                FROM inbox_events WHERE event_id = ?""",
                (event_id,),
            ).fetchone()
            if existing is not None:
                previous = InboxEvent(
                    event_id=event_id,
                    question_id=existing[0],
                    revision=existing[1],
                    event_kind=existing[2],
                    transition_id=existing[3],
                    run_id=existing[4],
                    decision_id=existing[5],
                    watch_id=existing[6],
                    occurred_at=existing[7],
                    muted=bool(existing[8]),
                    summary=existing[9],
                    payload=json.loads(existing[10]),
                )
                same_transition = previous.model_dump(
                    mode="json", exclude={"occurred_at", "muted"}
                ) == event.model_dump(mode="json", exclude={"occurred_at", "muted"})
                if not same_transition:
                    raise DomainError("immutable_identity", {"event_id": event_id})
                return previous
            connection.execute(
                """INSERT INTO inbox_events
                (event_id, question_id, revision, event_kind, transition_id, run_id,
                 decision_id, watch_id, occurred_at, muted, summary, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.question_id,
                    event.revision,
                    event.event_kind,
                    event.transition_id,
                    event.run_id,
                    event.decision_id,
                    event.watch_id,
                    event.occurred_at.isoformat(),
                    int(event.muted),
                    event.summary,
                    payload_content,
                ),
            )
            self._enqueue_event_webhooks(connection, event, priority=question[1])
            return event

    def list_inbox_events(
        self,
        *,
        question_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> InboxPage:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError("invalid_page", {})
        if question_id is not None:
            self.get_question(question_id)
        where = " WHERE e.question_id = ?" if question_id is not None else ""
        params = (question_id,) if question_id is not None else ()
        with self._connection() as connection:
            total_count = connection.execute(
                "SELECT count(*) FROM inbox_events e" + where, params
            ).fetchone()[0]
            rows = connection.execute(
                """SELECT e.event_id, e.question_id, e.revision, e.event_kind,
                    e.transition_id, e.run_id, e.decision_id, e.watch_id,
                    e.occurred_at, e.muted, e.summary, e.payload,
                    COALESCE((SELECT json_group_array(state) FROM (
                        SELECT d.state FROM webhook_outbox d
                        WHERE d.event_id = e.event_id
                        ORDER BY d.subscription_id
                    )), '[]')
                FROM inbox_events e JOIN questions q ON q.question_id = e.question_id"""
                + where
                + " ORDER BY q.priority ASC, e.occurred_at DESC, e.event_id ASC LIMIT ? OFFSET ?",
                (*params, limit + 1, offset),
            ).fetchall()
        events = tuple(
            InboxEvent(
                event_id=row[0],
                question_id=row[1],
                revision=row[2],
                event_kind=row[3],
                transition_id=row[4],
                run_id=row[5],
                decision_id=row[6],
                watch_id=row[7],
                occurred_at=row[8],
                muted=bool(row[9]),
                summary=row[10],
                payload=json.loads(row[11]),
                delivery_states=tuple(json.loads(row[12])),
            )
            for row in rows[:limit]
        )
        return InboxPage(
            events=events,
            next_offset=offset + limit if len(rows) > limit else None,
            total_count=total_count,
        )
