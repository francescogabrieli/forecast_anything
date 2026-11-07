"""Public reads redact historical provider diagnostics without rewriting storage."""

import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from test_backtest_api import T, setup
from test_backtest_worker import Provider, configured

from forecast_anything.contracts import DomainError
from forecast_anything.jobs import JobQueue
from forecast_anything.worker import Worker

PRIVATE = "/private/provider-source.csv token=sentinel-secret-413"


@pytest.mark.parametrize("surface", ["http", "sse", "mcp"])
@pytest.mark.parametrize("domain_error", [False, True])
def test_http_sse_and_mcp_redact_persisted_provider_failures(
    tmp_path, monkeypatch, domain_error, surface
):
    ledger, runtime, _, _, client = setup(tmp_path)

    class FailingProvider(Provider):
        def forecast(self, value):
            if domain_error:
                raise DomainError(
                    "execution_error",
                    {
                        "message": PRIVATE,
                        "token": PRIVATE,
                        "nested": {"details": PRIVATE},
                        "reason": {"message": PRIVATE},
                    },
                )
            raise RuntimeError(PRIVATE)

    job_id, _ = configured(runtime, client, FailingProvider())
    Worker(runtime, JobQueue(ledger)).run_due(T)
    persisted = ledger.events_after(0, 1000)
    assert PRIVATE in json.dumps([e.model_dump(mode="json") for e in persisted])
    events = client.get("/v1/events?limit=1000")
    stream = client.get("/v1/events/stream?follow=false")
    assert events.status_code == stream.status_code == 200
    if surface != "mcp":
        assert PRIVATE not in (events.text if surface == "http" else stream.text)
    visible = events.json()
    assert [(e["event_id"], e["cursor"]) for e in visible] == [
        (e.event_id, e.cursor) for e in persisted
    ]
    for original, event in zip(persisted, visible):
        if original.kind == "run_failed":
            assert event["payload"]["error"]["code"] == "execution_error"
            assert event["payload"]["node_id"] == "model"
            assert event["payload"]["provider_id"] == "controlled"
        else:
            assert event == original.model_dump(mode="json")
    sse = [
        json.loads(line[6:])
        for line in stream.text.splitlines()
        if line.startswith("data: ")
    ]
    assert sse == visible

    if surface != "mcp":
        assert ledger.events_after(0, 1000) == persisted
        return

    # Real SDK tool -> real authenticated ASGI API; no source grant is supplied.
    mcp = pytest.importorskip("mcp")
    from forecast_anything.mcp_adapter import server
    from forecast_anything.mcp_adapter.client import CoreClient
    from forecast_anything.mcp_adapter.config import McpConfig

    monkeypatch.setattr(
        server,
        "CoreClient",
        lambda cfg: CoreClient(cfg, transport=httpx.ASGITransport(app=client.app)),
    )

    async def read():
        async with mcp.Client(
            server.create_server(McpConfig(workspace_token="test-token"))
        ) as connection:
            result = await connection.call_tool("get_events", {"limit": 1000})
            assert not result.is_error
            assert PRIVATE not in result.content[0].text
            data = result.structured_content["data"]
            assert data["events"] == visible
            assert data["cursor"] == persisted[-1].cursor
            job = await connection.call_tool("get_job", {"job_id": job_id})
            assert not job.is_error

    asyncio.run(read())
    # The public boundary must cover already stored rows, leaving diagnostics intact.
    assert ledger.events_after(0, 1000) == persisted


def test_job_status_redacts_provider_capabilities_domain_error(tmp_path, monkeypatch):
    ledger, runtime, _, _, client = setup(tmp_path)
    provider = Provider()
    job_id, _ = configured(runtime, client, provider)

    def private_capabilities():
        raise DomainError(
            "provider_contract_changed",
            {"message": PRIVATE, "token": PRIVATE, "nested": {"message": PRIVATE}},
        )

    monkeypatch.setattr(provider, "capabilities", private_capabilities)
    for attempt in range(3):
        now = T + timedelta(seconds=31 * attempt)
        runtime.clock = ledger.clock = lambda: now
        Worker(runtime, JobQueue(ledger)).run_due(now, limit=1)
    assert PRIVATE in json.dumps(JobQueue(ledger).history(job_id))
    response = client.get(f"/v1/jobs/{job_id}")
    assert response.status_code == 200
    assert PRIVATE not in response.text
    assert response.json()["error"]["code"] == "provider_contract_changed"
