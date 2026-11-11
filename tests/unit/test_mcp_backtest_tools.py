"""MCP backtest report, origin and summary reads."""

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

            def respond(request, response=response):
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
