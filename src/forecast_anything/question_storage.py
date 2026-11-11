"""Transactional persistence for stable questions and immutable semantic history."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from ._storage.encoding import _hash, _identity, _json
from ._storage.inbox import InboxStorageMixin
from ._storage.operations import OperationStorageMixin
from ._storage.webhooks import WebhookStorageMixin
from ._storage.webhooks import _validate_webhook_target as _validate_webhook_target
from .contracts import (
    DomainError,
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
)


class QuestionStorageMixin(
    InboxStorageMixin, OperationStorageMixin, WebhookStorageMixin
):
    """Methods expect the short-lived connection/transaction helpers on Ledger."""

    def _question_time(self) -> str:
        now = self.clock()
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise DomainError("invalid_question_time", {})
        return now.astimezone(UTC).isoformat()

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
