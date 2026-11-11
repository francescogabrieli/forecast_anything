"""Persistence for watches and their append-only transition history."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..contracts import DomainError, EligibilityDecision, Watch
from .encoding import _json

if TYPE_CHECKING:
    from ..jobs import LeaseGuard


class WatchStorageMixin:
    def put_watch(
        self,
        watch: Watch,
        *,
        now: datetime | None = None,
        lease_guard: LeaseGuard | None = None,
    ) -> str:
        """Create a candidate watch; qualification and controls require events.

        The stored Candidate and epoch supply authoritative question/dependency
        lineage. Existing watch identities cannot replace their current history.
        """
        watch = Watch.model_validate(watch.model_dump())
        now = datetime.now(UTC) if now is None else now
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise DomainError("invalid_watch_time", {})
        candidate = self.get_candidate(watch.candidate_id)
        epoch = self.get_discovery_epoch(candidate.epoch_id)
        if watch.candidate != candidate or (
            watch.source_snapshot_ids
            and watch.source_snapshot_ids != epoch.source_snapshot_ids
        ):
            raise DomainError("watch_lineage_mismatch", {})
        watch = Watch.model_validate(
            watch.model_dump() | {"source_snapshot_ids": epoch.source_snapshot_ids}
        )
        expected_lifecycle = "candidate" if candidate.executable else "unsupported"
        if (
            watch.lifecycle != expected_lifecycle
            or watch.quality != "provisional"
            or watch.eligibility_decision is not None
            or watch.evidence_applicable
            or not watch.reevaluation_required
            or watch.invalidated_evaluation_ids
            or watch.candidate_invalidated
        ):
            raise DomainError("invalid_initial_watch", {})
        content = _json(watch.model_dump(mode="json"))
        with self._transaction(lease_guard) as connection:
            if watch.supersedes_watch_id is not None:
                predecessor = connection.execute(
                    "SELECT content FROM watches WHERE watch_id = ?",
                    (watch.supersedes_watch_id,),
                ).fetchone()
                if predecessor is None:
                    raise DomainError("missing_watch_predecessor", {})
                old = Watch.model_validate_json(predecessor[0])
                if old.candidate_id == watch.candidate_id or (
                    old.candidate.source_ids,
                    old.candidate.template_id,
                ) != (candidate.source_ids, candidate.template_id):
                    raise DomainError("invalid_watch_supersession", {})
            previous = connection.execute(
                "SELECT content FROM watches WHERE watch_id = ?", (watch.watch_id,)
            ).fetchone()
            if previous is not None:
                if previous[0] != content:
                    raise DomainError(
                        "immutable_identity", {"watch_id": watch.watch_id}
                    )
                return watch.watch_id
            connection.execute(
                "INSERT INTO watches VALUES (?, ?, ?, ?)",
                (
                    watch.watch_id,
                    watch.candidate_id,
                    watch.supersedes_watch_id,
                    content,
                ),
            )
            connection.execute(
                "INSERT INTO watch_history (watch_id, event_id, occurred_at, event_content, content) VALUES (?, ?, ?, ?, ?)",
                (
                    watch.watch_id,
                    "created",
                    now.isoformat(),
                    _json({"kind": "created"}),
                    content,
                ),
            )
            for source_id in candidate.source_ids:
                connection.execute(
                    """INSERT OR IGNORE INTO source_subscriptions
                    (source_id, active, created_at, updated_at) VALUES (?, 1, ?, ?)""",
                    (source_id, now.isoformat(), now.isoformat()),
                )
        return watch.watch_id

    def get_watch(self, watch_id: str) -> Watch:
        return Watch.model_validate_json(self._get("watches", {"watch_id": watch_id}))

    def list_watches(self) -> tuple[Watch, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT content FROM watches ORDER BY watch_id"
            ).fetchall()
        return tuple(Watch.model_validate_json(row[0]) for row in rows)

    def advance_watch(
        self,
        watch_id: str,
        event: dict,
        now: datetime,
        *,
        event_id: str,
        lease_guard: LeaseGuard | None = None,
    ) -> Watch:
        """Atomically apply an idempotent transition and retain the issued state.

        An evidence event can consume only an immutable decision recomputed by
        append_eligibility_decision. Retries return the original event's result.
        """
        from ..watches import advance_watch

        if (
            not isinstance(event_id, str)
            or not event_id.strip()
            or event_id == "created"
        ):
            raise DomainError("invalid_watch_event_id", {})
        event = dict(event)
        if isinstance(event.get("decision"), EligibilityDecision):
            event["decision"] = event["decision"].model_dump(mode="json")
        if isinstance(event.get("next_due_at"), datetime):
            event["next_due_at"] = event["next_due_at"].isoformat()
        if isinstance(event.get("requalification_due_at"), datetime):
            event["requalification_due_at"] = event[
                "requalification_due_at"
            ].isoformat()
        if isinstance(event.get("forecast_horizon_end"), datetime):
            event["forecast_horizon_end"] = event["forecast_horizon_end"].isoformat()
        event_content = _json(event)
        with self._transaction(lease_guard) as connection:
            previous = connection.execute(
                "SELECT event_content, content FROM watch_history WHERE watch_id = ? AND event_id = ?",
                (watch_id, event_id),
            ).fetchone()
            if previous is not None:
                if previous[0] != event_content:
                    raise DomainError("idempotency_conflict", {"event_id": event_id})
                return Watch.model_validate_json(previous[1])
            row = connection.execute(
                "SELECT content FROM watches WHERE watch_id = ?", (watch_id,)
            ).fetchone()
            if row is None:
                raise DomainError("not_found", {"watch_id": watch_id})
            watch = Watch.model_validate_json(row[0])
            if event.get("kind") == "evidence_qualified":
                decision = EligibilityDecision.model_validate(event.get("decision"))
                if (
                    connection.execute(
                        "SELECT 1 FROM eligibility_decisions WHERE candidate_id = ? AND content = ?",
                        (watch.candidate_id, _json(decision.model_dump(mode="json"))),
                    ).fetchone()
                    is None
                ):
                    raise DomainError("unrecorded_eligibility_decision", {})
            updated = advance_watch(watch, event, now)
            content = _json(updated.model_dump(mode="json"))
            connection.execute(
                "UPDATE watches SET content = ? WHERE watch_id = ?", (content, watch_id)
            )
            connection.execute(
                "INSERT INTO watch_history (watch_id, event_id, occurred_at, event_content, content) VALUES (?, ?, ?, ?, ?)",
                (watch_id, event_id, now.isoformat(), event_content, content),
            )
        return updated

    def watch_history(self, watch_id: str) -> tuple[dict, ...]:
        self.get_watch(watch_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT sequence, event_id, occurred_at, event_content, content FROM watch_history WHERE watch_id = ? ORDER BY sequence",
                (watch_id,),
            ).fetchall()
        return tuple(
            {
                "sequence": sequence,
                "event_id": event_id,
                "occurred_at": datetime.fromisoformat(occurred_at),
                "event": json.loads(event),
                "watch": Watch.model_validate_json(content),
            }
            for sequence, event_id, occurred_at, event, content in rows
        )

    def watch_history_page(
        self, watch_id: str, *, offset: int = 0, limit: int = 25
    ) -> tuple[tuple[dict, ...], int | None]:
        if type(offset) is not int or offset < 0:
            raise DomainError("invalid_watch_history_offset", {})
        if type(limit) is not int or not 1 <= limit <= 100:
            raise DomainError("invalid_watch_history_limit", {})
        self.get_watch(watch_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT sequence, event_id, occurred_at, event_content, content "
                "FROM watch_history WHERE watch_id = ? ORDER BY sequence LIMIT ? OFFSET ?",
                (watch_id, limit + 1, min(offset, 2**63 - 1)),
            ).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        entries = tuple(
            {
                "sequence": sequence,
                "event_id": event_id,
                "occurred_at": datetime.fromisoformat(occurred_at),
                "event": json.loads(event),
                "watch": Watch.model_validate_json(content),
            }
            for sequence, event_id, occurred_at, event, content in rows
        )
        return entries, offset + len(entries) if has_more else None
