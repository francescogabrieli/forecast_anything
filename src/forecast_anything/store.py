"""Immutable SQLite ledger and transactional outbox for local disk databases.

Every operation owns a short-lived connection. Provider work belongs outside this
boundary; WAL is intended for a local filesystem, not a network-mounted path.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import Iterator

from .contracts import (
    Candidate,
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EligibilityDecision,
    EvaluationRecord,
    EventRecord,
    GraphSpec,
    RunRecord,
    Snapshot,
)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 3:
                raise DomainError("unsupported_schema", {"version": version})
            if version == 0:
                migration = (
                    files("forecast_anything")
                    .joinpath("migrations/001_initial.sql")
                    .read_text()
                )
                connection.executescript(migration)
            if version < 2:
                migration = (
                    files("forecast_anything")
                    .joinpath("migrations/002_evaluations.sql")
                    .read_text()
                )
                connection.executescript(migration)

            if version < 3:
                migration = (
                    files("forecast_anything")
                    .joinpath("migrations/003_discovery.sql")
                    .read_text()
                )
                connection.executescript(migration)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = FULL")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def put_snapshot(self, snapshot: Snapshot) -> str:
        self._put(
            "snapshots",
            {"snapshot_id": snapshot.snapshot_id},
            _json(snapshot.model_dump(mode="json")),
        )
        return snapshot.snapshot_id

    def get_snapshot(self, snapshot_id: str) -> Snapshot:
        return Snapshot.model_validate_json(
            self._get("snapshots", {"snapshot_id": snapshot_id})
        )

    def put_graph(self, spec: GraphSpec) -> tuple[str, int]:
        self._put(
            "graphs",
            {"graph_id": spec.graph_id, "version": spec.version},
            _json(spec.model_dump(mode="json")),
        )
        return spec.graph_id, spec.version

    def get_graph(self, graph_id: str, version: int) -> GraphSpec:
        return GraphSpec.model_validate_json(
            self._get("graphs", {"graph_id": graph_id, "version": version})
        )

    def _put(self, table: str, identity: dict, content: str) -> None:
        # Table and column names come exclusively from internal callers.
        where = " AND ".join(f"{name} = ?" for name in identity)
        with self._transaction() as connection:
            row = connection.execute(
                f"SELECT content FROM {table} WHERE {where}", tuple(identity.values())
            ).fetchone()
            if row is not None:
                if row[0] != content:
                    raise DomainError(
                        "immutable_identity", {"table": table, **identity}
                    )
                return
            columns = ", ".join((*identity, "content"))
            placeholders = ", ".join("?" for _ in range(len(identity) + 1))
            connection.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                (*identity.values(), content),
            )

    def _get(self, table: str, identity: dict) -> str:
        where = " AND ".join(f"{name} = ?" for name in identity)
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT content FROM {table} WHERE {where}", tuple(identity.values())
            ).fetchone()
        if row is None:
            raise DomainError("not_found", {"table": table, **identity})
        return row[0]

    def append_run(
        self, run: RunRecord, events: tuple[EventRecord, ...], key: str
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
            with self._transaction() as connection:
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
                for event, value in zip(events, event_values):
                    connection.execute(
                        "INSERT INTO events (event_id, run_id, content) VALUES (?, ?, ?)",
                        (event.event_id, run.run_id, _json(value)),
                    )
        except sqlite3.IntegrityError as error:
            raise DomainError("immutable_identity", {"run_id": run.run_id}) from error
        return RunRecord.model_validate_json(content)

    def get_run(self, run_id: str) -> RunRecord:
        return RunRecord.model_validate_json(self._get("runs", {"run_id": run_id}))

    def append_evaluation(self, record: EvaluationRecord) -> str:
        record = EvaluationRecord.model_validate(record.model_dump())
        if record.discovery is not None:
            self._validate_discovery_evaluation(record)
        content = _json(record.model_dump(mode="json"))
        with self._transaction() as connection:
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
        from .evaluation.records import evaluate_run

        context = record.discovery
        candidate = self.get_candidate(context.candidate_id)
        epoch = self.get_discovery_epoch(context.epoch_id)
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
        expected = evaluate_run(run, actuals, candidate.graph)
        if record.model_dump(exclude={"discovery"}) != expected.model_dump(
            exclude={"discovery"}
        ):
            raise DomainError("invalid_discovery_evidence", {})

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

    def put_discovery_epoch(
        self, epoch: DiscoveryEpoch, budget: DiscoveryBudget
    ) -> str:
        """Freeze search configuration, budget and target reservations atomically.

        Origin IDs denote dataset/window identities, never configuration-specific
        labels. Different configurations must reserve fresh final windows.
        """
        epoch = DiscoveryEpoch.model_validate(epoch.model_dump())
        budget = DiscoveryBudget.model_validate(budget.model_dump())
        content, limits = (
            _json(epoch.model_dump(mode="json")),
            _json(budget.model_dump()),
        )
        with self._transaction() as connection:
            previous = connection.execute(
                "SELECT content, budget FROM discovery_epochs WHERE epoch_id = ?",
                (epoch.epoch_id,),
            ).fetchone()
            if previous is not None:
                if previous != (content, limits):
                    raise DomainError(
                        "immutable_identity", {"epoch_id": epoch.epoch_id}
                    )
                return epoch.epoch_id
            for snapshot_id in epoch.source_snapshot_ids:
                if (
                    connection.execute(
                        "SELECT 1 FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
                    ).fetchone()
                    is None
                ):
                    raise DomainError(
                        "missing_discovery_snapshot", {"snapshot_id": snapshot_id}
                    )
            for role, origins in (
                ("final", epoch.final_origin_ids),
                ("tuning", epoch.tuning_origin_ids),
            ):
                for origin in origins:
                    reservations = connection.execute(
                        "SELECT role FROM discovery_origins WHERE origin_id = ?",
                        (origin,),
                    ).fetchall()
                    if reservations and (
                        role == "final" or any(r[0] == "final" for r in reservations)
                    ):
                        raise DomainError("holdout_reuse", {"origin_id": origin})
            connection.execute(
                "INSERT INTO discovery_epochs VALUES (?, ?, ?)",
                (epoch.epoch_id, content, limits),
            )
            for role, origins in (
                ("final", epoch.final_origin_ids),
                ("tuning", epoch.tuning_origin_ids),
            ):
                for origin in origins:
                    connection.execute(
                        "INSERT INTO discovery_origins VALUES (?, ?, ?)",
                        (origin, epoch.epoch_id, role),
                    )
        return epoch.epoch_id

    def get_discovery_epoch(self, epoch_id: str) -> DiscoveryEpoch:
        return DiscoveryEpoch.model_validate_json(
            self._get("discovery_epochs", {"epoch_id": epoch_id})
        )

    def register_candidate(self, candidate: Candidate) -> str:
        from .discovery.candidates import validate_candidate

        candidate = Candidate.model_validate(candidate.model_dump())
        if "candidate_identity_mismatch" in validate_candidate(candidate):
            raise DomainError("candidate_identity_mismatch", {})
        content = _json(candidate.model_dump(mode="json"))
        with self._transaction() as connection:
            previous = connection.execute(
                "SELECT content FROM discovery_candidates WHERE candidate_id = ?",
                (candidate.candidate_id,),
            ).fetchone()
            if previous is not None:
                # Agent prose is not part of question identity: first proposal wins.
                return candidate.candidate_id
            row = connection.execute(
                "SELECT content, budget FROM discovery_epochs WHERE epoch_id = ?",
                (candidate.epoch_id,),
            ).fetchone()
            if row is None:
                raise DomainError("unknown_discovery_epoch", {})
            epoch, budget = (
                DiscoveryEpoch.model_validate_json(row[0]),
                DiscoveryBudget.model_validate_json(row[1]),
            )
            if candidate.candidate_id not in epoch.explored_candidate_ids:
                raise DomainError("epoch_lineage_mismatch", {})
            count = connection.execute(
                "SELECT COUNT(*) FROM discovery_candidates WHERE epoch_id = ?",
                (candidate.epoch_id,),
            ).fetchone()[0]
            if count >= budget.max_candidates:
                raise DomainError(
                    "discovery_budget_exhausted", {"budget": "candidates"}
                )
            connection.execute(
                "INSERT INTO discovery_candidates VALUES (?, ?, ?)",
                (candidate.candidate_id, candidate.epoch_id, content),
            )
        return candidate.candidate_id

    def get_candidate(self, candidate_id: str) -> Candidate:
        return Candidate.model_validate_json(
            self._get("discovery_candidates", {"candidate_id": candidate_id})
        )

    def discovery_usage(self, epoch_id: str) -> tuple[int, int]:
        self.get_discovery_epoch(epoch_id)
        with self._connection() as connection:
            return tuple(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE epoch_id = ?", (epoch_id,)
                ).fetchone()[0]
                for table in ("discovery_candidates", "discovery_tool_calls")
            )

    def consume_discovery_tool_call(self, epoch_id: str, call_id: str) -> None:
        """Reserve a call before dispatch; retry the same operation ID after restart."""
        if not isinstance(call_id, str) or not call_id.strip():
            raise DomainError("invalid_tool_call_id", {})
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT budget FROM discovery_epochs WHERE epoch_id = ?", (epoch_id,)
            ).fetchone()
            if row is None:
                raise DomainError("unknown_discovery_epoch", {})
            if connection.execute(
                "SELECT 1 FROM discovery_tool_calls WHERE epoch_id = ? AND call_id = ?",
                (epoch_id, call_id),
            ).fetchone():
                return
            budget = DiscoveryBudget.model_validate_json(row[0])
            count = connection.execute(
                "SELECT COUNT(*) FROM discovery_tool_calls WHERE epoch_id = ?",
                (epoch_id,),
            ).fetchone()[0]
            if count >= budget.max_tool_calls:
                raise DomainError(
                    "discovery_budget_exhausted", {"budget": "tool_calls"}
                )
            connection.execute(
                "INSERT INTO discovery_tool_calls VALUES (?, ?)", (epoch_id, call_id)
            )

    def append_eligibility_decision(
        self, candidate_id: str, decision: EligibilityDecision
    ) -> None:
        candidate = self.get_candidate(candidate_id)
        decision = EligibilityDecision.model_validate(decision.model_dump())
        if (decision.candidate_id, decision.protocol_id, decision.epoch_id) != (
            candidate_id,
            candidate.protocol_id,
            candidate.epoch_id,
        ):
            raise DomainError("decision_lineage_mismatch", {})
        from .discovery.policy import assess_candidate

        expected = assess_candidate(
            candidate,
            tuple(
                self.get_evaluation(identity) for identity in decision.evaluation_ids
            ),
            self.get_discovery_epoch(candidate.epoch_id),
        )
        if decision != expected:
            raise DomainError("invalid_eligibility_decision", {})
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO eligibility_decisions (candidate_id, content) VALUES (?, ?)",
                (candidate_id, _json(decision.model_dump(mode="json"))),
            )

    def eligibility_decisions(
        self, candidate_id: str
    ) -> tuple[EligibilityDecision, ...]:
        self.get_candidate(candidate_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT content FROM eligibility_decisions WHERE candidate_id = ? ORDER BY sequence",
                (candidate_id,),
            ).fetchall()
        return tuple(EligibilityDecision.model_validate_json(row[0]) for row in rows)
