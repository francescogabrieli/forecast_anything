"""MCP configured forecast and backtest submissions."""

import asyncio
import json

import httpx
import pytest
from mcp_tool_fixtures import (
    JOB,
    SELECTION,
    connected,
    payload,
)

from forecast_anything.mcp_adapter.config import McpConfig

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
                {
                    "key",
                    "source_id",
                    "snapshot_id",
                    "selection",
                    "selection_report_id",
                    "challenger_report_id",
                },
            ),
            (
                "submit_backtest",
                {"key", "source_id", "selection", "settings", "watch_id"},
            ),
        ):
            schema = catalog[name].input_schema
            assert set(schema["properties"]) == fields
            assert "selection" in schema["required"]
            assert not {"selection_report_id", "challenger_report_id"} & set(
                schema["required"]
            )
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
        (
            "submit_configured_forecast",
            {
                **CONFIGURED,
                "selection_report_id": "default-report",
                "challenger_report_id": "challenger-report",
            },
            "configured_run",
        ),
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
