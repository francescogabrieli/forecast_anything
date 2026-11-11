"""MCP candidate forecasts and evaluation jobs."""

import asyncio
import json

import httpx
import pytest
from mcp_tool_fixtures import (
    CANDIDATE,
    FORECAST,
    GRAPH,
    JOB,
    connected,
    payload,
)


def test_submit_forecast_uses_frozen_graph_explicit_snapshots_origin_and_key(
    monkeypatch,
):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=CANDIDATE if request.method == "GET" else JOB)

    async def check():
        async with connected(monkeypatch, respond) as client:
            assert (
                payload(await client.call_tool("submit_forecast", FORECAST))["data"]
                == JOB
            )
        assert calls[0].url.path == "/v1/candidates/candidate-1"
        assert calls[1].url.path == "/v1/jobs"
        assert json.loads(calls[1].content) == {
            "kind": "run",
            "key": "caller/forecast/key",
            "graph": GRAPH,
            "snapshot_ids": {"sales": "snapshot-1"},
            "as_of": "2026-10-24T00:00:00Z",
            "previous_run_id": None,
        }

    asyncio.run(check())


@pytest.mark.parametrize(
    "patch", [{"executable": False}, {"unresolved": ["unsupported_provider"]}]
)
def test_unsupported_candidate_never_submits_work(monkeypatch, patch):
    def respond(request):
        assert request.method == "GET"
        return httpx.Response(200, json={**CANDIDATE, **patch})

    async def check():
        async with connected(monkeypatch, respond) as client:
            assert (
                payload(await client.call_tool("submit_forecast", FORECAST))["code"]
                == "candidate_not_executable"
            )

    asyncio.run(check())


@pytest.mark.parametrize(
    "bindings",
    [{"wrong": "snapshot-1"}, {"sales": "snapshot-1", "extra": "snapshot-2"}],
)
def test_submit_forecast_requires_exact_declared_source_bindings(monkeypatch, bindings):
    def respond(request):
        assert request.method == "GET"
        return httpx.Response(200, json=CANDIDATE)

    async def check():
        async with connected(monkeypatch, respond) as client:
            assert (
                payload(
                    await client.call_tool(
                        "submit_forecast", {**FORECAST, "snapshot_ids": bindings}
                    )
                )["code"]
                == "invalid_snapshot_bindings"
            )

    asyncio.run(check())


def test_evaluation_uses_existing_job_contract_only(monkeypatch):
    def respond(request):
        assert request.url.path == "/v1/jobs"
        assert json.loads(request.content) == {
            "kind": "evaluation",
            "key": "caller-evaluation",
            "run_id": "run-1",
            "actuals_snapshot_id": "actuals-1",
        }
        return httpx.Response(202, json=JOB)

    async def check():
        async with connected(monkeypatch, respond) as client:
            assert (
                payload(
                    await client.call_tool(
                        "submit_evaluation",
                        {
                            "run_id": "run-1",
                            "actuals_snapshot_id": "actuals-1",
                            "key": "caller-evaluation",
                        },
                    )
                )["data"]
                == JOB
            )

    asyncio.run(check())
