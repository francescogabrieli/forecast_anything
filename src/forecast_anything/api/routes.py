"""Thin typed v1 routes over the observatory boundary."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer

from ..backtesting.contracts import BacktestReport, OriginPage
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
    OpaqueDictionary,
    OperationCreateRequest,
    OperationPage,
    OperationSubmitRequest,
    OperationUpdateRequest,
    OperationView,
    QuestionCreateRequest,
    QuestionPage,
    QuestionReference,
    QuestionReferencePage,
    QuestionReferenceRequest,
    QuestionRevision,
    QuestionRevisionPage,
    QuestionRevisionRequest,
    QuestionTitlePatch,
    QuestionView,
    RunRecord,
    ScenarioRequest,
    ScenarioView,
    Snapshot,
    SnapshotSeriesPage,
    SnapshotSummary,
    SourceProfile,
    SourceRefreshRequest,
    SourceRegistration,
    SourceSpec,
    SourceView,
    WatchHistoryPage,
    WatchPatch,
    WatchRequest,
    WatchView,
)
from ..discovery.agent_gateway import AgentOperationRequest, AgentOperationResponse
from ..discovery.candidates import TEMPLATES
from ..presentations import (
    BacktestPresentation,
    ForecastPresentation,
    QuestionPresentation,
)
from ..sources.profiling import inspect_source
from .scenarios import create_scenario


def router(service):
    api = APIRouter(prefix="/v1", dependencies=[Depends(HTTPBearer(auto_error=False))])

    @api.post("/sources", response_model=SourceRegistration, status_code=201)
    def register(spec: SourceSpec):
        return service.register_source(spec)

    @api.post("/sources/preview", response_model=SourceProfile)
    def preview_source(spec: SourceSpec):
        return inspect_source(spec)

    @api.get("/sources", response_model=list[SourceView])
    def sources():
        return [service.source_view(s) for s in service.catalog.list()]

    @api.get("/sources/{source_id}/profile", response_model=SourceProfile)
    def profile(source_id: str):
        return service.profile(source_id)[0]

    @api.post(
        "/sources/{source_id}/refresh",
        response_model=SourceRegistration,
        status_code=202,
    )
    def refresh(source_id: str, request: SourceRefreshRequest):
        return service.refresh_source(source_id, request)

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

    @api.post("/questions", response_model=QuestionView, status_code=201)
    def create_question(request: QuestionCreateRequest):
        return service.create_question(request)

    @api.get("/questions", response_model=QuestionPage)
    def questions(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.questions(offset=offset, limit=limit)

    @api.get("/questions/{question_id}", response_model=QuestionView)
    def question(question_id: str):
        return service.question(question_id)

    @api.patch("/questions/{question_id}", response_model=QuestionView)
    def patch_question(question_id: str, request: QuestionTitlePatch):
        return service.patch_question(question_id, request)

    @api.post("/questions/{question_id}/revisions", response_model=QuestionView)
    def revise_question(question_id: str, request: QuestionRevisionRequest):
        return service.revise_question(question_id, request)

    @api.get("/questions/{question_id}/revisions", response_model=QuestionRevisionPage)
    def question_revisions(
        question_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.question_revisions(question_id, offset=offset, limit=limit)

    @api.get(
        "/questions/{question_id}/revisions/{revision}", response_model=QuestionRevision
    )
    def question_revision(question_id: str, revision: int):
        return service.question_revision(question_id, revision)

    @api.post(
        "/questions/{question_id}/references",
        response_model=QuestionReference,
        status_code=201,
    )
    def link_question_reference(question_id: str, request: QuestionReferenceRequest):
        return service.link_question_reference(question_id, request)

    @api.get(
        "/questions/{question_id}/references", response_model=QuestionReferencePage
    )
    def question_references(
        question_id: str,
        revision: Annotated[int | None, Query(ge=1)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.question_references(
            question_id, revision=revision, offset=offset, limit=limit
        )

    @api.get(
        "/questions/{question_id}/presentation", response_model=QuestionPresentation
    )
    def question_presentation(
        question_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=3)] = 3,
    ):
        return service.question_presentation(question_id, offset=offset, limit=limit)

    @api.post("/operations", response_model=OperationView, status_code=201)
    def create_operation(request: OperationCreateRequest):
        return service.create_operation(request)

    @api.get("/operations", response_model=OperationPage)
    def operations(
        question_id: Annotated[str | None, Query(min_length=1)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.operations(question_id=question_id, offset=offset, limit=limit)

    @api.get("/operations/{operation_id}", response_model=OperationView)
    def operation(operation_id: str):
        return service.operation(operation_id)

    @api.patch("/operations/{operation_id}", response_model=OperationView)
    def update_operation(operation_id: str, request: OperationUpdateRequest):
        return service.update_operation(operation_id, request)

    @api.post("/operations/{operation_id}/submit", response_model=OperationView)
    def submit_operation(operation_id: str, request: OperationSubmitRequest):
        return service.submit_operation(operation_id, request)

    @api.post("/operations/{operation_id}/resume", response_model=OperationView)
    def resume_operation(operation_id: str):
        return service.resume_operation(operation_id)

    @api.get("/watches/{watch_id}", response_model=WatchView)
    def get_watch(watch_id: str):
        return service.watch(watch_id)

    @api.get("/watches/{watch_id}/history", response_model=WatchHistoryPage)
    def watch_history(
        watch_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.watch_history(watch_id, offset=offset, limit=limit)

    @api.get("/watches/{watch_id}/changes", response_model=OpaqueDictionary)
    def watch_change_summary(
        watch_id: str,
        previous_run_id: Annotated[str, Query(min_length=1)],
        current_run_id: Annotated[str, Query(min_length=1)],
    ):
        return service.watch_change_summary(watch_id, previous_run_id, current_run_id)

    @api.patch("/watches/{watch_id}", response_model=WatchView)
    def patch(watch_id: str, request: WatchPatch):
        return service.patch_watch(watch_id, request)

    @api.post("/jobs", response_model=JobView, status_code=202)
    def submit(request: JobRequest):
        return service.submit(request)

    @api.post("/agent/operations", response_model=AgentOperationResponse)
    def agent_operation(request: AgentOperationRequest):
        return service.agent_operation(request)

    @api.get("/jobs/{job_id}", response_model=JobView)
    def job(job_id: str):
        return service.job(job_id)

    @api.get("/runs/{run_id}", response_model=RunRecord)
    def run(run_id: str):
        return service.ledger.get_run(run_id)

    @api.get("/runs/{run_id}/presentation", response_model=ForecastPresentation)
    def forecast_presentation(run_id: str):
        return service.forecast_presentation(run_id)

    @api.get("/runs/{run_id}/evaluations", response_model=list[EvaluationRecord])
    def run_evaluations(run_id: str):
        return service.ledger.evaluations_for_run(run_id)

    @api.get("/evaluations/{evaluation_id}", response_model=EvaluationRecord)
    def evaluation(evaluation_id: str):
        return service.ledger.get_evaluation(evaluation_id)

    @api.get("/backtests/{backtest_id}", response_model=BacktestReport)
    def backtest(backtest_id: str):
        return service.backtest(backtest_id)

    @api.get(
        "/backtests/{backtest_id}/presentation",
        response_model=BacktestPresentation,
    )
    def backtest_presentation(
        backtest_id: str,
        watch_id: Annotated[str | None, Query(min_length=1)] = None,
    ):
        return service.backtest_presentation(backtest_id, watch_id=watch_id)

    @api.get("/backtests/{backtest_id}/origins", response_model=OriginPage)
    def backtest_origins(
        backtest_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=50)] = 25,
    ):
        return service.backtest_origins(backtest_id, offset=offset, limit=limit)

    @api.get("/snapshots/{snapshot_id}", response_model=Snapshot)
    def snapshot(snapshot_id: str):
        return service.ledger.get_snapshot(snapshot_id)

    @api.get("/snapshots/{snapshot_id}/summary", response_model=SnapshotSummary)
    def snapshot_summary(snapshot_id: str):
        return service.snapshot_summary(snapshot_id)

    @api.get("/snapshots/{snapshot_id}/series", response_model=SnapshotSeriesPage)
    def snapshot_series(
        snapshot_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.snapshot_series(snapshot_id, offset=offset, limit=limit)

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
                batch = await asyncio.to_thread(service.events, position)
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
        from ..forecast_policy import model_readiness

        return CapabilitiesView(
            required_provider=service.runtime.required_provider,
            model_status=model_readiness(service.runtime)
            if service.runtime.required_provider
            else None,
            providers={
                k: p.capabilities() for k, p in service.runtime.providers.items()
            },
            operators={k: o.contract() for k, o in service.runtime.operators.items()},
            templates=tuple(TEMPLATES),
        )

    return api
