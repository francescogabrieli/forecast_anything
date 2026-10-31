"""Submission intent, trusted source binding and worker capture orchestration."""

from datetime import timedelta
from hashlib import sha256

from ..contracts import (
    BacktestJobRequest,
    Capabilities,
    ConfiguredRunJobRequest,
    DomainError,
    RunJobRequest,
)
from ..sources.profiling import read_observations
from .contracts import canonical_json
from .planning import (
    _observed,
    _source_frequency,
    build_forecast_graph,
    prepare_backtest,
)
from .runner import execute_backtest
from .store import BacktestStore


def original_request(request) -> dict:
    return request.model_dump(mode="json", exclude={"key"})


def replay_job(queue, request):
    """Compare JSON types and defaults before consulting mutable dependencies."""
    key = f"api/{request.key}"
    job_id = sha256(key.encode()).hexdigest()
    try:
        payload = queue.original_payload(job_id)
    except DomainError as error:
        if error.code != "not_found":
            raise
        return None
    if canonical_json(payload.get("request")) != canonical_json(
        original_request(request)
    ):
        raise DomainError("idempotency_conflict", {"key": key})
    return queue.get(job_id)


def configured_run(ledger, catalog, request: ConfiguredRunJobRequest) -> RunJobRequest:
    snapshot = ledger.get_snapshot(request.snapshot_id)
    if any(item.startswith("assumed:") for item in snapshot.assumptions):
        raise DomainError("scenario_required", {})
    catalog.get(request.source_id)
    vintages = {
        revision.revision: revision
        for revision in catalog.history(request.source_id)
        if f"source_revision={revision.revision}" in snapshot.assumptions
    }
    if len(vintages) != 1:
        raise DomainError(
            "source_snapshot_lineage_mismatch", {"source_id": request.source_id}
        )
    vintage = next(iter(vintages.values()))
    _observed(vintage.assumptions)
    frequency, _ = _source_frequency(vintage)
    graph = build_forecast_graph(
        request.source_id,
        snapshot,
        request.selection,
        frequency,
        graph_id="configured-"
        + sha256(canonical_json(original_request(request)).encode()).hexdigest(),
    )
    return RunJobRequest(
        kind="run",
        key=request.key,
        graph=graph,
        snapshot_ids={request.source_id: snapshot.snapshot_id},
        as_of=snapshot.as_of,
    )


def _provider_contracts(runtime, selection):
    contracts = {}
    for name in {selection.provider, "seasonal_naive"}:
        provider = runtime.providers.get(name)
        if provider is None:
            raise DomainError("unknown_provider", {"provider": name})
        capability = Capabilities.model_validate_json(
            provider.capabilities().model_dump_json()
        )
        if capability.provider_id != name:
            raise DomainError("unknown_provider", {"provider": name})
        contracts[name] = capability
    return contracts


def backtest_payload(runtime, catalog, request: BacktestJobRequest) -> dict:
    revision = catalog.get(request.source_id)
    if revision.spec.kind != "csv":
        raise DomainError("unsupported_backtest_source", {})
    _observed(revision.assumptions)
    _, step = _source_frequency(revision)
    if request.settings.origin_offset_seconds >= step // timedelta(seconds=1):
        raise DomainError("invalid_origin_offset", {})
    _provider_contracts(runtime, request.selection)
    return {
        "kind": "backtest",
        "request": original_request(request),
        "source_revision": revision.revision,
    }


def execute_job(runtime, catalog, job, now, *, secret_resolver=None) -> dict:
    """Capture once; existing plans/report recovery never consult source state."""
    store = BacktestStore(runtime.ledger)
    try:
        plan = store.get_plan(job.job_id)
    except DomainError as error:
        if error.code != "not_found":
            raise
        request = BacktestJobRequest.model_validate(
            {**job.payload["request"], "key": job.key}
        )
        revision = catalog.get(request.source_id)
        if revision.revision != job.payload["source_revision"]:
            raise DomainError("source_revision_changed", {})
        if revision.spec.kind != "csv":
            raise DomainError("unsupported_backtest_source", {})
        contracts = _provider_contracts(runtime, request.selection)
        observations = read_observations(
            revision.spec, secret_resolver=secret_resolver, max_rows=100000
        )
        plan = prepare_backtest(
            job.job_id,
            revision,
            observations,
            request.selection,
            request.settings,
            now,
            provider_contracts=contracts,
        )
    report = execute_backtest(runtime, store, plan, lease_guard=job.guard)
    return {"backtest_id": job.job_id, "report_id": report.report_id}
