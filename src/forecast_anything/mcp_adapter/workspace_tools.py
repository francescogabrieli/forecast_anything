"""Workspace capabilities, diagnostics, and event cursors."""

from __future__ import annotations

from pydantic import TypeAdapter

from ..contracts import CapabilitiesView, Contract, EventRecord
from .arguments import EventsArguments, NoArguments
from .client import CoreRequestError
from .dispatch import ToolContext
from .protocol import Tool


class DiagnosticPermissions(Contract):
    csv_roots: int
    readable_csv_roots: int
    source_grants: int


class DiagnosticsView(Contract):
    api: str
    authentication: str
    worker: str
    model: str
    runtime_version: str | None
    client_version: str
    permissions: DiagnosticPermissions
    ready: bool
    recovery: list[str]


class EventPage(Contract):
    events: list[EventRecord]
    cursor: int


TOOLS = (
    Tool(
        "get_diagnostics",
        NoArguments,
        DiagnosticsView,
        "Diagnose the configured local workspace even when the API is offline. Read-only: authentication, worker/model readiness, permission counts, version and recovery.",
    ),
    Tool(
        "get_capabilities",
        NoArguments,
        CapabilitiesView,
        "Read actual installed provider, operator and template contracts.",
    ),
    Tool(
        "get_events",
        EventsArguments,
        EventPage,
        "Read durable events after a cursor; use returned cursor to continue.",
    ),
)


async def delegate(context: ToolContext, name: str, arguments: Contract):
    client = context.client
    if name == "get_capabilities":
        return await client.request("GET", "/v1/capabilities", params=None)
    if name == "get_events":
        events = TypeAdapter(list[EventRecord]).validate_python(
            await client.request("GET", "/v1/events", params=arguments.model_dump())
        )
        return EventPage(
            events=events, cursor=events[-1].cursor if events else arguments.after
        )
    raise CoreRequestError("unknown_tool")
