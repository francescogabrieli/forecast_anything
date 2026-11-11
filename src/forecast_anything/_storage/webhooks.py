"""Persistence for webhook subscriptions and the delivery outbox."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import uuid4

from ..contracts import (
    DomainError,
    InboxEvent,
    WebhookDelivery,
    WebhookDeliveryPage,
    WebhookSubscription,
    WebhookSubscriptionPage,
    WebhookSubscriptionRequest,
)


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
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise DomainError("invalid_webhook_target", {})
    return target_url


class WebhookStorageMixin:
    def _enqueue_event_webhooks(self, connection, event: InboxEvent, *, priority: int):
        from ..jobs import JobQueue

        rows = connection.execute(
            "SELECT subscription_id FROM webhook_subscriptions WHERE active = 1 ORDER BY subscription_id"
        ).fetchall()
        now = event.occurred_at.isoformat()
        for (subscription_id,) in rows:
            delivery_id = sha256(
                f"webhook/{subscription_id}/{event.event_id}".encode()
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
        stamp = now.astimezone(UTC).isoformat()
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
        stamp = now.astimezone(UTC).isoformat()
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
                due = (now + timedelta(seconds=delay)).astimezone(UTC).isoformat()
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
