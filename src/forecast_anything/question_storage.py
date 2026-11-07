"""Transactional persistence for stable questions and immutable semantic history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256

from .contracts import (
    DomainError,
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
)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(namespace: str, *parts: str) -> str:
    return sha256("/".join((namespace, *parts)).encode("utf-8")).hexdigest()


def _hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


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
            """SELECT title, status, current_revision, created_at, updated_at
            FROM questions WHERE question_id = ?""",
            (question_id,),
        ).fetchone()
        if row is None:
            raise DomainError("not_found", {"question_id": question_id})
        title, status, current_revision, created_at, updated_at = row
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
                "SELECT title, status FROM questions WHERE question_id = ?",
                (question_id,),
            ).fetchone()
            if row is None:
                raise DomainError("not_found", {"question_id": question_id})
            title = patch.title if "title" in patch.model_fields_set else row[0]
            status = patch.status if "status" in patch.model_fields_set else row[1]
            connection.execute(
                "UPDATE questions SET title = ?, status = ?, updated_at = ? WHERE question_id = ?",
                (title, status, now, question_id),
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
        self, question_id: str, request: QuestionReferenceRequest
    ) -> QuestionReference:
        request = QuestionReferenceRequest.model_validate(request.model_dump())
        body = request.model_dump(mode="json", exclude={"key"})
        encoded = _json(body)
        request_hash = _hash(encoded)
        reference_id = _identity(
            "question-reference", question_id, str(request.revision), request.key
        )
        now = self._question_time()
        with self._transaction() as connection:
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
