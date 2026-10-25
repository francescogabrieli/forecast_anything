"""Append-only SQLite source specifications and assumption revisions.

The catalog is trusted application storage, never an agent payload. It retains
secret *references* for refresh jobs; resolved credentials are never stored.
append snapshots its input, reuses an identical latest revision, and otherwise
adds a row. Reads return detached copies, so mutating a result cannot rewrite
history. Source identity includes mapping, refresh policy and location, without
publishing those potentially sensitive values in snapshots.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from ..connectors.http_json import SecretResolver
from ..contracts import Contract, DomainError, Snapshot, SourceProfile, SourceSpec


class SourceRevision(Contract):
    revision: str
    spec: SourceSpec
    assumptions: tuple[str, ...]


def source_revision(spec: SourceSpec, assumptions: tuple[str, ...] = ()) -> str:
    content = json.dumps(
        {"spec": spec.model_dump(mode="json"), "assumptions": assumptions},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return sha256(content.encode()).hexdigest()


class SourceCatalog:
    """Small durable registry; callers provide a local SQLite database path."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        with sqlite3.connect(self.path) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS source_revisions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    assumptions_json TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS source_revisions_no_update
                BEFORE UPDATE ON source_revisions
                BEGIN SELECT RAISE(ABORT, 'source revisions are append-only'); END
            """)
            connection.execute("""
                CREATE TRIGGER IF NOT EXISTS source_revisions_no_delete
                BEFORE DELETE ON source_revisions
                BEGIN SELECT RAISE(ABORT, 'source revisions are append-only'); END
            """)

    @staticmethod
    def _decode(row) -> SourceRevision:
        return SourceRevision(
            revision=row[0],
            spec=SourceSpec.model_validate_json(row[1]),
            assumptions=tuple(json.loads(row[2])),
        )

    def append(
        self, spec: SourceSpec, assumptions: tuple[str, ...] = ()
    ) -> SourceRevision:
        revision = source_revision(spec, assumptions)
        with sqlite3.connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                "SELECT revision, spec_json, assumptions_json FROM source_revisions "
                "WHERE source_id = ? ORDER BY sequence DESC LIMIT 1",
                (spec.source_id,),
            ).fetchone()
            if latest is not None and latest[0] == revision:
                return self._decode(latest)
            spec_json = spec.model_dump_json()
            assumptions_json = json.dumps(assumptions)
            connection.execute(
                "INSERT INTO source_revisions (source_id, revision, spec_json, assumptions_json) "
                "VALUES (?, ?, ?, ?)",
                (spec.source_id, revision, spec_json, assumptions_json),
            )
        return self._decode((revision, spec_json, assumptions_json))

    def history(self, source_id: str) -> tuple[SourceRevision, ...]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT revision, spec_json, assumptions_json FROM source_revisions "
                "WHERE source_id = ? ORDER BY sequence",
                (source_id,),
            ).fetchall()
        return tuple(self._decode(row) for row in rows)

    def get(self, source_id: str, revision: str | None = None) -> SourceRevision:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                "SELECT revision, spec_json, assumptions_json FROM source_revisions "
                "WHERE source_id = ? AND (? IS NULL OR revision = ?) "
                "ORDER BY sequence DESC LIMIT 1",
                (source_id, revision, revision),
            ).fetchone()
        if row is None:
            raise DomainError("source_not_found", {})
        return self._decode(row)


# Delayed imports keep the required public functions available here as well as
# profiling.py, without a catalog/profiling import cycle.
def inspect_source(
    spec: SourceSpec, *, secret_resolver: SecretResolver | None = None
) -> SourceProfile:
    from .profiling import inspect_source as inspect

    return inspect(spec, secret_resolver=secret_resolver)


def ingest_source(
    spec: SourceSpec, as_of: datetime, *, secret_resolver: SecretResolver | None = None
) -> Snapshot:
    from .profiling import ingest_source as ingest

    return ingest(spec, as_of, secret_resolver=secret_resolver)
