"""MCP continuity, watch lifecycle and event cursors."""

import asyncio
import json

import httpx
import pytest
from mcp_tool_fixtures import (
    CANDIDATE,
    WATCH,
    connected,
    payload,
)

from forecast_anything.mcp_adapter.config import McpConfig

WATCH_CHANGE = {
    "watch_id": "watch-1",
    "candidate_id": "candidate-1",
    "template_id": "next_value",
    "question": "explicit",
    "dependencies": ["sales"],
    "previous_run_id": "run-1",
    "current_run_id": "run-2",
    "changes": [],
    "added_targets": [],
    "removed_targets": [],
    "common_target_count": 1,
    "incomparable": [],
    "new_snapshot_ids": [],
    "new_evidence_ids": [],
    "explanation": "Observed differences do not establish causal effects.",
}


def test_continuity_tools_delegate_without_exposing_webhook_secrets(monkeypatch):
    calls = []
    subscription = {
        "subscription_id": "sub-1",
        "target_url": "https://hooks.example.test/forecast",
        "active": True,
        "created_at": "2026-11-08T00:00:00Z",
    }

    def respond(request):
        calls.append(request)
        path = request.url.path
        if path == "/v1/inbox":
            assert request.url.params["question_id"] == "q-1"
            return httpx.Response(
                200, json={"events": [], "next_offset": None, "total_count": 0}
            )
        if path == "/v1/source-subscriptions":
            return httpx.Response(200, json={"subscriptions": [], "next_offset": None})
        if path == "/v1/source-subscriptions/sales":
            assert request.method == "PUT"
            assert json.loads(request.content) == {"active": False}
            return httpx.Response(
                200,
                json={
                    "source_id": "sales",
                    "active": False,
                    "created_at": "2026-11-08T00:00:00Z",
                    "updated_at": "2026-11-08T00:00:00Z",
                },
            )
        if path == "/v1/webhook-subscriptions" and request.method == "POST":
            assert json.loads(request.content)["secret"] == "write-only"
            return httpx.Response(201, json=subscription)
        if path == "/v1/webhook-subscriptions":
            return httpx.Response(
                200, json={"subscriptions": [subscription], "next_offset": None}
            )
        if path == "/v1/webhook-subscriptions/sub-1":
            assert request.method == "PATCH"
            assert json.loads(request.content) == {"active": False}
            return httpx.Response(200, json={**subscription, "active": False})
        if path == "/v1/webhook-subscriptions/sub-1/deliveries":
            return httpx.Response(200, json={"deliveries": [], "next_offset": None})
        raise AssertionError(f"unexpected request: {request.method} {path}")

    async def check():
        async with connected(monkeypatch, respond) as client:
            inbox_result = payload(
                await client.call_tool("list_inbox_events", {"question_id": "q-1"})
            )
            assert inbox_result["ok"], inbox_result
            assert inbox_result["data"]["total_count"] == 0
            assert (
                payload(await client.call_tool("list_source_subscriptions", {}))[
                    "data"
                ]["subscriptions"]
                == []
            )
            assert (
                payload(
                    await client.call_tool(
                        "set_source_subscription",
                        {"source_id": "sales", "active": False},
                    )
                )["data"]["active"]
                is False
            )
            created = payload(
                await client.call_tool(
                    "create_webhook_subscription",
                    {"target_url": subscription["target_url"], "secret": "write-only"},
                )
            )
            assert "secret" not in created["data"]
            assert payload(await client.call_tool("list_webhook_subscriptions", {}))[
                "data"
            ]["subscriptions"] == [subscription]
            assert (
                payload(
                    await client.call_tool(
                        "update_webhook_subscription",
                        {"subscription_id": "sub-1", "active": False},
                    )
                )["data"]["active"]
                is False
            )
            assert (
                payload(
                    await client.call_tool(
                        "list_webhook_deliveries", {"subscription_id": "sub-1"}
                    )
                )["data"]["deliveries"]
                == []
            )

    asyncio.run(check())
    assert len(calls) == 7


def test_watch_tools_preserve_ids_controls_pages_and_run_lineage(monkeypatch):
    calls = []
    history = {
        "entries": [
            {
                "sequence": 1,
                "event_id": "created",
                "occurred_at": "2026-10-24T00:00:00Z",
                "event": {"kind": "created"},
                "watch": WATCH,
            }
        ],
        "next_offset": None,
    }

    def respond(request):
        calls.append(request)
        path = request.url.path
        if request.method == "GET" and path == "/v1/candidates/candidate-1":
            return httpx.Response(200, json=CANDIDATE)
        if request.method == "POST" and path == "/v1/watches":
            assert json.loads(request.content) == {
                "candidate_id": "candidate-1",
                "next_due_at": "2026-10-25T00:00:00Z",
            }
            return httpx.Response(201, json=WATCH)
        if request.method == "GET" and path == "/v1/watches":
            return httpx.Response(200, json=[{**WATCH, "watch_id": "watch-2"}, WATCH])
        if request.method == "GET" and path == "/v1/watches/watch-1":
            return httpx.Response(200, json=WATCH)
        if request.method == "PATCH" and path == "/v1/watches/watch-1":
            assert json.loads(request.content) == {"muted": False, "priority": 5}
            return httpx.Response(200, json={**WATCH, "priority": 5})
        if request.method == "GET" and path == "/v1/watches/watch-1/history":
            assert dict(request.url.params) == {"offset": "3", "limit": "4"}
            return httpx.Response(200, json=history)
        if request.method == "GET" and path == "/v1/watches/watch-1/changes":
            assert dict(request.url.params) == {
                "previous_run_id": "run-1",
                "current_run_id": "run-2",
            }
            return httpx.Response(200, json=WATCH_CHANGE)
        pytest.fail(f"unexpected watch request: {request.method} {path}")

    async def check():
        async with connected(
            monkeypatch,
            respond,
            config=McpConfig(
                workspace_token="private-token", source_ids=frozenset({"sales"})
            ),
        ) as client:
            created_result = payload(
                await client.call_tool(
                    "create_watch",
                    {
                        "candidate_id": "candidate-1",
                        "next_due_at": "2026-10-25T00:00:00Z",
                    },
                )
            )
            assert created_result["ok"], created_result
            created = created_result["data"]
            assert created["watch_id"] == "watch-1"
            page = payload(await client.call_tool("list_watches", {"limit": 1}))["data"]
            assert [item["watch_id"] for item in page["watches"]] == ["watch-1"]
            assert page["next_offset"] == 1
            assert (
                payload(await client.call_tool("get_watch", {"watch_id": "watch-1"}))[
                    "data"
                ]["watch_id"]
                == "watch-1"
            )
            assert (
                payload(
                    await client.call_tool(
                        "update_watch",
                        {"watch_id": "watch-1", "muted": False, "priority": 5},
                    )
                )["data"]["priority"]
                == 5
            )
            history_page = payload(
                await client.call_tool(
                    "get_watch_history",
                    {"watch_id": "watch-1", "offset": 3, "limit": 4},
                )
            )["data"]
            assert history_page["next_offset"] is None
            assert history_page["entries"][0]["watch"]["watch_id"] == "watch-1"
            assert history_page["entries"][0]["watch"]["operational"] is False
            summary = payload(
                await client.call_tool(
                    "summarize_watch_change",
                    {
                        "watch_id": "watch-1",
                        "previous_run_id": "run-1",
                        "current_run_id": "run-2",
                    },
                )
            )["data"]
            assert summary == WATCH_CHANGE
        assert calls[0].url.path == "/v1/candidates/candidate-1"
        assert calls[1].url.path == "/v1/watches"
        assert dict(calls[2].url.params) == {}
        assert len(calls) == 7

    asyncio.run(check())


def test_create_watch_requires_source_allowlist_before_mutation(monkeypatch):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=CANDIDATE)

    async def check():
        async with connected(monkeypatch, respond) as client:
            result = payload(
                await client.call_tool(
                    "create_watch",
                    {
                        "candidate_id": "candidate-1",
                        "next_due_at": "2026-10-25T00:00:00Z",
                    },
                )
            )
            assert result == {"ok": False, "code": "source_forbidden"}
        assert len(calls) == 1
        assert calls[0].url.path == "/v1/candidates/candidate-1"

    asyncio.run(check())


def test_events_return_last_durable_cursor(monkeypatch):
    def respond(request):
        assert dict(request.url.params) == {"after": "3", "limit": "2"}
        return httpx.Response(
            200,
            json=[
                {
                    "cursor": 5,
                    "event_id": "e5",
                    "kind": "run",
                    "run_id": "r",
                    "payload": {},
                },
                {
                    "cursor": 8,
                    "event_id": "e8",
                    "kind": "run",
                    "run_id": "r",
                    "payload": {},
                },
            ],
        )

    async def check():
        async with connected(monkeypatch, respond) as client:
            assert (
                payload(await client.call_tool("get_events", {"after": 3, "limit": 2}))[
                    "data"
                ]["cursor"]
                == 8
            )
        async with connected(
            monkeypatch, lambda request: httpx.Response(200, json=[])
        ) as client:
            assert payload(await client.call_tool("get_events", {"after": 8}))[
                "data"
            ] == {"events": [], "cursor": 8}

    asyncio.run(check())
