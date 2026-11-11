"""Recurring watch controls and recorded history."""

from __future__ import annotations

from pydantic import TypeAdapter

from ..contracts import (
    Candidate,
    Contract,
    OpaqueDictionary,
    WatchHistoryPage,
    WatchPatch,
    WatchRequest,
    WatchView,
)
from .arguments import (
    CreateWatchArguments,
    UpdateWatchArguments,
    WatchArguments,
    WatchChangeArguments,
    WatchHistoryArguments,
    WatchListArguments,
)
from .client import CoreRequestError, encode_identifier
from .config import McpConfigError
from .dispatch import ToolContext
from .protocol import Tool


class WatchPage(Contract):
    watches: list[WatchView]
    next_offset: int | None


TOOLS = (
    Tool(
        "create_watch",
        CreateWatchArguments,
        WatchView,
        "Create a recurring watch for an executable candidate. Requires grants for all its sources and a timezone-aware next refresh time. Link it to a saved question revision. Scheduling uses the worker source subscription. Qualification requires a candidate-bound backtest.",
        mutating=True,
        open_world=True,
    ),
    Tool(
        "list_watches",
        WatchListArguments,
        WatchPage,
        "Read a bounded page of current recurring-question state, ordered by watch ID.",
    ),
    Tool(
        "get_watch",
        WatchArguments,
        WatchView,
        "Read the current lifecycle, evidence quality, next due time and controls for one recurring question.",
    ),
    Tool(
        "update_watch",
        UpdateWatchArguments,
        WatchView,
        "Mute or reprioritize a recurring question. This cannot qualify, activate or change its evidence.",
        mutating=True,
    ),
    Tool(
        "get_watch_history",
        WatchHistoryArguments,
        WatchHistoryPage,
        "Read a bounded page of append-only lifecycle transitions and the recorded watch state after each transition.",
    ),
    Tool(
        "summarize_watch_change",
        WatchChangeArguments,
        OpaqueDictionary,
        "Compare two completed recorded runs for the same recurring question. Reports observed value and snapshot differences; it does not claim causal effects.",
    ),
)


async def delegate(context: ToolContext, name: str, arguments: Contract):
    client, allowed = context.client, context.allowed
    if name == "create_watch":
        candidate = Candidate.model_validate(
            await client.request(
                "GET",
                "/v1/candidates/" + encode_identifier(arguments.candidate_id),
            )
        )
        if not set(candidate.source_ids).issubset(allowed):
            raise McpConfigError("source_forbidden")
        request = WatchRequest(**arguments.model_dump())
        return await client.request(
            "POST", "/v1/watches", body=request.model_dump(mode="json")
        )
    if name == "list_watches":
        watches = TypeAdapter(list[WatchView]).validate_python(
            await client.request("GET", "/v1/watches")
        )
        watches.sort(key=lambda watch: watch.watch_id)
        end = arguments.offset + arguments.limit
        return WatchPage(
            watches=watches[arguments.offset : end],
            next_offset=end if end < len(watches) else None,
        )
    if name == "get_watch":
        watch_id = encode_identifier(arguments.watch_id)
        return await client.request("GET", f"/v1/watches/{watch_id}", params=None)
    if name == "update_watch":
        watch_id = encode_identifier(arguments.watch_id)
        patch = WatchPatch.model_validate(
            arguments.model_dump(exclude={"watch_id"}, exclude_unset=True)
        )
        return await client.request(
            "PATCH",
            f"/v1/watches/{watch_id}",
            body=patch.model_dump(mode="json", exclude_unset=True),
        )
    if name == "get_watch_history":
        watch_id = encode_identifier(arguments.watch_id)
        return await client.request(
            "GET",
            f"/v1/watches/{watch_id}/history",
            params={"offset": arguments.offset, "limit": arguments.limit},
        )
    if name == "summarize_watch_change":
        watch_id = encode_identifier(arguments.watch_id)
        return await client.request(
            "GET",
            f"/v1/watches/{watch_id}/changes",
            params={
                "previous_run_id": arguments.previous_run_id,
                "current_run_id": arguments.current_run_id,
            },
        )
    raise CoreRequestError("unknown_tool")
