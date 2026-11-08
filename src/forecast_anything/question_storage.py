"""Transactional persistence for stable questions and immutable semantic history."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import uuid4

from .contracts import (
    DomainError,
    InboxEvent,
    InboxPage,
    OperationCreateRequest,
    OperationPage,
    OperationSubmitRequest,
    OperationUpdateRequest,
    OperationView,
    QuestionCreateRequest,
    QuestionPage,
    QuestionReference,
    QuestionReferencePage,
    QuestionReferenceRequest,
    QuestionRevision,
    QuestionRevisionPage,
    QuestionRevisionRequest,
    QuestionTitlePatch,
    QuestionView,
    SourceSubscription,
    SourceSubscriptionPage,
    WebhookDelivery,
    WebhookDeliveryPage,
    WebhookSubscription,
    WebhookSubscriptionPage,
    WebhookSubscriptionRequest,
)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(namespace: str, *parts: str) -> str:
    return sha256("/".join((namespace, *parts)).encode("utf-8")).hexdigest()


def _hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def _validate_webhook_target(target_url: str) -> str:
    if not isinstance(target_url, str) or len(target_url) > 2048:
        raise DomainError("invalid_webhook_target", {})
    try:
        parsed = urlsplit(target_url)
        port = parsed.port
    except ValueError as error:
        raise DomainError("invalid_webhook_target", {}) from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise DomainError("invalid_webhook_target", {})
    return target_url


class QuestionStorageMixin:
    """Methods expect the short-lived connection/transaction helpers on Ledger."""

    def _question_time(self) -> str:
        now = self.clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise DomainError("invalid_question_time", {})
        return now.astimezone(timezone.utc).isoformat()

    def _question_view(self, connection, question_id: str) -> QuestionView:
        row = connection.execute(
            """SELECT title, status, muted, priority, current_revision, created_at, updated_at
            FROM questions WHERE question_id = ?""",
            (question_id,),
        ).fetchone()
        if row is None:
            raise DomainError("not_found", {"question_id": question_id})
        title, status, muted, priority, current_revision, created_at, updated_at = row
        revision_row = connection.execute(
            "SELECT content FROM question_revisions WHERE question_id = ? AND revision = ?",
            (question_id, current_revision),
        ).fetchone()
        revision_count = connection.execute(
            "SELECT count(*) FROM question_revisions WHERE question_id = ?",
            (question_id,),
        ).fetchone()[0]
        reference_count = connection.execute(
            "SELECT count(*) FROM question_references WHERE question_id = ?",
            (question_id,),
        ).fetchone()[0]
        revision = QuestionRevision.model_validate_json(revision_row[0])
        return QuestionView(
            question_id=question_id,
            title=title,
            status=status,
            muted=bool(muted),
            priority=priority,
            current_revision=current_revision,
            revision=revision,
            revision_count=revision_count,
            reference_count=reference_count,
            created_at=created_at,
            updated_at=updated_at,
        )

    def create_question(self, request: QuestionCreateRequest) -> QuestionView:
        request = QuestionCreateRequest.model_validate(request.model_dump())
        encoded = _json(request.model_dump(mode="json"))
        request_hash = _hash(encoded)
        question_id = _identity("question", request.key)
        now = self._question_time()
        revision = QuestionRevision(
            question_id=question_id,
            revision=1,
            meaning=request.meaning,
            source_ids=request.source_ids,
            selection=request.selection,
            created_at=now,
        )
        revision_content = _json(revision.model_dump(mode="json"))
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT question_id, request_hash FROM questions WHERE create_key = ?",
                (request.key,),
            ).fetchone()
            if existing is not None:
                if existing[1] != request_hash:
                    raise DomainError("idempotency_conflict", {"key": request.key})
                return self._question_view(connection, existing[0])
            connection.execute(
                """INSERT INTO questions
                (question_id, create_key, request_hash, title, status, current_revision, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', 1, ?, ?)""",
                (question_id, request.key, request_hash, request.title, now, now),
            )
            connection.execute(
                """INSERT INTO question_revisions
                (question_id, revision, idempotency_key, request_hash, content, created_at)
                VALUES (?, 1, ?, ?, ?, ?)""",
                (
                    question_id,
                    f"create:{request.key}",
                    request_hash,
                    revision_content,
                    now,
                ),
            )
            return self._question_view(connection, question_id)

    def get_question(self, question_id: str) -> QuestionView:
        with self._connection() as connection:
            return self._question_view(connection, question_id)

    def list_questions(self, *, offset: int = 0, limit: int = 25) -> QuestionPage:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError("invalid_page", {})
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT question_id FROM questions ORDER BY question_id LIMIT ? OFFSET ?",
                (limit + 1, offset),
            ).fetchall()
            questions = tuple(
                self._question_view(connection, row[0]) for row in rows[:limit]
            )
        return QuestionPage(
            questions=questions,
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def patch_question(
        self, question_id: str, patch: QuestionTitlePatch
    ) -> QuestionView:
        patch = QuestionTitlePatch.model_validate(patch.model_dump(exclude_unset=True))
        now = self._question_time()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT title, status, muted, priority FROM questions WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if row is None:
                raise DomainError("not_found", {"question_id": question_id})
            title = patch.title if "title" in patch.model_fields_set else row[0]
            status = patch.status if "status" in patch.model_fields_set else row[1]
            muted = patch.muted if "muted" in patch.model_fields_set else bool(row[2])
            priority = (
                patch.priority if "priority" in patch.model_fields_set else row[3]
            )
            connection.execute(
                "UPDATE questions SET title = ?, status = ?, muted = ?, priority = ?, updated_at = ? WHERE question_id = ?",
                (title, status, int(muted), priority, now, question_id),
            )
            if muted:
                connection.execute(
                    """UPDATE webhook_outbox
                    SET state = 'delivery_suppressed_muted', updated_at = ?
                    WHERE state IN ('pending', 'delivering')
                        AND event_id IN (
                            SELECT event_id FROM inbox_events WHERE question_id = ?
                        )""",
                    (now, question_id),
                )
            return self._question_view(connection, question_id)

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

    def question_links_for_watch(self, watch_id: str):
        """Return current references to a watch with per-question controls."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT q.question_id, q.current_revision, q.status, q.muted,
                    q.priority, r.content
                FROM questions q JOIN question_references r
                    ON r.question_id = q.question_id
                WHERE r.revision = q.current_revision
                ORDER BY q.question_id"""
            ).fetchall()
        links = {}
        for row in rows:
            reference = json.loads(row[5])
            if (
                reference.get("target_type") == "watch"
                and reference.get("target_id") == watch_id
            ):
                links[row[0]] = {
                    "question_id": row[0],
                    "revision": row[1],
                    "status": row[2],
                    "muted": bool(row[3]),
                    "priority": row[4],
                }
        return tuple(links[key] for key in sorted(links))

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

    def _enqueue_event_webhooks(self, connection, event: InboxEvent, *, priority: int):
        from .jobs import JobQueue

        rows = connection.execute(
            "SELECT subscription_id FROM webhook_subscriptions WHERE active = 1 ORDER BY subscription_id"
        ).fetchall()
        now = event.occurred_at.isoformat()
        for (subscription_id,) in rows:
            delivery_id = sha256(
                f"webhook/{subscription_id}/{event.event_id}".encode("utf-8")
            ).hexdigest()
            connection.execute(
                """INSERT OR IGNORE INTO webhook_outbox
                (delivery_id, subscription_id, event_id, state, attempts, max_attempts,
                 next_attempt_at, last_error, created_at, updated_at)
                VALUES (?, ?, ?, 'pending', 0, 3, ?, NULL, ?, ?)""",
                (delivery_id, subscription_id, event.event_id, now, now, now),
            )
            JobQueue(self).enqueue(
                f"webhook-delivery/{delivery_id}",
                {
                    "kind": "webhook_delivery",
                    "delivery_id": delivery_id,
                    "priority": priority,
                },
                connection=connection,
            )

    def create_webhook_subscription(
        self, request: WebhookSubscriptionRequest
    ) -> WebhookSubscription:
        request = WebhookSubscriptionRequest.model_validate(request.model_dump())
        target_url = _validate_webhook_target(request.target_url)
        if request.secret is not None and (
            not request.secret or len(request.secret.encode("utf-8")) > 1024
        ):
            raise DomainError("invalid_webhook_secret", {})
        subscription_id = uuid4().hex
        now = self._question_time()
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO webhook_subscriptions VALUES (?, ?, ?, ?, ?)",
                (
                    subscription_id,
                    target_url,
                    request.secret,
                    int(request.active),
                    now,
                ),
            )
        return WebhookSubscription(
            subscription_id=subscription_id,
            target_url=target_url,
            active=request.active,
            created_at=now,
        )

    def set_webhook_subscription_active(
        self, subscription_id: str, *, active: bool
    ) -> WebhookSubscription:
        if type(active) is not bool:
            raise DomainError("invalid_webhook_subscription", {})
        with self._transaction() as connection:
            cursor = connection.execute(
                "UPDATE webhook_subscriptions SET active = ? WHERE subscription_id = ?",
                (int(active), subscription_id),
            )
            if not cursor.rowcount:
                raise DomainError("not_found", {"subscription_id": subscription_id})
            row = connection.execute(
                "SELECT subscription_id, target_url, active, created_at FROM webhook_subscriptions WHERE subscription_id = ?",
                (subscription_id,),
            ).fetchone()
        return WebhookSubscription(
            subscription_id=row[0],
            target_url=row[1],
            active=bool(row[2]),
            created_at=row[3],
        )

    def list_webhook_subscriptions(
        self, *, offset: int = 0, limit: int = 25
    ) -> WebhookSubscriptionPage:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError("invalid_page", {})
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT subscription_id, target_url, active, created_at FROM webhook_subscriptions ORDER BY subscription_id LIMIT ? OFFSET ?",
                (limit + 1, offset),
            ).fetchall()
        return WebhookSubscriptionPage(
            subscriptions=tuple(
                WebhookSubscription(
                    subscription_id=row[0],
                    target_url=row[1],
                    active=bool(row[2]),
                    created_at=row[3],
                )
                for row in rows[:limit]
            ),
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def list_webhook_deliveries(
        self, subscription_id: str, *, offset: int = 0, limit: int = 25
    ) -> WebhookDeliveryPage:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError("invalid_page", {})
        with self._connection() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM webhook_subscriptions WHERE subscription_id = ?",
                    (subscription_id,),
                ).fetchone()
                is None
            ):
                raise DomainError("not_found", {"subscription_id": subscription_id})
            rows = connection.execute(
                """SELECT delivery_id, subscription_id, event_id, state, attempts,
                    max_attempts, next_attempt_at, last_error, created_at, updated_at
                FROM webhook_outbox WHERE subscription_id = ?
                ORDER BY created_at DESC, delivery_id LIMIT ? OFFSET ?""",
                (subscription_id, limit + 1, offset),
            ).fetchall()
        return WebhookDeliveryPage(
            deliveries=tuple(
                WebhookDelivery(
                    delivery_id=row[0],
                    subscription_id=row[1],
                    event_id=row[2],
                    state=row[3],
                    attempts=row[4],
                    max_attempts=row[5],
                    next_attempt_at=row[6],
                    last_error=row[7],
                    created_at=row[8],
                    updated_at=row[9],
                )
                for row in rows[:limit]
            ),
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def begin_webhook_delivery(
        self, delivery_id: str, now: datetime, *, lease_guard=None
    ):
        stamp = now.astimezone(timezone.utc).isoformat()
        with self._transaction(lease_guard) as connection:
            row = connection.execute(
                """SELECT d.state, d.attempts, d.max_attempts, d.next_attempt_at,
                    s.subscription_id, s.target_url, s.secret, s.active,
                    e.event_id, e.question_id, e.revision, e.event_kind,
                    e.transition_id, e.run_id, e.occurred_at, e.muted, q.muted
                FROM webhook_outbox d
                JOIN webhook_subscriptions s ON s.subscription_id = d.subscription_id
                JOIN inbox_events e ON e.event_id = d.event_id
                JOIN questions q ON q.question_id = e.question_id
                WHERE d.delivery_id = ?""",
                (delivery_id,),
            ).fetchone()
            if row is None:
                raise DomainError("not_found", {"delivery_id": delivery_id})
            state, attempts, maximum, next_attempt = row[:4]
            if state in {"delivered", "delivery_failed", "delivery_suppressed_muted"}:
                return {"state": state, "attempts": attempts}
            if row[15] or row[16]:
                connection.execute(
                    "UPDATE webhook_outbox SET state = 'delivery_suppressed_muted', updated_at = ? WHERE delivery_id = ?",
                    (stamp, delivery_id),
                )
                return {"state": "delivery_suppressed_muted", "attempts": attempts}
            if not row[7]:
                connection.execute(
                    "UPDATE webhook_outbox SET state = 'delivery_failed', last_error = 'subscription_inactive', updated_at = ? WHERE delivery_id = ?",
                    (stamp, delivery_id),
                )
                return {"state": "delivery_failed", "attempts": attempts}
            if attempts >= maximum:
                connection.execute(
                    "UPDATE webhook_outbox SET state = 'delivery_failed', last_error = 'attempt_limit', updated_at = ? WHERE delivery_id = ?",
                    (stamp, delivery_id),
                )
                return {"state": "delivery_failed", "attempts": attempts}
            if datetime.fromisoformat(next_attempt) > now:
                return {
                    "state": "pending",
                    "attempts": attempts,
                    "next_attempt_at": next_attempt,
                }
            attempts += 1
            connection.execute(
                "UPDATE webhook_outbox SET state = 'delivering', attempts = ?, updated_at = ? WHERE delivery_id = ?",
                (attempts, stamp, delivery_id),
            )
            body = {
                "event_id": row[8],
                "question_id": row[9],
                "revision": row[10],
                "event_kind": row[11],
                "transition_id": row[12],
                "run_id": row[13],
                "occurred_at": row[14],
            }
            return {
                "state": "delivering",
                "attempts": attempts,
                "max_attempts": maximum,
                "target_url": row[5],
                "secret": row[6],
                "body": body,
            }

    def finish_webhook_delivery(
        self,
        delivery_id: str,
        now: datetime,
        *,
        error_code: str | None,
        lease_guard=None,
    ) -> WebhookDelivery:
        stamp = now.astimezone(timezone.utc).isoformat()
        with self._transaction(lease_guard) as connection:
            row = connection.execute(
                "SELECT attempts, max_attempts, state FROM webhook_outbox WHERE delivery_id = ?",
                (delivery_id,),
            ).fetchone()
            if row is None:
                raise DomainError("not_found", {"delivery_id": delivery_id})
            attempts, maximum, state = row
            if state in {"delivered", "delivery_failed", "delivery_suppressed_muted"}:
                pass
            elif error_code is None:
                connection.execute(
                    "UPDATE webhook_outbox SET state = 'delivered', last_error = NULL, updated_at = ? WHERE delivery_id = ?",
                    (stamp, delivery_id),
                )
            elif attempts >= maximum:
                connection.execute(
                    "UPDATE webhook_outbox SET state = 'delivery_failed', last_error = ?, updated_at = ? WHERE delivery_id = ?",
                    (error_code, stamp, delivery_id),
                )
            else:
                delay = 30 if attempts == 1 else 120
                due = (
                    (now + timedelta(seconds=delay))
                    .astimezone(timezone.utc)
                    .isoformat()
                )
                connection.execute(
                    "UPDATE webhook_outbox SET state = 'pending', next_attempt_at = ?, last_error = ?, updated_at = ? WHERE delivery_id = ?",
                    (due, error_code, stamp, delivery_id),
                )
            result = connection.execute(
                """SELECT delivery_id, subscription_id, event_id, state, attempts,
                    max_attempts, next_attempt_at, last_error, created_at, updated_at
                FROM webhook_outbox WHERE delivery_id = ?""",
                (delivery_id,),
            ).fetchone()
        return WebhookDelivery(
            delivery_id=result[0],
            subscription_id=result[1],
            event_id=result[2],
            state=result[3],
            attempts=result[4],
            max_attempts=result[5],
            next_attempt_at=result[6],
            last_error=result[7],
            created_at=result[8],
            updated_at=result[9],
        )

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

    def revise_question(
        self, question_id: str, request: QuestionRevisionRequest
    ) -> QuestionView:
        request = QuestionRevisionRequest.model_validate(request.model_dump())
        revision_body = request.model_dump(mode="json", exclude={"key"})
        encoded = _json(revision_body)
        request_hash = _hash(encoded)
        now = self._question_time()
        with self._transaction() as connection:
            existing = connection.execute(
                """SELECT request_hash FROM question_revisions
                WHERE question_id = ? AND idempotency_key = ?""",
                (question_id, request.key),
            ).fetchone()
            if existing is not None:
                if existing[0] != request_hash:
                    raise DomainError("idempotency_conflict", {"key": request.key})
                return self._question_view(connection, question_id)
            row = connection.execute(
                "SELECT current_revision FROM questions WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if row is None:
                raise DomainError("not_found", {"question_id": question_id})
            if row[0] != request.expected_revision:
                raise DomainError(
                    "stale_question_revision",
                    {
                        "expected_revision": request.expected_revision,
                        "current_revision": row[0],
                    },
                )
            revision_number = row[0] + 1
            revision = QuestionRevision(
                question_id=question_id,
                revision=revision_number,
                meaning=request.meaning,
                source_ids=request.source_ids,
                selection=request.selection,
                created_at=now,
            )
            connection.execute(
                """INSERT INTO question_revisions
                (question_id, revision, idempotency_key, request_hash, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    question_id,
                    revision_number,
                    request.key,
                    request_hash,
                    _json(revision.model_dump(mode="json")),
                    now,
                ),
            )
            connection.execute(
                "UPDATE questions SET current_revision = ?, updated_at = ? WHERE question_id = ?",
                (revision_number, now, question_id),
            )
            return self._question_view(connection, question_id)

    def get_question_revision(
        self, question_id: str, revision: int
    ) -> QuestionRevision:
        if type(revision) is not int or revision < 1:
            raise DomainError("invalid_question_revision", {})
        with self._connection() as connection:
            row = connection.execute(
                "SELECT content FROM question_revisions WHERE question_id = ? AND revision = ?",
                (question_id, revision),
            ).fetchone()
        if row is None:
            raise DomainError(
                "not_found", {"question_id": question_id, "revision": revision}
            )
        return QuestionRevision.model_validate_json(row[0])

    def list_question_revisions(
        self, question_id: str, *, offset: int = 0, limit: int = 25
    ) -> QuestionRevisionPage:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError("invalid_page", {})
        self.get_question(question_id)
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT content FROM question_revisions WHERE question_id = ?
                ORDER BY revision LIMIT ? OFFSET ?""",
                (question_id, limit + 1, offset),
            ).fetchall()
        return QuestionRevisionPage(
            revisions=tuple(
                QuestionRevision.model_validate_json(row[0]) for row in rows[:limit]
            ),
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def link_question_reference(
        self,
        question_id: str,
        request: QuestionReferenceRequest,
        *,
        lease_guard=None,
    ) -> QuestionReference:
        request = QuestionReferenceRequest.model_validate(request.model_dump())
        body = request.model_dump(mode="json", exclude={"key"})
        encoded = _json(body)
        request_hash = _hash(encoded)
        reference_id = _identity(
            "question-reference", question_id, str(request.revision), request.key
        )
        now = self._question_time()
        with self._transaction(lease_guard) as connection:
            existing = connection.execute(
                """SELECT request_hash, content FROM question_references
                WHERE question_id = ? AND revision = ? AND idempotency_key = ?""",
                (question_id, request.revision, request.key),
            ).fetchone()
            if existing is not None:
                if existing[0] != request_hash:
                    raise DomainError("idempotency_conflict", {"key": request.key})
                return QuestionReference.model_validate_json(existing[1])
            if (
                connection.execute(
                    "SELECT 1 FROM question_revisions WHERE question_id = ? AND revision = ?",
                    (question_id, request.revision),
                ).fetchone()
                is None
            ):
                raise DomainError(
                    "not_found",
                    {"question_id": question_id, "revision": request.revision},
                )
            reference = QuestionReference(
                reference_id=reference_id,
                question_id=question_id,
                revision=request.revision,
                target_type=request.target_type,
                target_id=request.target_id,
                note=request.note,
                created_at=now,
            )
            content = _json(reference.model_dump(mode="json"))
            connection.execute(
                """INSERT INTO question_references
                (reference_id, question_id, revision, idempotency_key, request_hash, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    reference_id,
                    question_id,
                    request.revision,
                    request.key,
                    request_hash,
                    content,
                    now,
                ),
            )
            return reference

    def list_question_references(
        self,
        question_id: str,
        *,
        revision: int | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> QuestionReferencePage:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError("invalid_page", {})
        self.get_question(question_id)
        if revision is not None:
            self.get_question_revision(question_id, revision)
        with self._connection() as connection:
            if revision is None:
                rows = connection.execute(
                    """SELECT content FROM question_references WHERE question_id = ?
                    ORDER BY revision, reference_id LIMIT ? OFFSET ?""",
                    (question_id, limit + 1, offset),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT content FROM question_references WHERE question_id = ? AND revision = ?
                    ORDER BY reference_id LIMIT ? OFFSET ?""",
                    (question_id, revision, limit + 1, offset),
                ).fetchall()
        return QuestionReferencePage(
            references=tuple(
                QuestionReference.model_validate_json(row[0]) for row in rows[:limit]
            ),
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def _operation_view(self, connection, operation_id: str) -> OperationView:
        row = connection.execute(
            """SELECT question_id, question_revision, version, phase, state,
            missing_data, request_kind, request_digest, source_ids,
            expected_job_id, created_at, updated_at
            FROM operations WHERE operation_id = ?""",
            (operation_id,),
        ).fetchone()
        if row is None:
            raise DomainError("not_found", {"operation_id": operation_id})
        (
            question_id,
            question_revision,
            version,
            phase,
            state,
            missing_data,
            request_kind,
            request_digest,
            source_ids,
            expected_job_id,
            created_at,
            updated_at,
        ) = row
        return OperationView(
            operation_id=operation_id,
            question_id=question_id,
            question_revision=question_revision,
            version=version,
            phase=phase,
            state=state,
            missing_data=tuple(json.loads(missing_data)),
            request_kind=request_kind,
            request_digest=request_digest,
            source_ids=tuple(json.loads(source_ids)),
            job_id=expected_job_id,
            job_state=None,
            job_error=None,
            created_at=created_at,
            updated_at=updated_at,
        )

    def create_operation(self, request: OperationCreateRequest) -> OperationView:
        request = OperationCreateRequest.model_validate(request.model_dump())
        encoded = _json(request.model_dump(mode="json"))
        request_hash = _hash(encoded)
        operation_id = _identity("operation", request.key)
        now = self._question_time()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT operation_id, request_hash FROM operations WHERE create_key = ?",
                (request.key,),
            ).fetchone()
            if existing is not None:
                if existing[1] != request_hash:
                    raise DomainError("idempotency_conflict", {"key": request.key})
                return self._operation_view(connection, existing[0])
            if (
                request.question_id is not None
                and connection.execute(
                    """SELECT 1 FROM question_revisions
                WHERE question_id = ? AND revision = ?""",
                    (request.question_id, request.question_revision),
                ).fetchone()
                is None
            ):
                raise DomainError(
                    "not_found",
                    {
                        "question_id": request.question_id,
                        "revision": request.question_revision,
                    },
                )
            connection.execute(
                """INSERT INTO operations
                (operation_id, create_key, request_hash, question_id, question_revision,
                 version, phase, state, missing_data, request_content, request_digest,
                 request_kind, source_ids, expected_job_id, candidate_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, 'open', ?, NULL, NULL, NULL, '[]', NULL, NULL, ?, ?)""",
                (
                    operation_id,
                    request.key,
                    request_hash,
                    request.question_id,
                    request.question_revision,
                    request.phase,
                    _json(list(request.missing_data)),
                    now,
                    now,
                ),
            )
            return self._operation_view(connection, operation_id)

    def get_operation(self, operation_id: str) -> OperationView:
        with self._connection() as connection:
            return self._operation_view(connection, operation_id)

    def list_operations(
        self,
        *,
        question_id: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> OperationPage:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError("invalid_page", {})
        with self._connection() as connection:
            if question_id is None:
                rows = connection.execute(
                    "SELECT operation_id FROM operations ORDER BY operation_id LIMIT ? OFFSET ?",
                    (limit + 1, offset),
                ).fetchall()
            else:
                self._question_view(connection, question_id)
                rows = connection.execute(
                    """SELECT operation_id FROM operations WHERE question_id = ?
                    ORDER BY operation_id LIMIT ? OFFSET ?""",
                    (question_id, limit + 1, offset),
                ).fetchall()
            operations = tuple(
                self._operation_view(connection, row[0]) for row in rows[:limit]
            )
        return OperationPage(
            operations=operations,
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def update_operation(
        self, operation_id: str, request: OperationUpdateRequest
    ) -> OperationView:
        request = OperationUpdateRequest.model_validate(request.model_dump())
        request_hash = _hash(_json(request.model_dump(mode="json", exclude={"key"})))
        now = self._question_time()
        with self._transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM operations WHERE operation_id = ?", (operation_id,)
                ).fetchone()
                is None
            ):
                raise DomainError("not_found", {"operation_id": operation_id})
            prior = connection.execute(
                """SELECT request_hash FROM operation_mutations
                WHERE operation_id = ? AND idempotency_key = ?""",
                (operation_id, request.key),
            ).fetchone()
            if prior is not None:
                if prior[0] != request_hash:
                    raise DomainError("idempotency_conflict", {"key": request.key})
                return self._operation_view(connection, operation_id)
            row = connection.execute(
                "SELECT version, state FROM operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row[1] != "open":
                raise DomainError("operation_already_submitted", {})
            if row[0] != request.expected_version:
                raise DomainError(
                    "stale_operation_version",
                    {
                        "expected_version": request.expected_version,
                        "current_version": row[0],
                    },
                )
            version = row[0] + 1
            connection.execute(
                """UPDATE operations SET phase = ?, missing_data = ?,
                version = ?, updated_at = ? WHERE operation_id = ?""",
                (
                    request.phase,
                    _json(list(request.missing_data)),
                    version,
                    now,
                    operation_id,
                ),
            )
            connection.execute(
                "INSERT INTO operation_mutations VALUES (?, ?, ?, ?)",
                (operation_id, request.key, request_hash, version),
            )
            return self._operation_view(connection, operation_id)

    def reserve_operation_submission(
        self,
        operation_id: str,
        request: OperationSubmitRequest,
        *,
        source_ids: tuple[str, ...],
    ) -> OperationView:
        request = OperationSubmitRequest.model_validate(request.model_dump())
        if request.request.kind not in {
            "run",
            "configured_run",
            "backtest",
            "evaluation",
        }:
            raise DomainError("invalid_operation_job", {})
        if len(set(source_ids)) > 16:
            raise DomainError("too_many_operation_sources", {})
        content = _json(request.model_dump(mode="json"))
        digest = _hash(_json(request.request.model_dump(mode="json")))
        logical_key = f"operation/{operation_id}"
        expected_job_id = sha256(logical_key.encode("utf-8")).hexdigest()
        now = self._question_time()
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT state, phase, missing_data, version, request_content,
                request_digest, request_kind, expected_job_id
                FROM operations WHERE operation_id = ?""",
                (operation_id,),
            ).fetchone()
            if row is None:
                raise DomainError("not_found", {"operation_id": operation_id})
            if row[4] is not None:
                if row[4] != content:
                    raise DomainError(
                        "idempotency_conflict", {"operation_id": operation_id}
                    )
                return self._operation_view(connection, operation_id)
            state, phase, missing, version = row[:4]
            if state != "open" or phase != "ready" or json.loads(missing):
                raise DomainError("operation_not_ready", {})
            if version != request.expected_version:
                raise DomainError(
                    "stale_operation_version",
                    {
                        "expected_version": request.expected_version,
                        "current_version": version,
                    },
                )
            connection.execute(
                """UPDATE operations SET state = 'reserved', version = ?,
                request_content = ?, request_digest = ?, request_kind = ?,
                source_ids = ?, expected_job_id = ?, candidate_id = ?, updated_at = ?
                WHERE operation_id = ?""",
                (
                    version + 1,
                    content,
                    digest,
                    request.request.kind,
                    _json(sorted(set(source_ids))),
                    expected_job_id,
                    request.candidate_id,
                    now,
                    operation_id,
                ),
            )
            return self._operation_view(connection, operation_id)

    def operation_submission(
        self, operation_id: str
    ) -> tuple[OperationView, OperationSubmitRequest]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT request_content FROM operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            view = self._operation_view(connection, operation_id)
        if row is None or row[0] is None:
            raise DomainError("operation_not_submitted", {})
        return view, OperationSubmitRequest.model_validate_json(row[0])

    def mark_operation_enqueued(self, operation_id: str, job_id: str) -> OperationView:
        now = self._question_time()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT expected_job_id, state FROM operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is None:
                raise DomainError("not_found", {"operation_id": operation_id})
            if row[0] != job_id:
                raise DomainError("operation_job_mismatch", {})
            if row[1] == "reserved":
                connection.execute(
                    "UPDATE operations SET state = 'submitted', updated_at = ? WHERE operation_id = ?",
                    (now, operation_id),
                )
            return self._operation_view(connection, operation_id)
