"""The shared durable queue. Expiry reclaims an attempt; failure starts a new one."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from .contracts import DomainError
from .store import Ledger, _json


@dataclass(frozen=True)
class LeaseGuard:
    job_id: str
    lease_token: str


@dataclass(frozen=True)
class Job:
    job_id: str
    key: str
    payload: dict
    attempt: int
    state: str
    lease_token: str | None
    lease_until: datetime | None

    @property
    def emission_key(self) -> str:
        return f"{self.job_id}/{self.attempt}"

    @property
    def guard(self) -> LeaseGuard:
        return LeaseGuard(self.job_id, self.lease_token or "")


def _time(now: datetime) -> float:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise DomainError("naive_timestamp", {})
    return now.timestamp()


class JobQueue:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    @staticmethod
    def _decode(row) -> Job:
        return Job(
            *row[:2],
            json.loads(row[2]),
            *row[3:6],
            datetime.fromtimestamp(row[6], timezone.utc)
            if row[6] is not None
            else None,
        )

    def get(self, job_id: str) -> Job:
        with self.ledger._connection() as connection:
            row = connection.execute(
                "SELECT job_id, logical_key, payload, attempt, state, lease_token, lease_until FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise DomainError("not_found", {"job_id": job_id})
        return self._decode(row)

    def original_payload(self, job_id: str) -> dict:
        """Read detached immutable submission intent, independent of checkpoints."""
        with self.ledger._connection() as connection:
            row = connection.execute(
                "SELECT original_payload FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise DomainError("not_found", {"job_id": job_id})
        return json.loads(row[0])

    def enqueue(
        self, key: str, payload: dict, *, lease_guard: LeaseGuard | None = None
    ) -> Job:
        if not isinstance(key, str) or not key.strip() or not isinstance(payload, dict):
            raise DomainError("invalid_job", {})
        content = _json(payload)
        due = (
            _time(datetime.fromisoformat(payload["next_due_at"]))
            if "next_due_at" in payload
            else 0
        )
        job_id = sha256(key.encode()).hexdigest()
        with self.ledger._transaction(lease_guard) as connection:
            row = connection.execute(
                "SELECT job_id, original_payload FROM jobs WHERE logical_key = ?",
                (key,),
            ).fetchone()
            if row is not None:
                if row[1] != content:
                    raise DomainError("idempotency_conflict", {"key": key})
            else:
                connection.execute(
                    "INSERT INTO jobs VALUES (?, ?, ?, ?, 1, 'pending', NULL, NULL, NULL, ?, NULL)",
                    (job_id, key, content, content, due),
                )
        return self.get(job_id)

    def claim(self, owner: str, now: datetime, ttl_seconds: int) -> Job | None:
        stamp = _time(now)
        if not owner or type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise DomainError("invalid_lease", {})
        with self.ledger._transaction() as connection:
            row = connection.execute(
                "SELECT job_id, attempt FROM jobs WHERE next_due_at <= ? AND "
                "(state = 'pending' OR (state = 'running' AND lease_until <= ?)) "
                "ORDER BY next_due_at, rowid LIMIT 1",
                (stamp, stamp),
            ).fetchone()
            if row is None:
                return None
            token = uuid4().hex
            connection.execute(
                "UPDATE jobs SET state = 'running', owner = ?, lease_token = ?, lease_until = ? WHERE job_id = ?",
                (owner, token, stamp + ttl_seconds, row[0]),
            )
            connection.execute(
                "INSERT OR IGNORE INTO job_attempts (job_id, attempt, state) VALUES (?, ?, 'running')",
                row,
            )
        return self.get(row[0])

    def _guard(self, connection, job: Job, now: datetime):
        self.ledger._assert_lease(
            connection, job.guard, now=max(now, self.ledger.clock())
        )

    def renew(self, job: Job, now: datetime, ttl_seconds: int = 60) -> Job:
        if type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise DomainError("invalid_lease", {})
        with self.ledger._transaction() as connection:
            self._guard(connection, job, now)
            connection.execute(
                "UPDATE jobs SET lease_until = ? WHERE job_id = ?",
                (_time(now) + ttl_seconds, job.job_id),
            )
        return self.get(job.job_id)

    def checkpoint(
        self,
        job: Job,
        payload: dict,
        now: datetime,
        *,
        next_due_at: datetime | None = None,
    ) -> Job:
        """Persist session/poll position before releasing a pending poll."""
        with self.ledger._transaction() as connection:
            self._guard(connection, job, now)
            if next_due_at is None:
                connection.execute(
                    "UPDATE jobs SET payload = ? WHERE job_id = ?",
                    (_json(payload), job.job_id),
                )
            else:
                connection.execute(
                    "UPDATE jobs SET payload = ?, next_due_at = ?, state = 'pending', lease_token = NULL, lease_until = NULL WHERE job_id = ?",
                    (_json(payload), _time(next_due_at), job.job_id),
                )
        return self.get(job.job_id)

    def complete(self, job: Job, now: datetime, result: dict | None = None) -> None:
        with self.ledger._transaction() as connection:
            self._guard(connection, job, now)
            content = _json(result or {})
            connection.execute(
                "UPDATE job_attempts SET state = 'completed', result = ? WHERE job_id = ? AND attempt = ?",
                (content, job.job_id, job.attempt),
            )
            connection.execute(
                "UPDATE jobs SET state = 'completed', result = ?, lease_token = NULL, lease_until = NULL WHERE job_id = ?",
                (content, job.job_id),
            )

    def fail(
        self,
        job: Job,
        now: datetime,
        error: dict,
        *,
        retry_seconds: int = 30,
        max_attempts: int = 3,
    ) -> None:
        with self.ledger._transaction() as connection:
            self._guard(connection, job, now)
            connection.execute(
                "UPDATE job_attempts SET state = 'failed', error = ? WHERE job_id = ? AND attempt = ?",
                (_json(error), job.job_id, job.attempt),
            )
            retry = job.attempt < max_attempts
            connection.execute(
                "UPDATE jobs SET state = ?, attempt = ?, next_due_at = ?, lease_token = NULL, lease_until = NULL WHERE job_id = ?",
                (
                    "pending" if retry else "failed",
                    job.attempt + int(retry),
                    _time(now + timedelta(seconds=retry_seconds)),
                    job.job_id,
                ),
            )

    def history(self, job_id: str) -> tuple[dict, ...]:
        self.get(job_id)
        with self.ledger._connection() as connection:
            rows = connection.execute(
                "SELECT attempt, state, result, error FROM job_attempts WHERE job_id = ? ORDER BY attempt",
                (job_id,),
            ).fetchall()
        return tuple(
            dict(
                attempt=a,
                state=s,
                result=json.loads(r) if r else None,
                error=json.loads(e) if e else None,
            )
            for a, s, r, e in rows
        )
