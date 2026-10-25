"""Immutable SQLite ledger and transactional outbox for local disk databases.

Every operation owns a short-lived connection. Provider work belongs outside this
boundary; WAL is intended for a local filesystem, not a network-mounted path.
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib.resources import files
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .contracts import DomainError, EventRecord, GraphSpec, RunRecord, Snapshot


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Ledger:
    def __init__(self, path: Path):
        self.path = Path(path)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise DomainError("unsupported_schema", {"version": version})
            if version == 0:
                migration = files("forecast_anything").joinpath("migrations/001_initial.sql").read_text()
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
        self._put("snapshots", {"snapshot_id": snapshot.snapshot_id}, _json(snapshot.model_dump(mode="json")))
        return snapshot.snapshot_id

    def get_snapshot(self, snapshot_id: str) -> Snapshot:
        return Snapshot.model_validate_json(self._get("snapshots", {"snapshot_id": snapshot_id}))

    def put_graph(self, spec: GraphSpec) -> tuple[str, int]:
        self._put("graphs", {"graph_id": spec.graph_id, "version": spec.version}, _json(spec.model_dump(mode="json")))
        return spec.graph_id, spec.version

    def get_graph(self, graph_id: str, version: int) -> GraphSpec:
        return GraphSpec.model_validate_json(self._get("graphs", {"graph_id": graph_id, "version": version}))

    def _put(self, table: str, identity: dict, content: str) -> None:
        # Table and column names come exclusively from internal callers.
        where = " AND ".join(f"{name} = ?" for name in identity)
        with self._transaction() as connection:
            row = connection.execute(f"SELECT content FROM {table} WHERE {where}", tuple(identity.values())).fetchone()
            if row is not None:
                if row[0] != content:
                    raise DomainError("immutable_identity", {"table": table, **identity})
                return
            columns = ", ".join((*identity, "content"))
            placeholders = ", ".join("?" for _ in range(len(identity) + 1))
            connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", (*identity.values(), content))

    def _get(self, table: str, identity: dict) -> str:
        where = " AND ".join(f"{name} = ?" for name in identity)
        with self._connection() as connection:
            row = connection.execute(f"SELECT content FROM {table} WHERE {where}", tuple(identity.values())).fetchone()
        if row is None:
            raise DomainError("not_found", {"table": table, **identity})
        return row[0]

    def append_run(self, run: RunRecord, events: tuple[EventRecord, ...], key: str) -> RunRecord:
        """Commit a run and its ordered events once; cursors are always assigned here.

        Retries must contain the same run and events (excluding their supplied
        cursors). Reusing a run identity with another key is an identity conflict.
        """
        if not key or any(event.run_id != run.run_id for event in events):
            raise DomainError("invalid_append", {"run_id": run.run_id})
        content = _json(run.model_dump(mode="json"))
        event_values = [event.model_dump(mode="json", exclude={"cursor"}) for event in events]
        events_content = _json(event_values)
        try:
            with self._transaction() as connection:
                previous = connection.execute("SELECT content, events_content FROM runs WHERE idempotency_key = ?", (key,)).fetchone()
                if previous is not None:
                    if previous != (content, events_content):
                        raise DomainError("idempotency_conflict", {"key": key})
                    return RunRecord.model_validate_json(previous[0])
                connection.execute("INSERT INTO runs VALUES (?, ?, ?, ?)", (run.run_id, key, content, events_content))
                for event, value in zip(events, event_values):
                    connection.execute("INSERT INTO events (event_id, run_id, content) VALUES (?, ?, ?)", (event.event_id, run.run_id, _json(value)))
        except sqlite3.IntegrityError as error:
            raise DomainError("immutable_identity", {"run_id": run.run_id}) from error
        return RunRecord.model_validate_json(content)

    def get_run(self, run_id: str) -> RunRecord:
        return RunRecord.model_validate_json(self._get("runs", {"run_id": run_id}))

    def get_run_by_key(self, key: str) -> RunRecord | None:
        with self._connection() as connection:
            row = connection.execute("SELECT content FROM runs WHERE idempotency_key = ?", (key,)).fetchone()
        return None if row is None else RunRecord.model_validate_json(row[0])

    def events_after(self, cursor: int, limit: int = 100) -> tuple[EventRecord, ...]:
        if limit <= 0:
            raise DomainError("invalid_limit", {"limit": limit})
        with self._connection() as connection:
            rows = connection.execute("SELECT cursor, content FROM events WHERE cursor > ? ORDER BY cursor LIMIT ?", (cursor, limit)).fetchall()
        return tuple(EventRecord.model_validate({**json.loads(content), "cursor": assigned}) for assigned, content in rows)
