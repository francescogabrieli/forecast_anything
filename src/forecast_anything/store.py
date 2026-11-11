"""Immutable SQLite ledger and transactional outbox for local disk databases.

Every operation owns a short-lived connection. Provider work belongs outside this
boundary; WAL is intended for a local filesystem, not a network-mounted path.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from ._storage.discovery import DiscoveryStorageMixin
from ._storage.encoding import _json
from ._storage.runs import RunStorageMixin
from ._storage.watches import WatchStorageMixin
from .contracts import DomainError, GraphSpec, ScenarioRecord, Snapshot
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
    "013_continuity_and_inbox.sql",
    "014_workspace_forecast_checkpoint.sql",
)


class Ledger(
    QuestionStorageMixin,
    AgentStorageMixin,
    DiscoveryStorageMixin,
    RunStorageMixin,
    WatchStorageMixin,
):
    def __init__(self, path: Path, *, clock: Callable[[], datetime] | None = None):
        self.path = Path(path)
        self.clock = clock or (lambda: datetime.now(UTC))
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

    def bind_forecast_checkpoint(self, checkpoint: str) -> None:
        """Set the product model once before a process can serve or run forecasts."""
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO workspace_forecast_checkpoint VALUES (1, ?)",
                (checkpoint,),
            )
            existing = connection.execute(
                "SELECT checkpoint FROM workspace_forecast_checkpoint WHERE singleton = 1"
            ).fetchone()[0]
            if existing != checkpoint:
                raise DomainError(
                    "workspace_model_conflict",
                    {
                        "checkpoint": existing,
                        "requested_checkpoint": checkpoint,
                        "recovery": "Use the workspace's original model or create a separate workspace.",
                    },
                )

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
