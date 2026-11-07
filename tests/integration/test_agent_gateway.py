"""Agent bridge trust and restart boundaries."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.contracts import (
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EventRecord,
    RunRecord,
    SourceSpec,
)
from forecast_anything.discovery.candidates import CandidateProposal, compile_proposal
from forecast_anything.jobs import JobQueue
from forecast_anything.runtime import Runtime
from forecast_anything.sources.catalog import SourceCatalog
from forecast_anything.sources.profiling import ingest_source, inspect_source
from forecast_anything.store import Ledger
from forecast_anything.watches import create_watch
from forecast_anything.worker import Worker

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def test_agent_gateway_allows_only_internal_docker_agent_http_origin():
    from forecast_anything.discovery.agent_gateway import AgentGateway

    assert (
        AgentGateway("http://agent:3000", token="bridge-token").base_url
        == "http://agent:3000"
    )
    for unsafe in ("http://agent:3001", "http://remote-agent:3000"):
        with pytest.raises(DomainError, match="invalid_agent_gateway_config"):
            AgentGateway(unsafe, token="bridge-token")


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


def test_agent_token_is_scoped_and_operation_is_bound_to_session(tmp_path):
    client, ledger, job, _, csv = _setup(tmp_path)
    payload = _operation(job.job_id)
    assert _agent_post(client, payload, token="workspace").status_code == 401
    assert (
        client.get("/v1/sources", headers={"Authorization": "Bearer agent"}).status_code
        == 401
    )
    assert _agent_post(client, {**payload, "session_id": "wrong"}).status_code == 422
    assert _agent_post(client, {**payload, "epoch_id": "wrong"}).status_code == 422
    assert ledger.discovery_usage("epoch") == (1, 0)
    response = _agent_post(client, payload)
    assert response.status_code == 200
    assert response.json()["result"]["source_id"] == "sales"
    assert str(csv) not in response.text
    assert ledger.discovery_usage("epoch") == (1, 1)


def test_agent_tool_call_replay_is_stable_and_cannot_reset_budget(tmp_path):
    client, ledger, job, _, _ = _setup(tmp_path, max_tool_calls=1)
    first = _agent_post(client, _operation(job.job_id))
    assert first.status_code == 200
    ledger = Ledger(ledger.path, clock=lambda: NOW)
    replay = _agent_post(client, _operation(job.job_id))
    assert replay.status_code == 200
    assert replay.json() == first.json()
    changed = _agent_post(client, _operation(job.job_id, value={"source_id": "other"}))
    assert changed.status_code == 409
    assert changed.json()["code"] == "idempotency_conflict"
    extra = _agent_post(client, _operation(job.job_id, call_key="call-2"))
    assert extra.status_code == 422
    assert extra.json()["code"] == "discovery_budget_exhausted"
    assert ledger.discovery_usage("epoch") == (1, 1)


def test_exhausted_tool_budget_does_not_block_completed_session_poll(tmp_path):
    client, ledger, job, candidate, _ = _setup(tmp_path, max_tool_calls=4)
    queue = JobQueue(ledger)
    now = [NOW]

    class Gateway:
        calls = 0

        def poll(self, session_id):
            assert session_id == "session-1"
            self.calls += 1
            return None if self.calls == 1 else (candidate,)

    gateway = Gateway()
    runtime = Runtime(ledger, {}, {}, lambda: now[0])
    first = queue.claim("first", NOW, 60)
    assert first.job_id == job.job_id
    assert (
        Worker(runtime, queue, discovery_gateway=gateway)._poll_discovery(first, NOW)
        is None
    )
    for index in range(3):
        response = _agent_post(
            client, _operation(job.job_id, call_key=f"inspect-{index}")
        )
        assert response.status_code == 200
    proposal = _operation(
        job.job_id,
        call_key="propose",
        tool="proposeCandidates",
        value={
            "proposals": [
                {
                    "template_id": "forecast_change",
                    "source_ids": ["sales"],
                    "reason": "Existing frozen question",
                }
            ]
        },
    )
    assert _agent_post(client, proposal).status_code == 200
    assert ledger.discovery_usage("epoch") == (1, 4)
    assert (
        _agent_post(client, _operation(job.job_id, call_key="fifth")).json()["code"]
        == "discovery_budget_exhausted"
    )

    now[0] += timedelta(seconds=30)
    second = queue.claim("second", now[0], 60)
    result = Worker(runtime, queue, discovery_gateway=gateway)._poll_discovery(
        second, now[0]
    )
    queue.complete(second, now[0], result)
    assert queue.get(job.job_id).state == "completed"
    assert result["candidate_ids"] == [candidate.candidate_id]
    assert ledger.discovery_usage("epoch") == (1, 4)


def test_completed_job_allows_only_replay_of_an_existing_tool_call(tmp_path):
    client, ledger, job, _, _ = _setup(tmp_path)
    payload = _operation(job.job_id)
    first = _agent_post(client, payload)
    queue = JobQueue(ledger)
    claimed = queue.claim("owner", NOW, 60)
    queue.complete(claimed, NOW, {})
    replay = _agent_post(client, payload)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert _agent_post(client, {**payload, "call_key": "new"}).status_code == 422
    assert ledger.discovery_usage("epoch") == (1, 1)


def test_agent_boundary_rejects_unconfigured_token_and_malformed_input(tmp_path):
    client, ledger, job, _, _ = _setup(tmp_path)
    runtime = Runtime(ledger, {}, {}, lambda: NOW)
    disabled = TestClient(create_app(ledger, runtime, workspace_token="workspace"))
    assert _agent_post(disabled, _operation(job.job_id), token="").status_code == 401
    with pytest.raises(DomainError, match="invalid_agent_token"):
        create_app(ledger, runtime, workspace_token="same", agent_token="same")
    malformed = _agent_post(
        client, _operation(job.job_id, value={"source_id": ["sales"]})
    )
    assert malformed.status_code == 422
    assert malformed.json()["code"] == "invalid_agent_input"


def test_agent_proposal_reuses_frozen_identity_and_preserves_unregistered_idea(
    tmp_path,
):
    client, ledger, job, candidate, _ = _setup(tmp_path)
    payload = _operation(
        job.job_id,
        tool="proposeCandidates",
        value={
            "proposals": [
                {
                    "template_id": "forecast_change",
                    "source_ids": ["sales"],
                    "reason": "Reworded by an agent",
                    "selection_method": "prespecified_holdout",
                }
            ]
        },
    )
    result = _agent_post(client, payload)
    assert result.status_code == 200
    assert result.json()["result"]["candidateIds"] == [candidate.candidate_id]
    assert (
        result.json()["result"]["candidates"][0]["candidate_id"]
        == candidate.candidate_id
    )
    assert ledger.get_discovery_epoch("epoch").final_origin_ids == ()
    assert ledger.discovery_usage("epoch") == (1, 1)
    payload["call_key"] = "call-2"
    payload["input"]["proposals"][0]["template_id"] = "new_question"
    exploratory = _agent_post(client, payload)
    assert exploratory.status_code == 200
    idea = exploratory.json()["result"]["candidates"][0]
    assert idea["executable"] is False
    assert idea["unresolved"] == ["unregistered_template"]
    assert (
        idea["candidate_id"]
        in ledger.get_discovery_epoch("epoch").explored_candidate_ids
    )
    assert ledger.get_candidate(idea["candidate_id"]).graph.nodes == ()
    assert ledger.list_watches() == ()
    assert ledger.discovery_usage("epoch") == (2, 2)


def test_agent_cannot_forge_graph_or_append_after_final_origin_is_reserved(tmp_path):
    client, ledger, job, candidate, _ = _setup(tmp_path)
    forged = _operation(
        job.job_id,
        tool="proposeCandidates",
        value={
            "proposals": [
                {
                    "template_id": "forecast_change",
                    "source_ids": ["sales"],
                    "reason": "Forge",
                    "graph": {"nodes": [{"provider": "unregistered"}]},
                }
            ]
        },
    )
    invalid = _agent_post(client, forged)
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_agent_input"
    assert ledger.discovery_usage("epoch")[0] == 1

    sealed_candidate = compile_proposal(
        CandidateProposal(
            template_id="forecast_change", source_ids=("sales",), reason="Frozen"
        ),
        candidate.source_profiles,
        epoch_id="sealed",
    )
    ledger.put_discovery_epoch(
        DiscoveryEpoch(
            epoch_id="sealed",
            source_snapshot_ids=(),
            explored_candidate_ids=(sealed_candidate.candidate_id,),
            final_origin_ids=("fresh-final",),
            final_candidate_id=sealed_candidate.candidate_id,
        ),
        DiscoveryBudget(max_candidates=3, max_tool_calls=4),
    )
    ledger.register_candidate(sealed_candidate)
    sealed_job = JobQueue(ledger).enqueue(
        "discovery/sealed",
        {
            "kind": "discovery",
            "epoch_id": "sealed",
            "source_ids": ["sales"],
            "session_id": "session-2",
        },
    )
    proposal = _operation(
        sealed_job.job_id,
        call_key="new",
        tool="proposeCandidates",
        value={
            "proposals": [
                {
                    "template_id": "new_question",
                    "source_ids": ["sales"],
                    "reason": "New",
                }
            ]
        },
    )
    proposal["epoch_id"] = "sealed"
    proposal["session_id"] = "session-2"
    rejected = _agent_post(client, proposal)
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "exploration_closed"
    assert ledger.get_discovery_epoch("sealed").explored_candidate_ids == (
        sealed_candidate.candidate_id,
    )


def test_agent_explanation_contains_only_evidence_from_a_scoped_run(tmp_path):
    client, ledger, job, _, _ = _setup(tmp_path)
    run = RunRecord(
        run_id="run-1",
        graph_id="graph",
        graph_version=1,
        as_of=NOW,
        snapshot_ids=("snap",),
        requested_provider={},
        actual_provider={},
        state="completed",
        results={},
        evidence_ids=("evidence-1",),
        scenario_id=None,
        parent_run_id=None,
    )
    event = EventRecord(
        cursor=0,
        event_id="start",
        kind="run_started",
        run_id=run.run_id,
        payload={"source_bindings": {"sales": "snap"}},
    )
    ledger.append_run(run, (event,), "run-key")
    result = _agent_post(
        client,
        _operation(job.job_id, tool="explainRun", value={"run_id": "run-1"}),
    )
    assert result.status_code == 200
    assert result.json()["result"]["evidenceIds"] == ["evidence-1"]
    assert "probability" not in result.json()["result"]["text"].lower()


def test_template_discovery_schedules_optional_agent_session(tmp_path):
    _, ledger, existing, candidate, _ = _setup(tmp_path)
    queue = JobQueue(ledger)
    claimed = queue.claim("setup", NOW, 60)
    assert claimed.job_id == existing.job_id
    queue.complete(claimed, NOW, {})
    profile = candidate.source_profiles[0]
    registered = SourceCatalog(ledger.path).get("sales")
    template_job = queue.enqueue(
        "templates/new",
        {
            "kind": "discovery_templates",
            "source_id": "sales",
            "revision": registered.revision,
            "epoch_id": "new-epoch",
            "profile": profile.model_dump(mode="json"),
        },
    )
    runtime = Runtime(ledger, {}, {}, lambda: NOW)
    Worker(runtime, queue, discovery_gateway=object()).run_due(NOW, limit=1)
    assert queue.get(template_job.job_id).state == "completed", queue.history(
        template_job.job_id
    )
    agent_job = queue.claim("assert", NOW, 60)
    assert agent_job is not None
    assert agent_job.payload == {
        "kind": "discovery",
        "epoch_id": "new-epoch",
        "source_ids": ["sales"],
    }


def test_refreshed_epoch_schedules_optional_agent_session(tmp_path):
    _, ledger, existing, candidate, _ = _setup(tmp_path)
    queue = JobQueue(ledger)
    queue.complete(queue.claim("setup", NOW, 60), NOW, {})
    watch = create_watch(
        candidate, watch_id="watch", next_due_at=NOW + timedelta(days=1)
    )
    ledger.put_watch(watch, now=NOW)
    spec = SourceCatalog(ledger.path).get("sales").spec
    snapshot = ingest_source(spec, NOW)
    ledger.put_snapshot(snapshot)
    refresh = queue.enqueue(
        "rediscover/test",
        {
            "kind": "discover_refresh",
            "watch_id": "watch",
            "snapshot_id": snapshot.snapshot_id,
            "profile": candidate.source_profiles[0].model_dump(mode="json"),
        },
    )
    Worker(
        Runtime(ledger, {}, {}, lambda: NOW), queue, discovery_gateway=object()
    ).run_due(NOW, limit=1)
    refreshed = queue.get(refresh.job_id)
    assert refreshed.state == "completed", queue.history(refresh.job_id)
    epoch_id = queue.history(refresh.job_id)[0]["result"]["epoch_id"]
    agent_job_id = sha256(f"discovery/agent/{epoch_id}".encode()).hexdigest()
    agent_job = queue.get(agent_job_id)
    assert agent_job.payload == {
        "kind": "discovery",
        "epoch_id": epoch_id,
        "source_ids": ["sales"],
    }


def test_postgres_restart_fixture_reaches_gateway_under_product_policy(
    tmp_path, monkeypatch
):
    import runpy
    from pathlib import Path

    from forecast_anything.providers.configuration import configured_providers

    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty-cache"))
    helper = runpy.run_path(
        str(
            Path(__file__).resolve().parents[2]
            / "apps/agent/scripts/restart-test-core.py"
        )
    )
    db = tmp_path / "restart.db"
    seeded = helper["seed"](db, tmp_path / "source.csv")
    ledger = Ledger(db)
    runtime = Runtime(
        ledger,
        configured_providers(),
        {},
        lambda: datetime.now(timezone.utc),
        required_provider="timestral",
    )

    class Gateway:
        started = False

        def start(self, *args, **kwargs):
            self.started = True
            return "restart-session"

        def poll(self, session_id):
            assert session_id == "restart-session"
            return None

    gateway = Gateway()
    queue = JobQueue(ledger)
    Worker(runtime, queue, discovery_gateway=gateway).run_due(runtime.clock(), limit=1)
    assert gateway.started
    assert queue.get(seeded["job_id"]).state == "pending"
    candidate = ledger.get_candidate(seeded["candidate_id"])
    assert (
        next(n for n in candidate.graph.nodes if n.node_id == "forecast").config[
            "provider"
        ]
        == "timestral"
    )
