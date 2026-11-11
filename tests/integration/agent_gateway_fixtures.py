"""Setup and request helpers for agent gateway integration tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.contracts import (
    DiscoveryBudget,
    DiscoveryEpoch,
    SourceSpec,
)
from forecast_anything.discovery.candidates import CandidateProposal, compile_proposal
from forecast_anything.jobs import JobQueue
from forecast_anything.runtime import Runtime
from forecast_anything.sources.catalog import SourceCatalog
from forecast_anything.sources.profiling import inspect_source
from forecast_anything.store import Ledger

NOW = datetime(2026, 10, 24, tzinfo=UTC)


def _setup(tmp_path, *, max_tool_calls=4, max_candidates=3):
    csv = tmp_path / "sales.csv"
    csv.write_text("time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n")
    ledger = Ledger(tmp_path / "state.db", clock=lambda: NOW)
    spec = SourceSpec(
        source_id="sales",
        kind="csv",
        location=str(csv),
        refresh_seconds=120,
        mapping={
            "event_time": "time",
            "available_at": "time",
            "value": "value",
            **{
                name: {"constant": value}
                for name, value in {
                    "series_id": "sales",
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
    SourceCatalog(ledger.path).append(spec)
    candidate = compile_proposal(
        CandidateProposal(
            template_id="forecast_change", source_ids=("sales",), reason="Frozen"
        ),
        (inspect_source(spec),),
        epoch_id="epoch",
    )
    ledger.put_discovery_epoch(
        DiscoveryEpoch(
            epoch_id="epoch",
            source_snapshot_ids=(),
            explored_candidate_ids=(candidate.candidate_id,),
            final_origin_ids=(),
        ),
        DiscoveryBudget(max_candidates=max_candidates, max_tool_calls=max_tool_calls),
    )
    ledger.register_candidate(candidate)
    job = JobQueue(ledger).enqueue(
        "discovery/sales",
        {
            "kind": "discovery",
            "epoch_id": "epoch",
            "source_ids": ["sales"],
            "session_id": "session-1",
        },
    )
    runtime = Runtime(ledger, {}, {}, lambda: NOW)
    client = TestClient(
        create_app(ledger, runtime, workspace_token="workspace", agent_token="agent")
    )
    return client, ledger, job, candidate, csv


def _operation(job_id, *, call_key="call-1", tool="inspectSource", value=None):
    return {
        "job_id": job_id,
        "epoch_id": "epoch",
        "session_id": "session-1",
        "call_key": call_key,
        "tool": tool,
        "input": value if value is not None else {"source_id": "sales"},
    }


def _agent_post(client, payload, token="agent"):
    return client.post(
        "/v1/agent/operations",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
