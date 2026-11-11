"""MCP browser links and contextual views."""

import asyncio
import json

import httpx
from mcp_tool_fixtures import (
    connected,
    payload,
)


def test_browser_link_is_bound_to_stored_workspace_and_contains_no_credentials(
    monkeypatch,
):
    seen = []

    def respond(request):
        seen.append(request.url.path)
        if request.url.path == "/v1/workspace":
            return httpx.Response(200, json={"workspace_id": "a" * 32})
        if request.url.path == "/v1/resource-identities/run/run-1":
            return httpx.Response(200, json={"kind": "run", "resource_id": "run-1"})
        return httpx.Response(404, json={})

    async def check():
        async with connected(monkeypatch, respond) as client:
            result = payload(
                await client.call_tool(
                    "get_browser_link",
                    {
                        "kind": "run",
                        "resource_id": "run-1",
                        "browser_url": "http://127.0.0.1:4173",
                    },
                )
            )
            assert result["ok"]
            assert (
                result["data"]["url"]
                == f"http://127.0.0.1:4173/#/w/{'a' * 32}/run/run-1"
            )
            assert "private-token" not in json.dumps(result)
            bad = payload(
                await client.call_tool(
                    "get_browser_link",
                    {
                        "kind": "run",
                        "resource_id": "run-1",
                        "browser_url": "https://evil.example/?token=secret",
                    },
                )
            )
            assert bad["code"] == "invalid_browser_url"
            assert "secret" not in json.dumps(bad)

    asyncio.run(check())
    assert seen == ["/v1/workspace", "/v1/resource-identities/run/run-1"]


def test_context_view_oversized_presentation_retains_browser_fallback(monkeypatch):
    presentation = {
        "run_id": "run-1",
        "primary_node_id": "model",
        "graph_id": "graph",
        "graph_version": 1,
        "as_of": "2026-10-23T12:00:00Z",
        "state": "completed",
        "snapshot_ids": [],
        "snapshot_ids_truncated": False,
        "providers": [],
        "providers_truncated": False,
        "points": [
            {
                "node_id": "model",
                "series_id": "sales",
                "timestamp": "2026-10-24T00:00:00Z",
                "unit": "u" * 70000,
                "representation": "point",
                "point": 3,
                "quantiles": {},
                "quantiles_truncated": False,
                "sample_count": 0,
            }
        ],
        "total_point_count": 1,
        "truncated": False,
    }

    def respond(request):
        if request.url.path == "/v1/workspace":
            return httpx.Response(200, json={"workspace_id": "a" * 32})
        if request.url.path == "/v1/resource-identities/run/run-1":
            return httpx.Response(200, json={"kind": "run", "resource_id": "run-1"})
        if request.url.path == "/v1/runs/run-1/presentation":
            return httpx.Response(200, json=presentation)
        return httpx.Response(404)

    async def check():
        async with connected(monkeypatch, respond) as client:
            result = await client.call_tool(
                "open_context_view",
                {
                    "kind": "run",
                    "resource_id": "run-1",
                    "browser_url": "http://127.0.0.1:4173",
                },
            )
            assert not result.is_error
            assert result.structured_content["data"]["presentation"] is None
            assert (
                result.structured_content["data"]["unavailable_reason"]
                == "result_too_large"
            )
            assert result.structured_content["data"]["browser_link"]["url"] == (
                f"http://127.0.0.1:4173/#/w/{'a' * 32}/run/run-1"
            )
            assert (
                result.structured_content["data"]["browser_link"]["url"]
                in result.content[0].text
            )
            assert len(result.model_dump_json(by_alias=True).encode()) <= 65536

    asyncio.run(check())


def test_context_view_api_limit_and_missing_identity(monkeypatch):
    def respond(request):
        if request.url.path == "/v1/workspace":
            return httpx.Response(200, json={"workspace_id": "b" * 32})
        if request.url.path == "/v1/resource-identities/run/run-1":
            return httpx.Response(200, json={"kind": "run", "resource_id": "run-1"})
        if request.url.path == "/v1/runs/run-1/presentation":
            return httpx.Response(200, content=b"x" * (1024 * 1024 + 1))
        return httpx.Response(404)

    async def check():
        async with connected(monkeypatch, respond) as client:
            args = {
                "kind": "run",
                "resource_id": "run-1",
                "browser_url": "http://127.0.0.1:4173",
            }
            result = await client.call_tool("open_context_view", args)
            assert not result.is_error
            data = result.structured_content["data"]
            assert data["unavailable_reason"] == "response_too_large"
            assert (
                data["browser_link"]["url"]
                == f"http://127.0.0.1:4173/#/w/{'b' * 32}/run/run-1"
            )
            assert data["browser_link"]["url"] in result.content[0].text
            missing = await client.call_tool(
                "open_context_view", {**args, "resource_id": "missing"}
            )
            assert (
                missing.is_error and missing.structured_content["code"] == "not_found"
            )

    asyncio.run(check())
