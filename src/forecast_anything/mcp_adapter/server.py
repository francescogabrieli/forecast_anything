"""Typed stdio tools over the operator-configured loopback API only."""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from mcp import types
from mcp.server import Server as MCPServer
from mcp.server.stdio import stdio_server
from pydantic import TypeAdapter, ValidationError

from ..contracts import Contract
from ..diagnostics import diagnose, runtime_version
from .arguments import NonNegative as NonNegative
from .arguments import ToolIdentifier as ToolIdentifier
from .catalog import CATALOG as _CATALOG
from .catalog import DELEGATES
from .catalog import TOOLS as _TOOLS
from .client import CoreClient, CoreRequestError
from .config import McpConfig, McpConfigError
from .context_views import BrowserLink as BrowserLink
from .context_views import ContextViewResult as ContextViewResult
from .context_views import render_context_view
from .dispatch import ToolContext
from .protocol import VIEW_META, VIEW_MIME, VIEW_URI
from .protocol import Envelope as Envelope
from .protocol import InputErrors as InputErrors
from .protocol import Tool as _Tool
from .protocol import tool_result as _result
from .protocol import validation_errors as _validation_errors
from .source_tools import SourcePage as SourcePage
from .watch_tools import WatchPage as WatchPage
from .workspace_tools import DiagnosticPermissions as DiagnosticPermissions
from .workspace_tools import DiagnosticsView as DiagnosticsView
from .workspace_tools import EventPage as EventPage


async def _delegate(
    client: CoreClient,
    allowed: set[str],
    config: McpConfig,
    tool: _Tool,
    arguments: Contract,
    adapter_session: str,
):
    if tool.name == "get_diagnostics":
        # Keep the diagnostic callable at the server boundary, including when
        # the core client cannot connect.
        return await asyncio.to_thread(
            diagnose,
            config.api_url,
            config.workspace_token,
            config.csv_roots,
            allowed.copy(),
        )
    handler = DELEGATES.get(tool.name)
    if handler is None:
        raise CoreRequestError("unknown_tool")
    return await handler(
        ToolContext(client, allowed, config, adapter_session), tool.name, arguments
    )


def create_server(config: McpConfig) -> MCPServer:
    """Create an official SDK v2 server; one async HTTP client per connection."""
    allowed = set(config.source_ids)
    adapter_session = uuid4().hex

    @asynccontextmanager
    async def lifespan(server):
        async with CoreClient(config) as client:
            yield client

    async def list_tools(context, params):
        return types.ListToolsResult(tools=[tool.schema() for tool in _TOOLS])

    async def list_resources(context, params):
        return types.ListResourcesResult(
            resources=[
                types.Resource(
                    name="forecast-context",
                    uri=VIEW_URI,
                    mime_type=VIEW_MIME,
                    meta=VIEW_META,
                )
            ]
        )

    async def read_resource(context, params):
        if str(params.uri) != VIEW_URI:
            raise ValueError("Unknown resource")
        html = (Path(__file__).parent / "ui_dist" / "context.html").read_text(
            encoding="utf-8"
        )
        return types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri=VIEW_URI, mime_type=VIEW_MIME, text=html, meta=VIEW_META
                )
            ]
        )

    async def call_tool(context, params):
        if not isinstance(params.name, str) or params.name not in _CATALOG:
            return _result({"ok": False, "code": "unknown_tool"})
        tool = _CATALOG[params.name]
        try:
            arguments = tool.arguments.model_validate(
                params.arguments if params.arguments is not None else {}
            )
        except ValidationError as error:
            return _result(
                {
                    "ok": False,
                    "code": "validation_error",
                    "errors": _validation_errors(error, tool.arguments),
                }
            )
        try:
            data = await _delegate(
                context.lifespan_context,
                allowed,
                config,
                tool,
                arguments,
                adapter_session,
            )
            data = TypeAdapter(tool.result).validate_python(data)
            result = {
                "ok": True,
                "data": TypeAdapter(tool.result).dump_python(data, mode="json"),
            }
            if tool.name == "open_context_view":
                return render_context_view(data, result)
            return _result(result)
        except (CoreRequestError, McpConfigError) as error:
            return _result({"ok": False, "code": error.code})
        except ValidationError:
            return _result({"ok": False, "code": "invalid_response"})
        except Exception:
            # Protocol failure must never echo input, upstream exceptions, or
            # source locations, and must never masquerade as successful data.
            return _result({"ok": False, "code": "internal_error"})

    server = MCPServer(
        "forecast-anything",
        version=runtime_version(),
        lifespan=lifespan,
        instructions=files(__package__)
        .joinpath("instructions.md")
        .read_text(encoding="utf-8")
        .strip(),
        on_list_tools=list_tools,
        on_list_resources=list_resources,
        on_read_resource=read_resource,
    )
    server.extensions["io.modelcontextprotocol/ui"] = {}
    server.add_request_handler("tools/call", types.CallToolRequestParams, call_tool)
    return server


def run_stdio() -> int:
    """Read operator configuration and serve only MCP traffic on stdout."""
    try:
        config = McpConfig.from_env()

        async def serve():
            server = create_server(config)
            async with stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream, write_stream, server.create_initialization_options()
                )

        asyncio.run(serve())
        return 0
    except KeyboardInterrupt:
        return 0
    except McpConfigError as error:
        print(json.dumps({"ok": False, "code": error.code}), file=sys.stderr)
    except Exception:
        print(json.dumps({"ok": False, "code": "server_error"}), file=sys.stderr)
    return 2
