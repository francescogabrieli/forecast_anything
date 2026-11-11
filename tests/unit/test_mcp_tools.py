"""MCP tool discovery, protocol validation and response boundaries."""

import asyncio

import httpx
import pytest
from mcp_tool_fixtures import (
    CANDIDATE,
    FORECAST,
    GRAPH,
    JOB,
    NAMES,
    connected,
    module,
    payload,
)

from forecast_anything.mcp_adapter.client import CoreClient
from forecast_anything.mcp_adapter.config import McpConfig

MUTATIONS = {
    "confirm_csv_source",
    "register_csv_source",
    "get_source_profile",
    "refresh_source",
    "submit_forecast",
    "submit_configured_forecast",
    "submit_backtest",
    "submit_evaluation",
    "create_watch",
    "update_watch",
    "update_question",
    "set_source_subscription",
    "create_webhook_subscription",
    "update_webhook_subscription",
    "create_question",
    "revise_question",
    "link_question_reference",
    "create_operation",
    "update_operation",
    "submit_operation",
    "resume_operation",
}


def test_discovery_has_typed_schemas_and_honest_annotations(monkeypatch):
    async def check():
        async with connected(
            monkeypatch, lambda request: pytest.fail("discovery made an HTTP request")
        ) as client:
            catalog = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert set(catalog) == NAMES
        for name, tool in catalog.items():
            assert tool.input_schema["type"] == "object"
            assert tool.input_schema["additionalProperties"] is False
            assert tool.output_schema["type"] == "object"
            assert "data" in tool.output_schema["properties"]
            assert tool.annotations.read_only_hint is (name not in MUTATIONS)
            assert tool.annotations.open_world_hint is (
                name
                in {
                    "get_source_profile",
                    "refresh_source",
                    "submit_configured_forecast",
                    "submit_backtest",
                    "create_watch",
                    "set_source_subscription",
                    "create_webhook_subscription",
                    "update_webhook_subscription",
                    "submit_operation",
                    "resume_operation",
                }
            )
            assert tool.annotations.idempotent_hint is (
                name not in {"register_csv_source", "get_source_profile"}
            )
        assert set(catalog["submit_forecast"].input_schema["required"]) == {
            "candidate_id",
            "snapshot_ids",
            "as_of",
            "key",
        }
        assert set(catalog["submit_evaluation"].input_schema["properties"]) == {
            "run_id",
            "actuals_snapshot_id",
            "key",
        }
        assert "GraphSpec" in catalog["get_candidate"].output_schema["$defs"]
        assert "OperatorContract" in catalog["get_capabilities"].output_schema["$defs"]
        assert set(catalog["create_watch"].input_schema["required"]) == {
            "candidate_id",
            "next_due_at",
        }
        assert set(catalog["update_watch"].input_schema["required"]) == {"watch_id"}
        assert set(catalog["update_question"].input_schema["properties"]) == {
            "question_id",
            "title",
            "status",
            "muted",
            "priority",
        }
        assert (
            catalog["create_webhook_subscription"].annotations.read_only_hint is False
        )
        assert (
            "secret"
            not in catalog["list_webhook_subscriptions"].output_schema["$defs"][
                "WebhookSubscription"
            ]["properties"]
        )
        assert "WatchHistoryPage" in catalog["get_watch_history"].output_schema["$defs"]
        assert catalog["create_watch"].annotations.open_world_hint is True
        assert (
            "operational"
            in catalog["get_watch"].output_schema["$defs"]["WatchView"]["properties"]
        )

    asyncio.run(check())


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("list_sources", {"limit": 0}),
        ("list_sources", {"offset": -1}),
        ("get_events", {"limit": 1001}),
        ("get_events", {"after": -1}),
        ("list_watches", {"limit": 0}),
        ("get_watch_history", {"watch_id": "w", "limit": 101}),
        ("create_watch", {"candidate_id": "c", "next_due_at": "2026-10-24"}),
        ("update_watch", {"watch_id": "w"}),
        ("update_watch", {"watch_id": "w", "muted": None}),
        ("list_inbox_events", {"limit": 101}),
        ("list_webhook_deliveries", {"subscription_id": "s", "limit": 0}),
        ("set_source_subscription", {"source_id": "sales", "active": "false"}),
        ("update_question", {"question_id": "q", "priority": 6}),
        ("update_question", {"question_id": "q", "muted": None}),
        ("get_graph", {"graph_id": "x", "version": 0}),
        ("get_graph", {"graph_id": "x", "version": True}),
        ("submit_forecast", {**FORECAST, "as_of": "2026-10-24"}),
        ("submit_forecast", {k: v for k, v in FORECAST.items() if k != "key"}),
        ("submit_forecast", {**FORECAST, "snapshot_ids": {}}),
        (
            "register_csv_source",
            {
                "spec": {
                    "location": "/private/SECRET-INPUT",
                    "refresh_seconds": "SECRET-INPUT",
                }
            },
        ),
        (
            "submit_evaluation",
            {
                "run_id": "r",
                "actuals_snapshot_id": "s",
                "key": "k",
                "metrics": {"SECRET-INPUT": 1},
            },
        ),
        ("get_job", {"job_id": {"SECRET-INPUT": "SECRET-INPUT"}}),
        ("get_job", {"job_id": "x", "SECRET-INPUT": "SECRET-INPUT"}),
    ],
)
def test_protocol_rejects_invalid_input_without_leaking_values(
    monkeypatch, name, arguments
):
    async def check():
        async with connected(
            monkeypatch, lambda request: pytest.fail("invalid input reached HTTP")
        ) as client:
            result = await client.call_tool(name, arguments)
        data = payload(result)
        assert data["code"] == "validation_error"
        assert "SECRET-INPUT" not in result.model_dump_json()
        for error in data.get("errors", []):
            assert set(error) == {"loc", "type"}

    asyncio.run(check())


@pytest.mark.parametrize(
    ("name", "arguments", "path", "response"),
    [
        ("get_job", {"job_id": "a/b?x#z%"}, b"/v1/jobs/a%2Fb%3Fx%23z%25", JOB),
        (
            "get_candidate",
            {"candidate_id": "a/b?x#z%"},
            b"/v1/candidates/a%2Fb%3Fx%23z%25",
            CANDIDATE,
        ),
        (
            "get_graph",
            {"graph_id": "a/b?x#z%", "version": 2},
            b"/v1/graphs/a%2Fb%3Fx%23z%25?version=2",
            GRAPH,
        ),
        (
            "get_snapshot",
            {"snapshot_id": "a/b?x#z%"},
            b"/v1/snapshots/a%2Fb%3Fx%23z%25",
            {
                "snapshot_id": "s",
                "as_of": "2026-10-24T00:00:00Z",
                "observations": [],
                "assumptions": [],
            },
        ),
        (
            "list_run_evaluations",
            {"run_id": "a/b?x#z%"},
            b"/v1/runs/a%2Fb%3Fx%23z%25/evaluations",
            [],
        ),
    ],
)
def test_identifiers_are_single_encoded_segments(
    monkeypatch, name, arguments, path, response
):
    def respond(request):
        assert request.url.raw_path == path
        return httpx.Response(200, json=response)

    async def check():
        async with connected(monkeypatch, respond) as client:
            assert payload(await client.call_tool(name, arguments))["ok"]

    asyncio.run(check())


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "unauthorized"),
        (404, "not_found"),
        (422, "validation_error"),
        (500, "upstream_error"),
    ],
)
def test_upstream_errors_do_not_become_empty_success_or_leak_bodies(
    monkeypatch, status, code
):
    async def check():
        async with connected(
            monkeypatch,
            lambda request: httpx.Response(
                status, text="/private/SECRET-TOKEN source instruction"
            ),
        ) as client:
            result = await client.call_tool("list_run_evaluations", {"run_id": "r"})
            assert payload(result)["code"] == code
            assert "SECRET-TOKEN" not in result.model_dump_json()

    asyncio.run(check())


def test_malformed_typed_upstream_data_is_sanitized(monkeypatch):
    async def check():
        async with connected(
            monkeypatch,
            lambda request: httpx.Response(
                200, json={**JOB, "attempt": "/private/SECRET-TOKEN"}
            ),
        ) as client:
            result = await client.call_tool("get_job", {"job_id": "j"})
            assert payload(result)["code"] == "invalid_response"
            assert "SECRET-TOKEN" not in result.model_dump_json()

    asyncio.run(check())


@pytest.mark.parametrize("size", [20000, 40000, 70000])
def test_total_serialized_result_including_text_duplication_is_bounded(
    monkeypatch, size
):
    async def check():
        snapshot = {
            "snapshot_id": "s",
            "as_of": "2026-10-24T00:00:00Z",
            "observations": [],
            "assumptions": ["x" * size],
        }
        async with connected(
            monkeypatch, lambda request: httpx.Response(200, json=snapshot)
        ) as client:
            result = await client.call_tool("get_snapshot", {"snapshot_id": "s"})
            assert len(result.model_dump_json(by_alias=True).encode()) <= 65536
            if size >= 40000:
                assert payload(result) == {"ok": False, "code": "result_too_large"}
                assert "data" not in payload(result)
            else:
                assert payload(result)["ok"]

    asyncio.run(check())


def test_async_http_client_is_closed_when_protocol_disconnects(monkeypatch):
    clients = []

    class ObservedClient(CoreClient):
        def __init__(self, config):
            super().__init__(
                config,
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, json=JOB)
                ),
            )
            clients.append(self)

    async def check():
        server_module = module()
        monkeypatch.setattr(server_module, "CoreClient", ObservedClient)
        async with pytest.importorskip("mcp").Client(
            server_module.create_server(McpConfig(workspace_token="t"))
        ) as client:
            assert payload(await client.call_tool("get_job", {"job_id": "j"}))["ok"]
            assert not clients[0]._client.is_closed
        assert clients[0]._client.is_closed

    asyncio.run(check())


@pytest.mark.parametrize(
    "params",
    [
        {"name": "get_job", "arguments": "SECRET-INPUT"},
        {"name": "get_job", "arguments": ["SECRET-INPUT"]},
        {"name": {"SECRET-INPUT": "SECRET-INPUT"}, "arguments": {}},
        {"arguments": {"job_id": "SECRET-INPUT"}},
    ],
)
def test_malformed_protocol_tool_parameters_are_safe_errors(monkeypatch, params):
    async def check():
        sdk = pytest.importorskip("mcp")
        async with connected(
            monkeypatch, lambda request: pytest.fail("malformed tool call reached HTTP")
        ) as client:
            from mcp.shared.exceptions import MCPError

            with pytest.raises(MCPError) as error:
                await client.session.send_request(
                    sdk.types.Request[dict, str](method="tools/call", params=params),
                    sdk.types.CallToolResult,
                )
            assert error.value.code == -32602
            assert error.value.message == "Invalid request parameters"
            assert error.value.data == ""
            assert "SECRET-INPUT" not in str(error.value)

    asyncio.run(check())


def test_output_schema_requires_success_data_or_error_code(monkeypatch):
    async def check():
        jsonschema = pytest.importorskip("jsonschema")
        async with connected(
            monkeypatch, lambda request: httpx.Response(200, json=JOB)
        ) as client:
            catalog = {tool.name: tool for tool in (await client.list_tools()).tools}
            schema = catalog["get_job"].output_schema
            jsonschema.validate(
                payload(await client.call_tool("get_job", {"job_id": "j"})), schema
            )
            jsonschema.validate({"ok": False, "code": "not_found"}, schema)
            for invalid in (
                {"ok": True},
                {"ok": False},
                {"ok": True, "data": JOB, "code": "not_found"},
                {"ok": False, "code": "not_found", "data": JOB},
            ):
                with pytest.raises(jsonschema.ValidationError):
                    jsonschema.validate(invalid, schema)

    asyncio.run(check())


@pytest.mark.parametrize(
    ("name", "arguments", "response"),
    [
        (
            "get_capabilities",
            {},
            {
                "providers": {
                    "custom": {
                        "provider_id": "custom",
                        "provider_revision": "pin",
                        "representations": ["point"],
                        "supports_known_future": False,
                    }
                },
                "operators": {},
                "templates": ["custom-template"],
            },
        ),
        (
            "get_run",
            {"run_id": "r"},
            {
                "run_id": "r",
                "graph_id": "g",
                "graph_version": 4,
                "as_of": "2026-10-24T00:00:00Z",
                "snapshot_ids": ["s"],
                "requested_provider": {"f": "seasonal_naive"},
                "actual_provider": {"f": "seasonal_naive"},
                "state": "completed",
                "results": {},
                "evidence_ids": ["recorded-evidence"],
                "scenario_id": None,
                "parent_run_id": None,
            },
        ),
        (
            "get_evaluation",
            {"evaluation_id": "e"},
            {
                "evaluation_id": "e",
                "run_id": "r",
                "actuals_snapshot_id": "a",
                "status": "evaluated",
                "metrics": {"mae": 3},
                "origin_count": 1,
                "assumptions": ["recorded assumption"],
                "discovery": None,
            },
        ),
    ],
)
def test_read_tools_preserve_installed_contracts_and_recorded_evidence(
    monkeypatch, name, arguments, response
):
    async def check():
        async with connected(
            monkeypatch, lambda request: httpx.Response(200, json=response)
        ) as client:
            assert payload(await client.call_tool(name, arguments))["data"] == response

    asyncio.run(check())
