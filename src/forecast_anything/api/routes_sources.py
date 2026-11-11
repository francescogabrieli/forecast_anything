"""Registered source and candidate routes."""

from ..contracts import (
    Candidate,
    CandidateRequest,
    CsvConfirmation,
    CsvConfirmationResult,
    CsvPreview,
    CsvPreviewRequest,
    SourceConfiguration,
    SourceProfile,
    SourceRefreshRequest,
    SourceRegistration,
    SourceSpec,
    SourceView,
)
from ..sources.profiling import inspect_source, preview_csv


def register_sources(api, service):
    @api.post("/sources", response_model=SourceRegistration, status_code=201)
    def register(spec: SourceSpec):
        return service.register_source(spec)

    @api.post("/sources/preview", response_model=SourceProfile)
    def preview_source(spec: SourceSpec):
        return inspect_source(spec)

    @api.post("/sources/csv-preview", response_model=CsvPreview)
    def preview_csv_source(request: CsvPreviewRequest):
        return preview_csv(request.spec, request.as_of)

    @api.post(
        "/sources/csv-confirm", response_model=CsvConfirmationResult, status_code=201
    )
    def confirm_csv_source(request: CsvConfirmation):
        return service.confirm_csv_source(request)

    @api.get("/sources", response_model=list[SourceView])
    def sources():
        return [service.source_view(s) for s in service.catalog.list()]

    @api.get("/sources/{source_id}/profile", response_model=SourceProfile)
    def profile(source_id: str):
        return service.profile(source_id)[0]

    @api.get("/sources/{source_id}/configuration", response_model=SourceConfiguration)
    def source_configuration(source_id: str):
        spec = service.catalog.get(source_id).spec
        return SourceConfiguration(
            source_id=spec.source_id,
            kind=spec.kind,
            location=spec.location,
            mapping=spec.mapping,
            refresh_seconds=spec.refresh_seconds,
            has_secret_ref=spec.secret_ref is not None,
        )

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
