"""MCP initialization and tool discovery advertise concise, packaged guidance."""

from importlib.resources import files

from mcp_tool_fixtures import module

from forecast_anything.mcp_adapter.config import McpConfig


def test_initialization_uses_packaged_instructions_within_budget():
    server = module().create_server(McpConfig(workspace_token="test-token"))
    instructions = server.create_initialization_options().instructions
    assert len(instructions) <= 900
    resource = files("forecast_anything.mcp_adapter").joinpath("instructions.md")
    assert instructions == resource.read_text(encoding="utf-8").strip()
