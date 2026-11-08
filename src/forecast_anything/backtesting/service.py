"""Submission intent, trusted source binding and worker capture orchestration."""

from datetime import datetime, timedelta
from hashlib import sha256

from ..contracts import (
    BacktestJobRequest,
    Capabilities,
    ConfiguredRunJobRequest,
    DomainError,
    QuestionReferenceRequest,
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
    from ..forecast_policy import validate_selection

    validate_selection(runtime, selection)
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
    payload = {
        "kind": "backtest",
        "request": original_request(request),
        "source_revision": revision.revision,
    }
    if request.watch_id is not None:
        from ..discovery.policy import candidate_backtest_selection

        watch = runtime.ledger.get_watch(request.watch_id)
        candidate = runtime.ledger.get_candidate(watch.candidate_id)
        if watch.candidate_invalidated:
            raise DomainError("watch_candidate_invalidated", {})
        try:
            selection = candidate_backtest_selection(candidate)
        except ValueError as error:
            raise DomainError("unsupported_watch_backtest", {}) from error
        profile_revision = (
            candidate.source_profiles[0].source_revision
            if len(candidate.source_profiles) == 1
            else None
        )
        if (
            candidate.candidate_id != watch.candidate_id
            or request.source_id not in candidate.source_ids
            or profile_revision != revision.revision
        ):
            raise DomainError("watch_backtest_lineage_mismatch", {})
        if request.selection != selection:
            raise DomainError("watch_backtest_selection_mismatch", {})
        if request.settings.max_origins_per_partition < 30:
            raise DomainError("insufficient_backtest_budget", {"minimum": 30})
        payload["candidate_id"] = candidate.candidate_id
        payload["watch_id"] = watch.watch_id
    return payload


def execute_job(runtime, catalog, job, now, *, secret_resolver=None) -> dict:
    """Capture once; existing plans/report recovery never consult source state."""
    store = BacktestStore(runtime.ledger)
    if runtime.required_provider is not None:
        selected = job.payload.get("request", {}).get("selection", {}).get("provider")
        if selected != runtime.required_provider:
            raise DomainError(
                "required_forecast_provider", {"provider": runtime.required_provider}
            )
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
        watch_id = job.payload.get("watch_id")
        candidate_id = job.payload.get("candidate_id")
        scheduled_snapshot = None
        if watch_id is not None:
            from ..discovery.policy import candidate_backtest_selection

            watch = runtime.ledger.get_watch(watch_id)
            candidate = runtime.ledger.get_candidate(candidate_id)
            profile_revision = (
                candidate.source_profiles[0].source_revision
                if len(candidate.source_profiles) == 1
                else None
            )
            if (
                watch.candidate_id != candidate.candidate_id
                or watch.candidate_invalidated
                or request.source_id not in candidate.source_ids
                or profile_revision != revision.revision
                or request.settings.max_origins_per_partition < 30
            ):
                raise DomainError("watch_backtest_lineage_mismatch", {})
            try:
                selection = candidate_backtest_selection(candidate)
            except ValueError as error:
                raise DomainError("unsupported_watch_backtest", {}) from error
            if request.selection != selection:
                raise DomainError("watch_backtest_selection_mismatch", {})
            if job.payload.get("automatic_requalification"):
                snapshot_id = job.payload.get("snapshot_id")
                if (
                    not snapshot_id
                    or not watch.source_snapshot_ids
                    or watch.source_snapshot_ids[-1] != snapshot_id
                ):
                    return {"suppressed": "source_snapshot_superseded"}
                scheduled_snapshot = runtime.ledger.get_snapshot(snapshot_id)
        contracts = _provider_contracts(runtime, request.selection)
        observations = (
            scheduled_snapshot.observations
            if scheduled_snapshot is not None
            else read_observations(
                revision.spec, secret_resolver=secret_resolver, max_rows=100000
            )
        )
        plan = prepare_backtest(
            job.job_id,
            revision,
            observations,
            request.selection,
            request.settings,
            scheduled_snapshot.as_of if scheduled_snapshot is not None else now,
            provider_contracts=contracts,
            watch_id=watch_id,
            candidate_id=candidate_id,
            origin_target_after=(
                datetime.fromisoformat(job.payload["origin_target_after"])
                if job.payload.get("automatic_requalification")
                and job.payload.get("origin_target_after")
                else None
            ),
        )
    report = execute_backtest(
        runtime,
        store,
        plan,
        lease_guard=job.guard,
        max_elapsed_seconds=(
            job.payload.get("execution_budget_seconds")
            if job.payload.get("automatic_requalification")
            else None
        ),
    )
    result = {"backtest_id": job.job_id, "report_id": report.report_id}
    if plan.watch_id is not None and plan.candidate_id is not None:
        ledger = runtime.ledger
        watch = ledger.get_watch(plan.watch_id)
        event_id = f"backtest/{report.report_id}"
        previous = next(
            (
                entry
                for entry in ledger.watch_history(watch.watch_id)
                if entry["event_id"] == event_id
            ),
            None,
        )
        if previous is not None:
            # A crash after publication must acknowledge the original payload,
            # even after its deadline or a later source invalidation.
            ledger.advance_watch(
                watch.watch_id,
                previous["event"],
                now,
                event_id=event_id,
                lease_guard=job.guard,
            )
            current = ledger.get_watch(watch.watch_id)
            decision = previous["event"]["decision"]
            _publish_requalification_updates(
                ledger, job, report, plan, decision, current
            )
            return result | {
                "watch_id": current.watch_id,
                "watch_lifecycle": current.lifecycle,
                "eligibility": decision["action"],
                "reason_codes": decision["reason_codes"],
            }
        if job.payload.get("automatic_requalification") and (
            not watch.source_snapshot_ids
            or job.payload.get("snapshot_id") != watch.source_snapshot_ids[-1]
        ):
            return result | {"suppressed": "source_snapshot_superseded"}
        candidate = ledger.get_candidate(plan.candidate_id)
        if watch.candidate_id != candidate.candidate_id or watch.candidate_invalidated:
            raise DomainError("watch_candidate_invalidated", {})
        from ..discovery.policy import assess_candidate_backtest

        outcomes = []
        offset = 0
        while True:
            page = store.list_origins(plan.backtest_id, offset=offset, limit=50)
            outcomes.extend(page.origins)
            if page.next_offset is None:
                break
            offset = page.next_offset
        decision = assess_candidate_backtest(candidate, report, plan, tuple(outcomes))
        ledger.append_eligibility_decision(candidate.candidate_id, decision)
        next_due_at = watch.next_due_at
        if next_due_at <= now:
            next_due_at = now + timedelta(
                seconds=catalog.get(candidate.source_ids[0]).spec.refresh_seconds
            )
        updated = ledger.advance_watch(
            watch.watch_id,
            {
                "kind": "evidence_qualified",
                "decision": decision,
                "next_due_at": next_due_at,
                "snapshot_id": plan.actuals_snapshot_id,
                **(
                    {"requalification_reason": decision.reason_codes[0]}
                    if decision.action != "activate" and decision.reason_codes
                    else {}
                ),
            },
            now,
            event_id=event_id,
            lease_guard=job.guard,
        )
        result.update(
            {
                "watch_id": updated.watch_id,
                "watch_lifecycle": updated.lifecycle,
                "eligibility": decision.action,
                "reason_codes": list(decision.reason_codes),
            }
        )
        _publish_requalification_updates(ledger, job, report, plan, decision, updated)
    return result


def _publish_requalification_updates(ledger, job, report, plan, decision, watch):
    links = tuple(job.payload.get("question_links", ()))
    if not links:
        return
    reason_codes = (
        decision.reason_codes
        if hasattr(decision, "reason_codes")
        else tuple(decision.get("reason_codes", ()))
    )
    action = decision.action if hasattr(decision, "action") else decision["action"]
    for link in links:
        question_id, revision = link["question_id"], link["revision"]
        ledger.link_question_reference(
            question_id,
            QuestionReferenceRequest(
                key=f"worker-backtest-{report.report_id}",
                revision=revision,
                target_type="backtest",
                target_id=report.backtest_id,
                note="Automatic requalification evidence",
            ),
            lease_guard=job.guard,
        )
        kind = (
            "requalification_completed"
            if action == "activate"
            else "requalification_result"
        )
        summary = (
            "La previsione è stata riqualificata su almeno 30 nuove origini finali indipendenti."
            if action == "activate"
            else "La previsione resta provvisoria dopo la riqualifica. Motivi: "
            + (", ".join(reason_codes) or "evidenza insufficiente")
            + "."
        )
        ledger.record_inbox_event(
            question_id=question_id,
            revision=revision,
            event_kind=kind,
            transition_id=report.report_id,
            decision_id=report.report_id,
            watch_id=watch.watch_id,
            summary=summary,
            payload={
                "action": action,
                "reason_codes": list(reason_codes),
                "quality": watch.quality,
                "evidence_applicable": watch.evidence_applicable,
                "backtest_id": report.backtest_id,
                "origin_target_after": (
                    plan.origin_target_after.isoformat()
                    if plan.origin_target_after is not None
                    else None
                ),
            },
            lease_guard=job.guard,
        )
