"""Thin typed v1 routes over the observatory boundary."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPBearer

from ..contracts import (
    CapabilitiesView,
    InboxPage,
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
    ResourceIdentity,
    ScenarioRequest,
    ScenarioView,
    WatchHistoryPage,
    WatchPatch,
    WatchRequest,
    WatchView,
    WorkspaceIdentity,
)
from ..discovery.candidates import TEMPLATES
from ..presentations import (
    QuestionPresentation,
)
from .routes_events import register_events
from .routes_jobs import register_jobs
from .routes_sources import register_sources
from .routes_subscriptions import register_subscriptions
from .scenarios import create_scenario


def router(service):
    api = APIRouter(prefix="/v1", dependencies=[Depends(HTTPBearer(auto_error=False))])

    @api.get("/workspace", response_model=WorkspaceIdentity)
    def workspace_identity():
        return WorkspaceIdentity(workspace_id=service.ledger.workspace_id())

    @api.get(
        "/resource-identities/{kind}/{resource_id}", response_model=ResourceIdentity
    )
    def resource_identity(kind: Literal["run", "question", "report"], resource_id: str):
        return ResourceIdentity(
            kind=kind, resource_id=service.ledger.resource_identity(kind, resource_id)
        )

    register_sources(api, service)

    @api.post("/watches", response_model=WatchView, status_code=201)
    def watch(request: WatchRequest):
        return service.create_watch(request)

    @api.get("/watches", response_model=list[WatchView])
    def watches():
        return service.watches()

    @api.post("/questions", response_model=QuestionView, status_code=201)
    def create_question(request: QuestionCreateRequest):
        return service.create_question(request)

    register_subscriptions(api, service)

    @api.get("/questions", response_model=QuestionPage)
    def questions(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.questions(offset=offset, limit=limit)

    @api.get("/inbox", response_model=InboxPage)
    def inbox_events(
        question_id: Annotated[str | None, Query(min_length=1)] = None,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.inbox_events(question_id=question_id, offset=offset, limit=limit)

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

    register_jobs(api, service)

    register_events(api, service)

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
