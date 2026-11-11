"""MCP source access, registration and guided confirmation."""

import asyncio
import json

import httpx
import pytest
from mcp_tool_fixtures import (
    PROFILE,
    REGISTRATION,
    connected,
    payload,
)

from forecast_anything.mcp_adapter.config import McpConfig


@pytest.mark.parametrize("name", ["get_source_profile", "refresh_source"])
def test_known_source_id_does_not_grant_read_or_refresh_access(monkeypatch, name):
    async def check():
        async with connected(
            monkeypatch, lambda request: pytest.fail("forbidden source reached HTTP")
        ) as client:
            arguments = {"source_id": "private-network"}
            if name == "refresh_source":
                arguments["key"] = "caller-key"
            assert (
                payload(await client.call_tool(name, arguments))["code"]
                == "source_forbidden"
            )

    asyncio.run(check())


def test_operator_allowlist_allows_profile_and_preserves_refresh_key(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200, json=REGISTRATION if request.method == "POST" else PROFILE
        )

    async def check():
        async with connected(
            monkeypatch,
            respond,
            config=McpConfig(workspace_token="t", source_ids=frozenset({"sales"})),
        ) as client:
            assert (
                payload(
                    await client.call_tool("get_source_profile", {"source_id": "sales"})
                )["data"]["source_id"]
                == "sales"
            )
            assert (
                payload(
                    await client.call_tool(
                        "refresh_source",
                        {"source_id": "sales", "key": "caller/refresh/key"},
                    )
                )["data"]["job_id"]
                == "job-1"
            )
        assert requests[0].url.path == "/v1/sources/sales/profile"
        assert json.loads(requests[1].content) == {"key": "caller/refresh/key"}

    asyncio.run(check())


def test_registration_guards_and_process_local_source_permission(monkeypatch, tmp_path):
    location = tmp_path / "private.csv"
    location.write_text("synthetic")
    calls = []

    def respond(request):
        calls.append(request)
        return (
            httpx.Response(201, json=REGISTRATION)
            if request.method == "POST"
            else httpx.Response(200, json=PROFILE)
        )

    async def check():
        config = McpConfig(workspace_token="t", csv_roots=(tmp_path,))
        spec = {
            "source_id": "sales",
            "kind": "csv",
            "location": str(location),
            "mapping": {"series_id": "sales"},
            "refresh_seconds": 60,
        }
        async with connected(monkeypatch, respond, config=config) as client:
            for changed in (
                {"kind": "http_json"},
                {"secret_ref": "PRIVATE-SECRET"},
                {"location": "/etc/passwd"},
            ):
                result = await client.call_tool(
                    "register_csv_source", {"spec": {**spec, **changed}}
                )
                assert payload(result)["code"] == "source_forbidden"
                assert str(location) not in result.model_dump_json()
                assert "PRIVATE-SECRET" not in result.model_dump_json()
            assert payload(
                await client.call_tool("register_csv_source", {"spec": spec})
            )["ok"]
            assert payload(
                await client.call_tool("get_source_profile", {"source_id": "sales"})
            )["ok"]
        assert len(calls) == 2
        assert json.loads(calls[0].content)["mapping"] == {"series_id": "sales"}
        async with connected(
            monkeypatch,
            lambda request: pytest.fail("permission persisted"),
            config=config,
        ) as client:
            assert (
                payload(
                    await client.call_tool("get_source_profile", {"source_id": "sales"})
                )["code"]
                == "source_forbidden"
            )

    asyncio.run(check())


def test_list_sources_is_stable_bounded_metadata_pagination(monkeypatch):
    sources = [
        {"source_id": name, "revision": "r", "kind": "csv", "refresh_seconds": 60}
        for name in ["z", "a", "m"]
    ]

    async def check():
        async with connected(
            monkeypatch, lambda request: httpx.Response(200, json=sources)
        ) as client:
            first = payload(await client.call_tool("list_sources", {"limit": 2}))[
                "data"
            ]
            assert [s["source_id"] for s in first["sources"]] == ["a", "m"]
            assert first["next_offset"] == 2
            last = payload(
                await client.call_tool("list_sources", {"offset": 2, "limit": 2})
            )["data"]
            assert last["next_offset"] is None
            assert [s["source_id"] for s in last["sources"]] == ["z"]

    asyncio.run(check())


def test_guided_confirmation_lost_response_recovers_grant_only_in_original_session(
    monkeypatch, tmp_path
):
    path = tmp_path / "source.csv"
    path.write_text("date,value\n2026-01-01,1\n")
    first_session = None
    requests = 0

    def respond(request):
        nonlocal first_session, requests
        if request.url.path == "/v1/sources/csv-confirm":
            data = json.loads(request.content)
            requests += 1
            if requests == 1:
                first_session = data["adapter_session"]
                raise httpx.ReadError("lost response", request=request)
            return httpx.Response(
                201,
                json={
                    **REGISTRATION,
                    "replayed": True,
                    "session_grant": data["adapter_session"] == first_session,
                },
            )
        return httpx.Response(200, json=PROFILE)

    async def check():
        config = McpConfig(workspace_token="t", csv_roots=(tmp_path,))
        args = {
            "spec": {
                "source_id": "sales",
                "kind": "csv",
                "location": str(path),
                "refresh_seconds": 60,
            },
            "key": "one",
            "proposal_version": "a" * 64,
            "as_of": "2026-10-23T12:00:00Z",
        }
        async with connected(monkeypatch, respond, config=config) as client:
            assert (
                payload(await client.call_tool("confirm_csv_source", args))["code"]
                == "network_error"
            )
            assert payload(await client.call_tool("confirm_csv_source", args))["ok"]
            assert payload(
                await client.call_tool("get_source_profile", {"source_id": "sales"})
            )["ok"]
        async with connected(monkeypatch, respond, config=config) as client:
            assert payload(await client.call_tool("confirm_csv_source", args))["ok"]
            assert (
                payload(
                    await client.call_tool("get_source_profile", {"source_id": "sales"})
                )["code"]
                == "source_forbidden"
            )

    asyncio.run(check())
