"""Immutable SQLite ledger and transactional outbox for local disk databases.

Every operation owns a short-lived connection. Provider work belongs outside this
boundary; WAL is intended for a local filesystem, not a network-mounted path.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator

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
    ScenarioRecord,
    Snapshot,
    Watch,
)
from .discovery.agent_storage import AgentStorageMixin
from .question_storage import QuestionStorageMixin

if TYPE_CHECKING:
    from .jobs import LeaseGuard

MIGRATIONS = (
    "001_initial.sql",
    "002_evaluations.sql",
    "003_discovery.sql",
    "004_observatory.sql",
    "005_jobs.sql",
    "006_scenarios.sql",
    "007_agent_operations.sql",
    "008_backtests.sql",
    "009_worker_liveness.sql",
    "010_worker_runtime.sql",
    "011_persistent_questions.sql",
    "012_workspace_identity.sql",
)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Ledger(QuestionStorageMixin, AgentStorageMixin):
    def __init__(self, path: Path, *, clock: Callable[[], datetime] | None = None):
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > len(MIGRATIONS):
                raise DomainError("unsupported_schema", {"version": version})
            for name in MIGRATIONS[version:]:
                migration = (
                    files("forecast_anything").joinpath("migrations", name).read_text()
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

    def workspace_id(self) -> str:
        """Return this ledger's stable, non-secret identity."""
        with self._connection() as connection:
            return connection.execute(
                "SELECT workspace_id FROM workspace_identity WHERE singleton = 1"
            ).fetchone()[0]

    def resource_identity(self, kind: str, resource_id: str) -> str:
        """Check a stored identity without loading its potentially large content."""
        table, column = {
            "run": ("runs", "run_id"),
            "question": ("questions", "question_id"),
            "report": ("backtest_reports", "report_id"),
        }[kind]
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT {column} FROM {table} WHERE {column} = ?", (resource_id,)
            ).fetchone()
        if row is None:
            raise DomainError("not_found", {})
        return row[0]

    def update_worker_heartbeat(
        self, worker_id: str, now: datetime, *, model_status: str | None = None
    ) -> None:
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise DomainError("invalid_worker_identity", {})
        if now.tzinfo is None or now.utcoffset() is None:
            raise DomainError("naive_timestamp", {})
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO worker_liveness (singleton, worker_id, heartbeat_at)
                VALUES (1, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    worker_id = excluded.worker_id,
                    heartbeat_at = excluded.heartbeat_at
                """,
                (worker_id, now.timestamp()),
            )
            if model_status is not None:
                connection.execute(
                    """INSERT INTO worker_runtime VALUES (1, ?, ?)
                    ON CONFLICT(singleton) DO UPDATE SET
                        worker_id = excluded.worker_id, model_status = excluded.model_status""",
                    (worker_id, model_status),
                )

    def clear_worker_heartbeat(self, worker_id: str) -> None:
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise DomainError("invalid_worker_identity", {})
        with self._transaction() as connection:
            connection.execute(
                "DELETE FROM worker_liveness WHERE singleton = 1 AND worker_id = ?",
                (worker_id,),
            )

            connection.execute(
                "DELETE FROM worker_runtime WHERE singleton = 1 AND worker_id = ?",
                (worker_id,),
            )

    def worker_status(self, now: datetime, stale_after_seconds: int = 10) -> str:
        return self.worker_diagnostics(now, stale_after_seconds)[0]

    def worker_diagnostics(
        self,
        now: datetime,
        stale_after_seconds: int = 10,
        *,
        expected_worker_id: str | None = None,
    ) -> tuple[str, str | None]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise DomainError("naive_timestamp", {})
        if type(stale_after_seconds) is not int or stale_after_seconds <= 0:
            raise DomainError("invalid_stale_after", {})
        with self._connection() as connection:
            row = connection.execute(
                """SELECT heartbeat_at, model_status, worker_id FROM worker_liveness
                LEFT JOIN worker_runtime USING (singleton, worker_id)
                WHERE singleton = 1"""
            ).fetchone()
        if row is None or (
            expected_worker_id is not None and row[2] != expected_worker_id
        ):
            return "not_running", None
        age = now.timestamp() - row[0]
        if -stale_after_seconds <= age <= stale_after_seconds:
            return "running", row[1]
        return "stale", None

    @contextmanager
    def _transaction(
        self, lease_guard: LeaseGuard | None = None
    ) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if lease_guard is not None:
                    self._assert_lease(connection, lease_guard)
                yield connection
                if lease_guard is not None:
                    self._assert_lease(connection, lease_guard)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    def put_snapshot(
        self, snapshot: Snapshot, *, lease_guard: LeaseGuard | None = None
    ) -> str:
        self._put(
            "snapshots",
            {"snapshot_id": snapshot.snapshot_id},
            _json(snapshot.model_dump(mode="json")),
            lease_guard=lease_guard,
        )
        return snapshot.snapshot_id

    def get_snapshot(self, snapshot_id: str) -> Snapshot:
        return Snapshot.model_validate_json(
            self._get("snapshots", {"snapshot_id": snapshot_id})
        )

    def put_graph(
        self, spec: GraphSpec, *, lease_guard: LeaseGuard | None = None
    ) -> tuple[str, int]:
        self._put(
            "graphs",
            {"graph_id": spec.graph_id, "version": spec.version},
            _json(spec.model_dump(mode="json")),
            lease_guard=lease_guard,
        )
        return spec.graph_id, spec.version

    def get_graph(self, graph_id: str, version: int) -> GraphSpec:
        return GraphSpec.model_validate_json(
            self._get("graphs", {"graph_id": graph_id, "version": version})
        )

    def _put(
        self,
        table: str,
        identity: dict,
        content: str,
        *,
        lease_guard: LeaseGuard | None = None,
    ) -> None:
        # Table and column names come exclusively from internal callers.
        where = " AND ".join(f"{name} = ?" for name in identity)
        with self._transaction(lease_guard) as connection:
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
                for event, value in zip(events, event_values):
                    connection.execute(
                        "INSERT INTO events (event_id, run_id, content) VALUES (?, ?, ?)",
                        (event.event_id, run.run_id, _json(value)),
                    )
        except sqlite3.IntegrityError as error:
            raise DomainError("immutable_identity", {"run_id": run.run_id}) from error
        return RunRecord.model_validate_json(content)

    def _assert_lease(
        self, connection, guard: LeaseGuard, *, now: datetime | None = None
    ) -> None:
        now = self.clock() if now is None else now
        if now.tzinfo is None or now.utcoffset() is None:
            raise DomainError("naive_timestamp", {})
        row = connection.execute(
            "SELECT state, lease_token, lease_until FROM jobs WHERE job_id = ?",
            (guard.job_id,),
        ).fetchone()
        if (
            row is None
            or row[0] != "running"
            or row[1] != guard.lease_token
            or row[2] <= now.timestamp()
        ):
            raise DomainError("lease_lost", {"job_id": guard.job_id})

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
        from .evaluation.records import evaluate_run

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
        expected = evaluate_run(run, actuals, candidate.graph)
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

    def put_discovery_epoch(
        self,
        epoch: DiscoveryEpoch,
        budget: DiscoveryBudget,
        *,
        lease_guard: LeaseGuard | None = None,
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
        with self._transaction(lease_guard) as connection:
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

    def discovery_budget(self, epoch_id: str) -> DiscoveryBudget:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT budget FROM discovery_epochs WHERE epoch_id = ?", (epoch_id,)
            ).fetchone()
        if row is None:
            raise DomainError("unknown_discovery_epoch", {})
        return DiscoveryBudget.model_validate_json(row[0])

    def get_discovery_epoch(self, epoch_id: str) -> DiscoveryEpoch:
        frozen = DiscoveryEpoch.model_validate_json(
            self._get("discovery_epochs", {"epoch_id": epoch_id})
        )
        with self._connection() as connection:
            additions = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT candidate_id FROM discovery_explored_appends "
                    "WHERE epoch_id = ? ORDER BY rowid",
                    (epoch_id,),
                ).fetchall()
            )
        return frozen.model_copy(
            update={"explored_candidate_ids": frozen.explored_candidate_ids + additions}
        )

    def register_candidate(
        self, candidate: Candidate, *, lease_guard: LeaseGuard | None = None
    ) -> str:
        from .discovery.candidates import validate_candidate

        candidate = Candidate.model_validate(candidate.model_dump())
        if "candidate_identity_mismatch" in validate_candidate(candidate):
            raise DomainError("candidate_identity_mismatch", {})
        content = _json(candidate.model_dump(mode="json"))
        with self._transaction(lease_guard) as connection:
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

    def candidates_for_epoch(self, epoch_id: str) -> tuple[Candidate, ...]:
        self.get_discovery_epoch(epoch_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT content FROM discovery_candidates WHERE epoch_id = ? ORDER BY candidate_id",
                (epoch_id,),
            ).fetchall()
        return tuple(Candidate.model_validate_json(row[0]) for row in rows)

    def discovery_usage(self, epoch_id: str) -> tuple[int, int]:
        self.get_discovery_epoch(epoch_id)
        with self._connection() as connection:
            return tuple(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE epoch_id = ?", (epoch_id,)
                ).fetchone()[0]
                for table in ("discovery_candidates", "discovery_tool_calls")
            )

    def consume_discovery_tool_call(
        self, epoch_id: str, call_id: str, *, lease_guard: LeaseGuard | None = None
    ) -> None:
        """Reserve a call before dispatch; retry the same operation ID after restart."""
        if not isinstance(call_id, str) or not call_id.strip():
            raise DomainError("invalid_tool_call_id", {})
        with self._transaction(lease_guard) as connection:
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
        if decision.backtest_id is not None:
            from .backtesting.store import BacktestStore
            from .discovery.policy import assess_candidate_backtest

            backtests = BacktestStore(self)
            report = backtests.get_report(decision.backtest_id)
            plan = backtests.get_plan(decision.backtest_id)
            if plan.watch_id is None or plan.candidate_id != candidate_id:
                raise DomainError("watch_backtest_lineage_mismatch", {})
            outcomes = []
            offset = 0
            while True:
                page = backtests.list_origins(
                    decision.backtest_id, offset=offset, limit=50
                )
                outcomes.extend(page.origins)
                if page.next_offset is None:
                    break
                offset = page.next_offset
            expected = assess_candidate_backtest(
                candidate, report, plan, tuple(outcomes)
            )
        else:
            from .discovery.policy import assess_candidate

            expected = assess_candidate(
                candidate,
                tuple(
                    self.get_evaluation(identity)
                    for identity in decision.evaluation_ids
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
        now = datetime.now(timezone.utc) if now is None else now
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
        from .watches import advance_watch

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

    def put_scenario(self, record: ScenarioRecord) -> None:
        record = ScenarioRecord.model_validate(record.model_dump())
        parent = self.get_run(record.parent_run_id)
        graph = self.get_graph(record.graph_id, record.version)
        base = self.get_graph(parent.graph_id, parent.graph_version)
        if (
            parent.state != "completed"
            or parent.scenario_id is not None
            or graph.nodes != base.nodes
            or graph.graph_id == base.graph_id
        ):
            raise DomainError("invalid_scenario_lineage", {})
        bindings = self.run_bindings(parent.run_id)
        if set(bindings) != set(record.snapshot_ids):
            raise DomainError("invalid_snapshot_bindings", {})
        for name, snapshot_id in record.snapshot_ids.items():
            snapshot = self.get_snapshot(snapshot_id)
            if (
                snapshot_id != bindings[name]
                and f"assumed:{record.scenario_id}" not in snapshot.assumptions
            ):
                raise DomainError("invalid_scenario_assumptions", {})
        self._put(
            "scenarios",
            {"scenario_id": record.scenario_id},
            _json(record.model_dump(mode="json")),
        )

    def get_scenario(self, scenario_id: str) -> ScenarioRecord:
        return ScenarioRecord.model_validate_json(
            self._get("scenarios", {"scenario_id": scenario_id})
        )

    def scenario_for_graph(self, graph_id: str, version: int) -> ScenarioRecord | None:
        with self._connection() as connection:
            rows = connection.execute("SELECT content FROM scenarios").fetchall()
        for (content,) in rows:
            record = ScenarioRecord.model_validate_json(content)
            if (record.graph_id, record.version) == (graph_id, version):
                return record
        return None
