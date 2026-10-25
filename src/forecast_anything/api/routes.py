"""Thin typed v1 routes over the observatory boundary."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer

from ..contracts import (
    Candidate,
    CandidateRequest,
    CapabilitiesView,
    DomainError,
    EvaluationRecord,
    EventRecord,
    GraphSpec,
    JobRequest,
    JobView,
    RunRecord,
    ScenarioRequest,
    ScenarioView,
    Snapshot,
    SourceProfile,
    SourceRegistration,
    SourceSpec,
    SourceView,
    WatchPatch,
    WatchRequest,
    WatchView,
)
from ..discovery.candidates import TEMPLATES
from .scenarios import create_scenario


def router(service):
    api = APIRouter(prefix="/v1", dependencies=[Depends(HTTPBearer(auto_error=False))])

    @api.post("/sources", response_model=SourceRegistration, status_code=201)
    def register(spec: SourceSpec):
        return service.register_source(spec)

    @api.get("/sources", response_model=list[SourceView])
    def sources():
        return [service.source_view(s) for s in service.catalog.list()]

    @api.get("/sources/{source_id}/profile", response_model=SourceProfile)
    def profile(source_id: str):
        return service.profile(source_id)[0]

    @api.post("/candidates", response_model=Candidate, status_code=201)
    def propose(request: CandidateRequest):
        return service.candidate(request)

    @api.get("/candidates/{candidate_id}", response_model=Candidate)
    def candidate(candidate_id: str):
        return service.ledger.get_candidate(candidate_id)

    @api.post("/watches", response_model=WatchView, status_code=201)
    def watch(request: WatchRequest):
        return service.create_watch(request)

    @api.get("/watches", response_model=list[WatchView])
    def watches():
        return service.watches()

    @api.patch("/watches/{watch_id}", response_model=WatchView)
    def patch(watch_id: str, request: WatchPatch):
        return service.patch_watch(watch_id, request)

    @api.post("/jobs", response_model=JobView, status_code=202)
    def submit(request: JobRequest):
        return service.submit(request)

    @api.get("/jobs/{job_id}", response_model=JobView)
    def job(job_id: str):
        return service.job(job_id)

    @api.get("/runs/{run_id}", response_model=RunRecord)
    def run(run_id: str):
        return service.ledger.get_run(run_id)

    @api.get("/evaluations/{evaluation_id}", response_model=EvaluationRecord)
    def evaluation(evaluation_id: str):
        return service.ledger.get_evaluation(evaluation_id)

    @api.get("/snapshots/{snapshot_id}", response_model=Snapshot)
    def snapshot(snapshot_id: str):
        return service.ledger.get_snapshot(snapshot_id)

    @api.get("/graphs/{graph_id}", response_model=GraphSpec)
    def graph(graph_id: str, version: Annotated[int, Query(gt=0)] = 1):
        return service.ledger.get_graph(graph_id, version)

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
        return service.ledger.events_after(cursor(after, last_event_id), limit)

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
                batch = await asyncio.to_thread(service.ledger.events_after, position)
                for event in batch:
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

    @api.post("/scenarios", response_model=ScenarioView, status_code=201)
    def scenario(request: ScenarioRequest):
        return create_scenario(service.runtime, request)

    @api.get("/capabilities", response_model=CapabilitiesView)
    def capabilities():
        return CapabilitiesView(
            providers={
                k: p.capabilities() for k, p in service.runtime.providers.items()
            },
            operators={k: o.contract() for k, o in service.runtime.operators.items()},
            templates=tuple(TEMPLATES),
        )

    return api
