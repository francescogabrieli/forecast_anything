"""Shared MCP client setup and mock HTTP requests."""

import asyncio
import importlib

import pytest


def config_module():
    return importlib.import_module("forecast_anything.mcp_adapter.config")


@pytest.fixture(autouse=True)
def operator_env(monkeypatch):
    for name in (
        "FORECAST_ANYTHING_MCP_API_URL",
        "FORECAST_ANYTHING_MCP_CSV_ROOTS",
        "FORECAST_ANYTHING_MCP_SOURCE_IDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FORECAST_ANYTHING_WORKSPACE_TOKEN", "operator-secret")


def client_module():
    return importlib.import_module("forecast_anything.mcp_adapter.client")


def request(transport, method="GET", path="/v1/capabilities", **kwargs):
    async def run():
        async with client_module().CoreClient(
            config_module().McpConfig.from_env(), transport=transport
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())
