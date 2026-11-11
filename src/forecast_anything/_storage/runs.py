"""Persistence for published forecast runs, events, and evaluations."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from ..contracts import DomainError, EvaluationRecord, EventRecord, RunRecord
from .encoding import _json

if TYPE_CHECKING:
    from ..jobs import LeaseGuard


class RunStorageMixin:
    def append_run(
        self,
        run: RunRecord,
        events: tuple[EventRecord, ...],
        key: str,
        lease_guard: LeaseGuard | None = None,
    ) -> RunRecord:
        """Commit a run and its ordered events once; cursors are always assigned here.

        Retries must contain the same run and events (excluding their supplied
        cursors). Reusing a run identity with another key is an identity conflict.
        """
        if not key or any(event.run_id != run.run_id for event in events):
            raise DomainError("invalid_append", {"run_id": run.run_id})
        content = _json(run.model_dump(mode="json"))
        event_values = [
            event.model_dump(mode="json", exclude={"cursor"}) for event in events
        ]
        events_content = _json(event_values)
        try:
            with self._transaction(lease_guard) as connection:
                previous = connection.execute(
                    "SELECT content, events_content FROM runs WHERE idempotency_key = ?",
                    (key,),
                ).fetchone()
                if previous is not None:
                    if previous != (content, events_content):
                        raise DomainError("idempotency_conflict", {"key": key})
                    return RunRecord.model_validate_json(previous[0])
                connection.execute(
                    "INSERT INTO runs VALUES (?, ?, ?, ?)",
                    (run.run_id, key, content, events_content),
                )
                for event, value in zip(events, event_values, strict=False):
                    connection.execute(
                        "INSERT INTO events (event_id, run_id, content) VALUES (?, ?, ?)",
                        (event.event_id, run.run_id, _json(value)),
                    )
        except sqlite3.IntegrityError as error:
            raise DomainError("immutable_identity", {"run_id": run.run_id}) from error
        return RunRecord.model_validate_json(content)

    def run_bindings(self, run_id: str) -> dict[str, str]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT events_content FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise DomainError("not_found", {"run_id": run_id})
        return next(
            (
                e["payload"]["source_bindings"]
                for e in json.loads(row[0])
                if e["kind"] == "run_started"
            ),
            {},
        )

    def get_run(self, run_id: str) -> RunRecord:
        return RunRecord.model_validate_json(self._get("runs", {"run_id": run_id}))

    def run_events(self, run_id: str) -> tuple[EventRecord, ...]:
        """Read the atomic event batch of one published run (without global scans)."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT events_content FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise DomainError("not_found", {"run_id": run_id})
        return tuple(
            EventRecord.model_validate({**value, "cursor": 0})
            for value in json.loads(row[0])
        )

    def append_evaluation(
        self, record: EvaluationRecord, *, lease_guard: LeaseGuard | None = None
    ) -> str:
        record = EvaluationRecord.model_validate(record.model_dump())
        if record.discovery is not None:
            self._validate_discovery_evaluation(record)
        content = _json(record.model_dump(mode="json"))
        with self._transaction(lease_guard) as connection:
            previous = connection.execute(
                "SELECT content FROM evaluations WHERE evaluation_id = ?",
                (record.evaluation_id,),
            ).fetchone()
            if previous is not None:
                if previous[0] != content:
                    raise DomainError(
                        "immutable_identity", {"evaluation_id": record.evaluation_id}
                    )
                return record.evaluation_id
            try:
                connection.execute(
                    "INSERT INTO evaluations VALUES (?, ?, ?, ?)",
                    (
                        record.evaluation_id,
                        record.run_id,
                        record.actuals_snapshot_id,
                        content,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise DomainError(
                    "missing_evaluation_reference",
                    {
                        "run_id": record.run_id,
                        "actuals_snapshot_id": record.actuals_snapshot_id,
                    },
                ) from error
        return record.evaluation_id

    def _validate_discovery_evaluation(self, record: EvaluationRecord) -> None:
        """Bind claimed scores to stored emissions and vintages in trusted code."""
        from ..evaluation.metrics import scoring_version_from_assumptions
        from ..evaluation.records import evaluate_run

        context = record.discovery
        candidate = self.get_candidate(context.candidate_id)
        epoch = self.get_discovery_epoch(context.epoch_id)
        if context.partition == "final":
            if (
                context.origin_id not in epoch.final_origin_ids
                or epoch.final_candidate_id != candidate.candidate_id
            ):
                raise DomainError("unreserved_discovery_origin", {})
        else:
            with self._connection() as connection:
                final_reservation = connection.execute(
                    "SELECT 1 FROM discovery_origins WHERE origin_id = ? AND role = 'final'",
                    (context.origin_id,),
                ).fetchone()
            if final_reservation is not None:
                raise DomainError("holdout_reuse", {"origin_id": context.origin_id})
            if context.origin_id not in epoch.tuning_origin_ids:
                raise DomainError("unreserved_discovery_origin", {})
        # Epoch reservations are immutable. A declared tuning reservation also
        # prevents another epoch from reserving that origin as final later.
        run = self.get_run(record.run_id)
        actuals = self.get_snapshot(record.actuals_snapshot_id)
        target = run.results.get(candidate.protocol.target_node_id)
        if (
            context.protocol_id != candidate.protocol_id
            or context.epoch_id != candidate.epoch_id
            or context.source_snapshot_ids != epoch.source_snapshot_ids
            or not run.snapshot_ids
            or not set(run.snapshot_ids).issubset(epoch.source_snapshot_ids)
            or target is None
            or not target.timestamps
            or context.target_start != min(target.timestamps)
            or context.target_end != max(target.timestamps)
            or (run.graph_id, run.graph_version)
            != (candidate.graph.graph_id, candidate.graph.version)
        ):
            raise DomainError("invalid_discovery_evidence", {})
        if context.temporal_valid and (
            context.target_start <= run.as_of
            or any(
                snapshot.as_of > run.as_of
                or any(
                    o.event_time > run.as_of or o.available_at > run.as_of
                    for o in snapshot.observations
                )
                for snapshot in (
                    self.get_snapshot(identity) for identity in run.snapshot_ids
                )
            )
        ):
            raise DomainError("invalid_discovery_evidence", {})
        expected = evaluate_run(
            run,
            actuals,
            candidate.graph,
            scoring_version=scoring_version_from_assumptions(record.assumptions),
        )
        if record.model_dump(exclude={"discovery"}) != expected.model_dump(
            exclude={"discovery"}
        ):
            raise DomainError("invalid_discovery_evidence", {})

    def evaluations_for_run(self, run_id: str) -> tuple[EvaluationRecord, ...]:
        """Read separately persisted evidence without rewriting the issued run."""
        self.get_run(run_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT content FROM evaluations WHERE run_id = ? ORDER BY evaluation_id",
                (run_id,),
            ).fetchall()
        return tuple(EvaluationRecord.model_validate_json(row[0]) for row in rows)

    def get_evaluation(self, evaluation_id: str) -> EvaluationRecord:
        return EvaluationRecord.model_validate_json(
            self._get("evaluations", {"evaluation_id": evaluation_id})
        )

    def get_run_by_key(self, key: str) -> RunRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT content FROM runs WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return None if row is None else RunRecord.model_validate_json(row[0])

    def events_after(self, cursor: int, limit: int = 100) -> tuple[EventRecord, ...]:
        if limit <= 0:
            raise DomainError("invalid_limit", {"limit": limit})
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT cursor, content FROM events WHERE cursor > ? ORDER BY cursor LIMIT ?",
                (cursor, limit),
            ).fetchall()
        return tuple(
            EventRecord.model_validate({**json.loads(content), "cursor": assigned})
            for assigned, content in rows
        )

    def latest_run(self, graph_id: str, version: int) -> RunRecord:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT content FROM runs ORDER BY rowid DESC"
            ).fetchall()
        for (content,) in rows:
            run = RunRecord.model_validate_json(content)
            if (run.graph_id, run.graph_version, run.state) == (
                graph_id,
                version,
                "completed",
            ):
                return run
        raise DomainError("not_found", {"graph_id": graph_id})
