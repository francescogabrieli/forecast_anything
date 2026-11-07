"""Seed and verify the synthetic core state used by check-postgres-restart.sh."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from forecast_anything.contracts import DiscoveryBudget, DiscoveryEpoch, SourceSpec
from forecast_anything.discovery.candidates import CandidateProposal, compile_proposal
from forecast_anything.forecast_policy import provider_epoch_context
from forecast_anything.jobs import JobQueue
from forecast_anything.providers.configuration import configured_providers
from forecast_anything.runtime import Runtime
from forecast_anything.sources.catalog import SourceCatalog
from forecast_anything.sources.profiling import inspect_source
from forecast_anything.store import Ledger

SOURCE_ID = "source-synthetic-1"
EPOCH_ID = "epoch-synthetic-restart-test"
JOB_KEY = "discovery/source-synthetic-restart-test"
REASON = "A synthetic question for the restart recovery check."


def seed(database: Path, csv_path: Path) -> dict[str, str]:
    csv_path.write_text(
        "time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n",
        encoding="utf-8",
    )
    spec = SourceSpec(
        source_id=SOURCE_ID,
        kind="csv",
        location=str(csv_path),
        refresh_seconds=120,
        mapping={
            "event_time": "time",
            "available_at": "time",
            "value": "value",
            **{
                name: {"constant": value}
                for name, value in {
                    "series_id": SOURCE_ID,
                    "unit": "count",
                    "revision": "1",
                    "frequency": "D",
                    "calendar": "gregorian",
                    "timezone": "UTC",
                    "missing_values": [],
                }.items()
            },
        },
    )
    ledger = Ledger(database)
    SourceCatalog(database).append(spec)
    candidate = compile_proposal(
        CandidateProposal(
            template_id="forecast_change",
            source_ids=(SOURCE_ID,),
            reason=REASON,
        ),
        (inspect_source(spec),),
        epoch_id=EPOCH_ID,
        forecast_provider="timestral",
    )
    ledger.put_discovery_epoch(
        DiscoveryEpoch(
            epoch_id=EPOCH_ID,
            source_snapshot_ids=(),
            explored_candidate_ids=(candidate.candidate_id,),
            final_origin_ids=(),
        ),
        DiscoveryBudget(max_candidates=3, max_tool_calls=4),
    )
    ledger.register_candidate(candidate)
    job = JobQueue(ledger).enqueue(
        JOB_KEY,
        {
            "kind": "discovery",
            "epoch_id": EPOCH_ID,
            "source_ids": [SOURCE_ID],
            "provider_context": provider_epoch_context(
                Runtime(
                    ledger,
                    configured_providers(),
                    {},
                    lambda: datetime.now(timezone.utc),
                    required_provider="timestral",
                )
            ),
        },
    )
    return {"candidate_id": candidate.candidate_id, "job_id": job.job_id}


def make_due(database: Path, job_id: str) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE jobs SET next_due_at = 0 WHERE job_id = ? AND state = 'pending'",
            (job_id,),
        )


def job_state(database: Path, job_id: str) -> str:
    return JobQueue(Ledger(database)).get(job_id).state


def operations(database: Path, job_id: str) -> list[dict[str, str]]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT call_key, tool, operation_id FROM agent_tool_operations "
            "WHERE job_id = ? ORDER BY rowid",
            (job_id,),
        ).fetchall()
    return [dict(call_key=row[0], tool=row[1], operation_id=row[2]) for row in rows]


def verify(
    database: Path, job_id: str, expected_candidate_id: str, session_id: str
) -> dict:
    ledger = Ledger(database)
    job = JobQueue(ledger).get(job_id)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT result FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    result = json.loads(row[0]) if row and row[0] else {}
    recorded_operations = operations(database, job_id)
    assert job.state == "completed", f"discovery job ended in {job.state}"
    assert job.payload.get("session_id") == session_id, "worker changed Eve session id"
    assert result.get("candidate_ids") == [expected_candidate_id], result
    assert ledger.discovery_usage(EPOCH_ID) == (1, 2), ledger.discovery_usage(EPOCH_ID)
    assert [entry["tool"] for entry in recorded_operations] == [
        "inspectSource",
        "proposeCandidates",
    ], recorded_operations
    assert all(entry["operation_id"] for entry in recorded_operations)
    return {
        "job_id": job_id,
        "session_id": session_id,
        "candidate_id": expected_candidate_id,
        "usage": ledger.discovery_usage(EPOCH_ID),
        "operations": recorded_operations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    seed_parser = commands.add_parser("seed")
    seed_parser.add_argument("--db", type=Path, required=True)
    seed_parser.add_argument("--csv", type=Path, required=True)
    due_parser = commands.add_parser("make-due")
    due_parser.add_argument("--db", type=Path, required=True)
    due_parser.add_argument("--job-id", required=True)
    state_parser = commands.add_parser("job-state")
    state_parser.add_argument("--db", type=Path, required=True)
    state_parser.add_argument("--job-id", required=True)
    operations_parser = commands.add_parser("operations")
    operations_parser.add_argument("--db", type=Path, required=True)
    operations_parser.add_argument("--job-id", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--db", type=Path, required=True)
    verify_parser.add_argument("--job-id", required=True)
    verify_parser.add_argument("--candidate-id", required=True)
    verify_parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    if args.command == "seed":
        result = seed(args.db, args.csv)
    elif args.command == "make-due":
        make_due(args.db, args.job_id)
        result = {"job_id": args.job_id, "due": True}
    elif args.command == "job-state":
        result = {"job_id": args.job_id, "state": job_state(args.db, args.job_id)}
    elif args.command == "operations":
        result = operations(args.db, args.job_id)
    else:
        result = verify(args.db, args.job_id, args.candidate_id, args.session_id)
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
