"""Shared MCP responses and in-process protocol helpers."""

import importlib
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from forecast_anything.mcp_adapter.client import CoreClient
from forecast_anything.mcp_adapter.config import McpConfig

NAMES = {
    "get_browser_link",
    "open_context_view",
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
    "list_inbox_events",
    "list_source_subscriptions",
    "set_source_subscription",
    "create_webhook_subscription",
    "list_webhook_subscriptions",
    "update_webhook_subscription",
    "list_webhook_deliveries",
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


SELECTION = {
    "provider": "seasonal_naive",
    "horizon": 2,
    "options": {"period": 2},
    "baseline_period": 1,
}
