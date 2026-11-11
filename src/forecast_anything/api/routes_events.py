"""Ledger event paging and authenticated event streaming."""

import asyncio
from typing import Annotated

from fastapi import Header, Query, Request
from fastapi.responses import StreamingResponse

from ..contracts import (
    DomainError,
    EventRecord,
)


def register_events(api, service):
    def cursor(after, last_event_id):
        if last_event_id is None:
            return after
        try:
            value = int(last_event_id)
            if value < 0:
                raise ValueError
        except ValueError as error:
            raise DomainError("invalid_cursor", {}) from error
        return max(after, value)

    @api.get("/events", response_model=list[EventRecord])
    def events(
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        last_event_id: Annotated[str | None, Header()] = None,
    ):
        return service.events(cursor(after, last_event_id), limit)

    @api.get(
        "/events/stream",
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {}}}},
    )
    async def stream(
        request: Request,
        after: Annotated[int, Query(ge=0)] = 0,
        last_event_id: Annotated[str | None, Header()] = None,
        follow: bool = True,
    ):
        position = cursor(after, last_event_id)

        async def replay():
            nonlocal position
            while True:
                check_session = getattr(request.state, "browser_session_valid", None)
                if check_session is not None and not check_session():
                    break
                batch = await asyncio.to_thread(service.events, position)
                for event in batch:
                    if check_session is not None and not check_session():
                        return
                    yield f"id: {event.cursor}\nevent: {event.kind}\ndata: {event.model_dump_json()}\n\n"
                    position = event.cursor
                if not follow:
                    if len(batch) == 100:
                        continue
                    break
                if await request.is_disconnected():
                    break
                if not batch:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(1)

        return StreamingResponse(
            replay(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
