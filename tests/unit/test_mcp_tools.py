"""MCP wire contracts and real HTTP delegation, without provider inference."""

import asyncio
import importlib
import json
import os
import select
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from forecast_anything.mcp_adapter.client import CoreClient
from forecast_anything.mcp_adapter.config import McpConfig

ROOT = Path(__file__).resolve().parents[2]
NAMES = {
    "create_operation",
    "update_operation",
    "list_operations",
    "get_operation",
    "submit_operation",
    "resume_operation",
    "summarize_snapshot",
    "list_snapshot_series",
    "get_backtest_presentation",
    "get_forecast_presentation",
    "get_question_presentation",
    "create_question",
    "list_questions",
    "get_question",
    "update_question",
    "revise_question",
    "list_question_revisions",
    "get_question_revision",
    "link_question_reference",
    "list_question_references",
    "get_capabilities",
    "get_diagnostics",
    "list_sources",
    "preview_csv_source",
    "confirm_csv_source",
    "register_csv_source",
    "get_source_profile",
    "refresh_source",
    "get_job",
    "get_candidate",
    "submit_forecast",
    "submit_configured_forecast",
    "submit_backtest",
    "get_run",
    "get_graph",
    "get_snapshot",
    "list_run_evaluations",
    "get_evaluation",
    "submit_evaluation",
    "get_events",
    "get_backtest",
    "summarize_backtest",
    "list_backtest_origins",
    "create_watch",
    "list_watches",
    "get_watch",
    "update_watch",
    "get_watch_history",
    "summarize_watch_change",
}
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
    "create_question",
    "update_question",
    "revise_question",
    "link_question_reference",
    "create_operation",
    "update_operation",
    "submit_operation",
    "resume_operation",
}
JOB = {
    "job_id": "job-1",
    "state": "pending",
    "attempt": 0,
    "result": None,
    "error": None,
}
GRAPH = {
    "graph_id": "graph-1",
    "version": 2,
    "nodes": [
        {
            "node_id": "history",
            "kind": "source",
            "inputs": [],
            "config": {
                "source_id": "sales",
                "series_ids": ["sales"],
                "units": ["count"],
                "frequency": "1d",
            },
        },
        {
            "node_id": "forecast",
            "kind": "forecast",
            "inputs": ["history"],
            "config": {
                "provider": "seasonal_naive",
                "history": "history",
                "horizon": 1,
                "frequency": "1d",
                "relation_type": {"history": "statistical"},
            },
        },
    ],
}
CANDIDATE = {
    "candidate_id": "candidate-1",
    "template_id": "next_value",
    "source_ids": ["sales"],
    "graph": GRAPH,
    "reason": "explicit",
    "protocol_id": "protocol-1",
    "epoch_id": "epoch-1",
    "executable": True,
}
WATCH = {
    "watch_id": "watch-1",
    "candidate_id": "candidate-1",
    "lifecycle": "candidate",
    "quality": "provisional",
    "graph_id": "graph-1",
    "graph_version": 2,
    "policy_version": "discovery-v1",
    "next_due_at": "2026-10-25T00:00:00Z",
    "muted": False,
    "priority": 3,
    "candidate": CANDIDATE,
    "eligibility_decision": None,
    "source_snapshot_ids": [],
    "evidence_applicable": False,
    "reevaluation_required": True,
    "invalidated_evaluation_ids": [],
    "candidate_invalidated": False,
    "supersedes_watch_id": None,
    "operational": False,
}
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
PROFILE = {
    "source_id": "sales",
    "fields": {},
    "proposed_mapping": {},
    "unresolved": [],
    "assumptions": [],
    "sample_rows": [],
}
REGISTRATION = {
    "source_id": "sales",
    "revision": "revision-1",
    "kind": "csv",
    "refresh_seconds": 60,
    "profile": PROFILE,
    "job_id": "job-1",
    "epoch_id": "epoch-1",
}
FORECAST = {
    "candidate_id": "candidate-1",
    "snapshot_ids": {"sales": "snapshot-1"},
    "as_of": "2026-10-24T00:00:00Z",
    "key": "caller/forecast/key",
}


def module():
    pytest.importorskip("mcp")
    return importlib.import_module("forecast_anything.mcp_adapter.server")


@asynccontextmanager
async def connected(monkeypatch, handler, *, config=None):
    server_module = module()
    monkeypatch.setattr(
        server_module,
        "CoreClient",
        lambda cfg: CoreClient(cfg, transport=httpx.MockTransport(handler)),
    )
    async with pytest.importorskip("mcp").Client(
        server_module.create_server(
            config or McpConfig(workspace_token="private-token")
        )
    ) as client:
        yield client


def payload(result):
    assert result.structured_content is not None
    value = result.structured_content
    assert result.is_error is (not value["ok"])
    assert json.loads(result.content[0].text) == value
    return value


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


def test_cli_mcp_missing_extra_is_safe_and_baseline_does_not_import_sdk(tmp_path):
    blocker = tmp_path / "sitecustomize.py"
    blocker.write_text(
        "import sys\nclass Block:\n def find_spec(self, fullname, path=None, target=None):\n  if fullname == 'mcp' or fullname.startswith('mcp.'):\n   raise ModuleNotFoundError('blocked optional mcp', name='mcp')\nsys.meta_path.insert(0, Block())\n"
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(tmp_path), str(ROOT / "src")]),
    }
    baseline = subprocess.run(
        [sys.executable, "-m", "forecast_anything.cli", "run", "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert baseline.returncode == 0
    assert "--as-of" in baseline.stdout
    result = subprocess.run(
        [sys.executable, "-m", "forecast_anything.cli", "mcp"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "forecast-anything[mcp]" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_invalid_configuration_never_writes_to_protocol_stdout():
    pytest.importorskip("mcp")
    env = {
        **os.environ,
        "FORECAST_ANYTHING_WORKSPACE_TOKEN": "",
        "FORECAST_ANYTHING_MCP_API_URL": "https://private:SECRET-TOKEN@example.com/path",
    }
    result = subprocess.run(
        [sys.executable, "-m", "forecast_anything.cli", "mcp"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert json.loads(result.stderr) == {"ok": False, "code": "configuration_error"}
    assert "SECRET-TOKEN" not in result.stderr


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


def test_stdio_catalog_stdout_contains_only_jsonrpc_and_no_private_config():
    pytest.importorskip("mcp")
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "clientInfo": {"name": "wire-test", "version": "1"},
                "capabilities": {},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_job",
                "arguments": {"job_id": {"secret": "/private/SECRET-TOKEN"}},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "get_job", "arguments": "/private/SECRET-TOKEN"},
        },
    ]
    process = subprocess.Popen(
        [sys.executable, "-m", "forecast_anything.cli", "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "FORECAST_ANYTHING_WORKSPACE_TOKEN": "SECRET-TOKEN"},
    )
    output = bytearray()
    try:
        process.stdin.write(
            "".join(json.dumps(message) + "\n" for message in messages).encode()
        )
        process.stdin.flush()
        deadline = time.monotonic() + 10
        while output.count(b"\n") < 4:
            ready, _, _ = select.select(
                [process.stdout], [], [], max(0, deadline - time.monotonic())
            )
            assert ready, "MCP subprocess response timed out"
            chunk = os.read(process.stdout.fileno(), 65536)
            assert chunk, "MCP subprocess exited before all replies"
            output.extend(chunk)
        process.stdin.close()
        process.stdin = None
        tail, stderr = process.communicate(timeout=5)
        output.extend(tail)
        assert process.returncode == 0, stderr.decode()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    replies = {item["id"]: item for item in map(json.loads, output.splitlines())}
    assert set(replies) == {1, 2, 3, 4}
    assert set(item["name"] for item in replies[2]["result"]["tools"]) == NAMES
    assert replies[3]["result"]["isError"] is True
    assert replies[4]["error"]["code"] == -32602
    assert b"SECRET-TOKEN" not in output + stderr
    assert b"Traceback" not in stderr


SELECTION = {
    "provider": "seasonal_naive",
    "horizon": 2,
    "options": {"period": 2},
    "baseline_period": 1,
}
CONFIGURED = {
    "source_id": "sales",
    "snapshot_id": "stored-http-or-csv-vintage",
    "selection": SELECTION,
    "key": "caller/configured%key",
}
BACKTEST = {
    "source_id": "sales",
    "selection": SELECTION,
    "settings": {"max_origins_per_partition": 3, "origin_offset_seconds": 60},
    "key": "caller/backtest%key",
}


def test_evidence_catalog_uses_nested_contracts_and_fixed_kinds(monkeypatch):
    async def check():
        async with connected(
            monkeypatch, lambda request: pytest.fail("schema discovery reached HTTP")
        ) as client:
            catalog = {tool.name: tool for tool in (await client.list_tools()).tools}
        for name, fields in (
            (
                "submit_configured_forecast",
                {"key", "source_id", "snapshot_id", "selection"},
            ),
            (
                "submit_backtest",
                {"key", "source_id", "selection", "settings", "watch_id"},
            ),
        ):
            schema = catalog[name].input_schema
            assert set(schema["properties"]) == fields
            assert "selection" in schema["required"]
            assert schema["$defs"]["ForecastSelection"]["additionalProperties"] is False
            assert (
                schema["$defs"]["ForecastSelection"]["properties"]["horizon"]["maximum"]
                == 366
            )
        page = catalog["list_backtest_origins"].input_schema["properties"]
        assert page["offset"]["default"] == 0
        assert page["limit"]["default"] == 25
        assert page["limit"]["maximum"] == 50
        assert "BacktestReport" in catalog["get_backtest"].output_schema["$defs"]
        assert (
            "OriginOutcome" in catalog["list_backtest_origins"].output_schema["$defs"]
        )

    asyncio.run(check())


@pytest.mark.parametrize(
    ("name", "arguments", "kind"),
    [
        ("submit_configured_forecast", CONFIGURED, "configured_run"),
        ("submit_backtest", BACKTEST, "backtest"),
    ],
)
@pytest.mark.parametrize("option", [True, 1, 1.0])
def test_evidence_submissions_inject_kind_and_preserve_original_json_types(
    monkeypatch, name, arguments, kind, option
):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == "POST"
        assert request.url.raw_path == b"/v1/jobs"
        body = json.loads(request.content)
        expected = {
            **arguments,
            "kind": kind,
            "selection": {**SELECTION, "options": {"custom": option}},
        }
        assert body == expected
        assert type(body["selection"]["options"]["custom"]) is type(option)
        return httpx.Response(202, json=JOB)

    async def check():
        config = McpConfig(workspace_token="t", source_ids=frozenset({"sales"}))
        async with connected(monkeypatch, respond, config=config) as client:
            submitted = {
                **arguments,
                "selection": {**SELECTION, "options": {"custom": option}},
            }
            for _ in range(2):
                assert payload(await client.call_tool(name, submitted))["data"] == JOB
        assert len(calls) == 2
        assert calls[0].content == calls[1].content

    asyncio.run(check())


def test_backtest_permission_precedes_every_api_call_and_configured_needs_no_source_grant(
    monkeypatch,
):
    async def check():
        async with connected(
            monkeypatch, lambda request: pytest.fail("forbidden backtest reached HTTP")
        ) as client:
            assert payload(await client.call_tool("submit_backtest", BACKTEST)) == {
                "ok": False,
                "code": "source_forbidden",
            }
        async with connected(
            monkeypatch, lambda request: httpx.Response(202, json=JOB)
        ) as client:
            assert (
                payload(
                    await client.call_tool("submit_configured_forecast", CONFIGURED)
                )["data"]
                == JOB
            )

    asyncio.run(check())


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("submit_configured_forecast", {**CONFIGURED, "key": " key"}),
        ("submit_configured_forecast", {**CONFIGURED, "source_id": "sales "}),
        ("submit_configured_forecast", {**CONFIGURED, "snapshot_id": " vintage"}),
        ("submit_backtest", {**BACKTEST, "key": "key "}),
        ("submit_backtest", {**BACKTEST, "source_id": " sales"}),
        ("submit_backtest", {**BACKTEST, "kind": "run"}),
        ("submit_backtest", {**BACKTEST, "selection": {**SELECTION, "horizon": True}}),
        (
            "submit_backtest",
            {**BACKTEST, "selection": {**SELECTION, "baseline_period": 1.0}},
        ),
        (
            "submit_backtest",
            {**BACKTEST, "settings": {"max_origins_per_partition": 51}},
        ),
        ("submit_backtest", {**BACKTEST, "settings": {"origin_offset_seconds": True}}),
        ("get_backtest", {"backtest_id": " b"}),
        ("list_backtest_origins", {"backtest_id": "b", "offset": True}),
        ("list_backtest_origins", {"backtest_id": "b", "limit": 51}),
    ],
)
def test_evidence_arguments_reject_unsafe_identity_and_strict_boundaries(
    monkeypatch, name, arguments
):
    async def check():
        async with connected(
            monkeypatch,
            lambda request: pytest.fail("invalid evidence input reached HTTP"),
        ) as client:
            result = payload(await client.call_tool(name, arguments))
            assert result["code"] == "validation_error"
            assert result["errors"]

    asyncio.run(check())


@pytest.mark.parametrize("name", ["submit_configured_forecast", "submit_backtest"])
def test_evidence_nested_validation_never_echoes_private_keys_or_values(
    monkeypatch, name
):
    async def check():
        async with connected(
            monkeypatch,
            lambda request: pytest.fail("invalid evidence input reached HTTP"),
        ) as client:
            arguments = CONFIGURED if name == "submit_configured_forecast" else BACKTEST
            for selection in (
                {**SELECTION, "SECRET-KEY": "/private/SECRET-VALUE"},
                {
                    **SELECTION,
                    "horizon": "/private/SECRET-VALUE",
                    "options": ["SECRET-KEY"],
                },
            ):
                result = await client.call_tool(
                    name, {**arguments, "selection": selection}
                )
                assert payload(result)["code"] == "validation_error"
                assert "SECRET" not in result.model_dump_json()
                assert "/private" not in result.model_dump_json()

    asyncio.run(check())


@pytest.mark.parametrize("name", ["get_backtest", "list_backtest_origins"])
@pytest.mark.parametrize(
    "status,code", [(404, "not_found"), (409, "conflict"), (500, "upstream_error")]
)
def test_pending_or_failed_backtests_never_return_fake_reports(
    monkeypatch, name, status, code
):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == "GET"
        return httpx.Response(status, text="/private/SECRET-VALUE")

    async def check():
        async with connected(monkeypatch, respond) as client:
            result = await client.call_tool(name, {"backtest_id": "pending-or-failed"})
            assert payload(result) == {"ok": False, "code": code}
            assert "SECRET" not in result.model_dump_json()
        assert len(calls) == 1

    asyncio.run(check())


def test_origin_pages_encode_one_id_and_preserve_pagination_and_recorded_failure(
    monkeypatch,
):
    response = {
        "backtest_id": "b",
        "offset": 2,
        "limit": 1,
        "next_offset": 3,
        "origins": [
            {
                "ordinal": 2,
                "partition": "final",
                "nominal_origin": "2026-01-01T00:00:00Z",
                "issuance_time": "2026-01-01T00:00:00Z",
                "target_start": "2026-01-02T00:00:00Z",
                "target_end": "2026-01-02T00:00:00Z",
                "backtest_id": "b",
                "plan_id": "p",
                "status": "failed",
                "reason_code": "provider_failed",
                "run_id": None,
                "evaluation_id": None,
                "matched_count": 0,
                "model_mae": None,
                "baseline_mae": None,
            }
        ],
    }

    def respond(request):
        assert request.method == "GET"
        assert (
            request.url.raw_path
            == b"/v1/backtests/a%2Fb%3Fx%23z%25/origins?offset=2&limit=1"
        )
        return httpx.Response(200, json=response)

    async def check():
        async with connected(monkeypatch, respond) as client:
            assert (
                payload(
                    await client.call_tool(
                        "list_backtest_origins",
                        {"backtest_id": "a/b?x#z%", "offset": 2, "limit": 1},
                    )
                )["data"]
                == response
            )

    asyncio.run(check())


def test_backtest_summary_validates_and_bounds_complete_envelope(monkeypatch):
    from forecast_anything.backtesting.contracts import BacktestReport

    report = {
        "backtest_id": "b",
        "plan_id": "p",
        "archive_id": "a",
        "source_id": "sales",
        "source_revision": "r",
        "captured_at": "2026-01-01T00:00:00Z",
        "actuals_snapshot_id": "s",
        "selection": SELECTION,
        "settings": {"max_origins_per_partition": 10, "origin_offset_seconds": 0},
        "provider_contracts": {},
        "frequency": "1d",
        "status": "insufficient_evidence",
        "partitions": [
            {"partition": part, "planned": 0}
            for part in ("exploration", "selection", "final")
        ],
    }

    async def check():
        for size in (0, 40000):
            response = BacktestReport.model_validate(
                {**report, "assumptions": ["x" * size]}
            ).model_dump(mode="json")

            def respond(request):
                assert request.method == "GET"
                assert request.url.raw_path == b"/v1/backtests/a%2Fb%3Fx%23z%25"
                return httpx.Response(200, json=response)

            async with connected(monkeypatch, respond) as client:
                result = await client.call_tool(
                    "get_backtest", {"backtest_id": "a/b?x#z%"}
                )
                assert len(result.model_dump_json(by_alias=True).encode()) <= 65536
                if size:
                    assert payload(result) == {"ok": False, "code": "result_too_large"}
                else:
                    assert payload(result)["data"] == response
        async with connected(
            monkeypatch,
            lambda request: httpx.Response(
                200, json={"SECRET-KEY": "/private/SECRET-VALUE"}
            ),
        ) as client:
            result = await client.call_tool("get_backtest", {"backtest_id": "b"})
            assert payload(result) == {"ok": False, "code": "invalid_response"}
            assert "SECRET" not in result.model_dump_json()

    asyncio.run(check())


def test_backtest_defaults_and_page_defaults_use_core_contract_values(monkeypatch):
    def respond(request):
        if request.method == "POST":
            assert json.loads(request.content) == {
                "kind": "backtest",
                "key": "default-key",
                "source_id": "sales",
                "selection": {
                    "provider": "seasonal_naive",
                    "horizon": 1,
                    "options": {},
                    "baseline_period": 1,
                },
                "settings": {
                    "max_origins_per_partition": 10,
                    "origin_offset_seconds": 0,
                },
            }
            return httpx.Response(202, json=JOB)
        assert request.url.raw_path == b"/v1/backtests/b/origins?offset=0&limit=25"
        return httpx.Response(
            200,
            json={
                "backtest_id": "b",
                "origins": [],
                "offset": 0,
                "limit": 25,
                "next_offset": None,
            },
        )

    async def check():
        async with connected(
            monkeypatch,
            respond,
            config=McpConfig(workspace_token="t", source_ids=frozenset({"sales"})),
        ) as client:
            assert (
                payload(
                    await client.call_tool(
                        "submit_backtest",
                        {
                            "source_id": "sales",
                            "selection": {"provider": "seasonal_naive", "horizon": 1},
                            "key": "default-key",
                        },
                    )
                )["data"]
                == JOB
            )
            assert (
                payload(
                    await client.call_tool(
                        "list_backtest_origins", {"backtest_id": "b"}
                    )
                )["data"]["origins"]
                == []
            )

    asyncio.run(check())


@pytest.mark.parametrize("name", ["get_backtest", "list_backtest_origins"])
def test_evidence_reads_keep_http_megabyte_bound(monkeypatch, name):
    async def check():
        async with connected(
            monkeypatch,
            lambda request: httpx.Response(200, content=b"x" * (1024 * 1024 + 1)),
        ) as client:
            assert payload(await client.call_tool(name, {"backtest_id": "b"})) == {
                "ok": False,
                "code": "response_too_large",
            }

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
