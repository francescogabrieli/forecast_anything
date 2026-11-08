"""Validated application boundary; routes never write SQL or trust agent lineage."""

from hashlib import sha256
from uuid import uuid4

from pydantic import ValidationError

from ..backtesting import service as backtesting
from ..backtesting.store import BacktestStore
from ..contracts import (
    BacktestJobRequest,
    CandidateRequest,
    ConfiguredRunJobRequest,
    CsvConfirmationResult,
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EvaluationJobRequest,
    JobView,
    OpaqueDictionary,
    OperationCreateRequest,
    OperationPage,
    OperationSubmitRequest,
    OperationUpdateRequest,
    OperationView,
    QuestionCreateRequest,
    QuestionPage,
    QuestionReferencePage,
    QuestionReferenceRequest,
    QuestionRevisionPage,
    QuestionRevisionRequest,
    QuestionTitlePatch,
    QuestionView,
    ResumeJobRequest,
    RunJobRequest,
    SnapshotSeriesPage,
    SnapshotSummary,
    SourceProfile,
    SourceRefreshRequest,
    SourceRegistration,
    SourceSpec,
    SourceSubscription,
    SourceSubscriptionPage,
    SourceView,
    WatchHistoryEntry,
    WatchHistoryPage,
    WatchPatch,
    WatchRequest,
    WatchView,
    WebhookDeliveryPage,
    WebhookSubscription,
    WebhookSubscriptionPage,
    WebhookSubscriptionPatch,
    WebhookSubscriptionRequest,
)
from ..discovery.agent_gateway import AgentOperationRequest, AgentOperationResponse
from ..discovery.candidates import CandidateProposal, compile_proposal
from ..forecast_policy import provider_epoch_context
from ..graph import ForecastConfig, SourceConfig, compile_graph, parse_node_config
from ..jobs import JobQueue
from ..providers.base import frequency_step, observation_grid
from ..runtime import _digest
from ..sources.catalog import SourceCatalog
from ..sources.profiling import capture_confirmed_csv, inspect_source
from ..store import _json
from ..watches import create_watch, summarize_watch_change
from ..worker import Worker
from .errors import public_event, public_failure


def validate_run(runtime, graph, snapshots, as_of, primary_node_id=None):
    from ..forecast_policy import ensure_required_model, validate_primary_provider

    validate_primary_provider(graph, runtime.required_provider, primary_node_id)
    ensure_required_model(runtime)
    try:
        stored = runtime.ledger.get_graph(graph.graph_id, graph.version)
    except DomainError as error:
        if error.code != "not_found":
            raise
    else:
        if stored != graph:
            raise DomainError(
                "immutable_identity",
                {"graph_id": graph.graph_id, "version": graph.version},
            )
    compiled = compile_graph(
        graph,
        {k: p.capabilities() for k, p in runtime.providers.items()},
        {k: o.contract() for k, o in runtime.operators.items()},
    )
    configs = {n.node_id: parse_node_config(n) for n in graph.nodes}
    expected = {c.source_id for c in configs.values() if isinstance(c, SourceConfig)}
    if expected != set(snapshots):
        raise DomainError("invalid_snapshot_bindings", {})
    calendars = {}
    for node_id in compiled.order:
        config = configs[node_id]
        if isinstance(config, SourceConfig):
            snap = snapshots[config.source_id]
            if snap.as_of != as_of:
                raise DomainError("snapshot_origin_mismatch", {"node_id": node_id})
            groups, calendar = observation_grid(snap, config.frequency)
            if set(groups) != set(config.series_ids) or any(
                groups[s][0].unit != unit
                for s, unit in zip(config.series_ids, config.units)
            ):
                raise DomainError("source_metadata_mismatch", {"node_id": node_id})
            calendars[node_id] = calendar
        elif isinstance(config, ForecastConfig):
            history = calendars[config.history]
            if history[-1] > as_of:
                raise DomainError("future_history", {"node_id": node_id})
            expected_grid = tuple(
                history[-1] + frequency_step(config.frequency) * (i + 1)
                for i in range(config.horizon)
            )
            if config.known_future and calendars[config.known_future] != expected_grid:
                raise DomainError(
                    "known_future_calendar_mismatch", {"node_id": node_id}
                )
            calendars[node_id] = expected_grid


class Observatory:
    def __init__(self, ledger, runtime):
        if ledger.path.resolve() != runtime.ledger.path.resolve():
            raise DomainError("runtime_ledger_mismatch", {})
        self.ledger, self.runtime = ledger, runtime
        self.catalog = SourceCatalog(ledger.path)
        self.queue = JobQueue(ledger)
        self.worker = Worker(runtime, self.queue)

    def now(self):
        return max(self.runtime.clock(), self.ledger.clock())

    def agent_operation(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """Serve a scoped Eve tool after durable core budget reservation."""
        request = AgentOperationRequest.model_validate(request.model_dump())
        operation_id, previous = self.ledger.reserve_agent_operation(
            request.job_id,
            request.epoch_id,
            request.session_id,
            request.call_key,
            request.tool,
            sha256(_json(request.input).encode()).hexdigest(),
        )
        if previous is not None:
            return AgentOperationResponse(operation_id=operation_id, result=previous)
        result = self._agent_tool_result(request)
        return AgentOperationResponse(
            operation_id=operation_id,
            result=self.ledger.complete_agent_operation(operation_id, result),
        )

    def _agent_tool_result(self, request: AgentOperationRequest) -> dict:
        job = self.queue.get(request.job_id)
        source_ids = set(job.payload["source_ids"])
        profiles = {}
        for candidate in self.ledger.candidates_for_epoch(request.epoch_id):
            for profile in candidate.source_profiles:
                prior = profiles.setdefault(profile.source_id, profile)
                if prior != profile:
                    raise DomainError("ambiguous_source_profile", {})

        if request.tool == "inspectSource":
            source_id = request.input.get("source_id")
            if (
                set(request.input) != {"source_id"}
                or not isinstance(source_id, str)
                or source_id not in source_ids
            ):
                raise DomainError("invalid_agent_input", {})
            if source_id not in profiles:
                raise DomainError("unknown_source_profile", {})
            return profiles[source_id].model_dump(mode="json")

        if request.tool == "proposeCandidates":
            proposals = request.input.get("proposals")
            if (
                set(request.input) != {"proposals"}
                or not isinstance(proposals, list)
                or len(proposals)
                > self.ledger.discovery_budget(request.epoch_id).max_candidates
            ):
                raise DomainError("invalid_agent_input", {})
            candidates = []
            for raw in proposals:
                try:
                    proposal = CandidateProposal.model_validate(raw)
                except ValidationError as error:
                    raise DomainError("invalid_agent_input", {}) from error
                if not set(proposal.source_ids).issubset(source_ids):
                    raise DomainError("invalid_agent_input", {})
                selected = tuple(
                    profiles[name] for name in proposal.source_ids if name in profiles
                )
                candidate = compile_proposal(
                    proposal,
                    selected,
                    epoch_id=request.epoch_id,
                    forecast_provider=self.runtime.required_provider
                    or "seasonal_naive",
                )
                self.ledger.register_agent_candidate(candidate)
                if candidate.executable:
                    self.ledger.put_graph(candidate.graph)
                candidates.append(self.ledger.get_candidate(candidate.candidate_id))
            unique = {candidate.candidate_id: candidate for candidate in candidates}
            return {
                "candidateIds": list(unique),
                "candidates": [
                    candidate.model_dump(mode="json") for candidate in unique.values()
                ],
            }

        if request.tool == "explainRun":
            run_id = request.input.get("run_id")
            if set(request.input) != {"run_id"} or not isinstance(run_id, str):
                raise DomainError("invalid_agent_input", {})
            run = self.ledger.get_run(run_id)
            bindings = self.ledger.run_bindings(run_id)
            if not bindings or not set(bindings).issubset(source_ids):
                raise DomainError("run_lineage_mismatch", {})
            return {
                "text": f"Run {run.run_id} recorded {len(run.evidence_ids)} evidence item(s).",
                "evidenceIds": list(run.evidence_ids),
            }
        raise DomainError("unknown_agent_tool", {})

    @staticmethod
    def source_view(revision):
        return SourceView(
            source_id=revision.spec.source_id,
            revision=revision.revision,
            kind=revision.spec.kind,
            refresh_seconds=revision.spec.refresh_seconds,
        )

    def profile(self, source_id):
        registered = self.catalog.get(source_id)
        profile = inspect_source(registered.spec)
        context = provider_epoch_context(self.runtime)
        epoch_id = _digest({"profile": profile.model_dump(mode="json"), **context})
        job = self.queue.enqueue(
            f"discover/templates/{epoch_id}",
            {
                "kind": "discovery_templates",
                **({"provider_context": context} if context else {}),
                "source_id": source_id,
                "revision": registered.revision,
                "epoch_id": epoch_id,
                "profile": profile.model_dump(mode="json"),
            },
        )
        return profile, epoch_id, job.job_id

    def register_source(self, spec: SourceSpec):
        registered = self.catalog.append(SourceSpec.model_validate(spec.model_dump()))
        profile, epoch_id, job_id = self.profile(spec.source_id)
        return SourceRegistration(
            **self.source_view(registered).model_dump(),
            profile=profile,
            epoch_id=epoch_id,
            job_id=job_id,
        )

    def confirm_csv_source(self, request):
        logical_key = f"guided-csv/{_digest({'key': request.key})}"
        job_id = sha256(logical_key.encode()).hexdigest()
        intent = _digest(request.model_dump(mode="json", exclude={"adapter_session"}))
        try:
            job = self.queue.get(job_id)
        except DomainError as error:
            if error.code != "not_found":
                raise
        else:
            original = self.queue.original_payload(job_id)
            if original.get("confirmation_intent") != intent:
                raise DomainError("idempotency_conflict", {})
            registered = self.catalog.get(original["source_id"], original["revision"])
            return CsvConfirmationResult(
                **self.source_view(registered).model_dump(),
                profile=SourceProfile.model_validate(original["profile"]),
                epoch_id=original["epoch_id"],
                job_id=job.job_id,
                replayed=True,
                session_grant=request.adapter_session is not None
                and request.adapter_session == original.get("adapter_session"),
            )
        profile, snap = capture_confirmed_csv(
            request.spec, request.proposal_version, request.as_of
        )
        context = provider_epoch_context(self.runtime)
        epoch_id = _digest(
            {
                "profile": profile.model_dump(mode="json"),
                "snapshot_id": snap.snapshot_id,
                **context,
            }
        )
        with self.ledger._transaction() as connection:
            # Check again under the shared write lock: another request may have
            # reserved this key while this one captured the file.
            try:
                current = self.queue.get(job_id)
            except DomainError as error:
                if error.code != "not_found":
                    raise
            else:
                original = self.queue.original_payload(job_id)
                if original.get("confirmation_intent") != intent:
                    raise DomainError("idempotency_conflict", {})
                registered = self.catalog.get(
                    original["source_id"], original["revision"]
                )
                return CsvConfirmationResult(
                    **self.source_view(registered).model_dump(),
                    profile=SourceProfile.model_validate(original["profile"]),
                    epoch_id=original["epoch_id"],
                    job_id=current.job_id,
                    replayed=True,
                    session_grant=request.adapter_session is not None
                    and request.adapter_session == original.get("adapter_session"),
                )
            registered = self.catalog.append(request.spec, connection=connection)
            job = self.queue.enqueue(
                logical_key,
                {
                    "kind": "discovery_templates",
                    **({"provider_context": context} if context else {}),
                    "source_id": request.spec.source_id,
                    "revision": registered.revision,
                    "epoch_id": epoch_id,
                    "profile": profile.model_dump(mode="json"),
                    "frozen_snapshot": snap.model_dump(mode="json"),
                    "confirmed_capture": True,
                    "confirmation_intent": intent,
                    "adapter_session": request.adapter_session,
                },
                connection=connection,
            )
        return CsvConfirmationResult(
            **self.source_view(registered).model_dump(),
            profile=profile,
            epoch_id=epoch_id,
            job_id=job.job_id,
            replayed=False,
        )

    def refresh_source(self, source_id: str, request: SourceRefreshRequest):
        request = SourceRefreshRequest.model_validate(request.model_dump())
        registered = self.catalog.get(source_id)
        epoch_id = _digest({"source_id": source_id, "refresh_key": request.key})
        key = f"refresh/templates/{epoch_id}"
        context = provider_epoch_context(self.runtime)
        new_epoch_id = (
            _digest({"legacy_request_epoch": epoch_id, **context})
            if context
            else epoch_id
        )
        job_id = sha256(key.encode()).hexdigest()
        try:
            job = self.queue.get(job_id)
        except DomainError as error:
            if error.code != "not_found":
                raise
            profile = inspect_source(registered.spec)
            try:
                job = self.queue.enqueue(
                    key,
                    {
                        "kind": "discovery_templates",
                        **({"provider_context": context} if context else {}),
                        "source_id": source_id,
                        "revision": registered.revision,
                        "epoch_id": new_epoch_id,
                        "profile": profile.model_dump(mode="json"),
                    },
                )
            except DomainError as conflict:
                if conflict.code != "idempotency_conflict":
                    raise
                job = self.queue.get(job_id)
        if job.payload["revision"] != registered.revision:
            raise DomainError("idempotency_conflict", {"key": key})
        profile = SourceProfile.model_validate(job.payload["profile"])
        return SourceRegistration(
            **self.source_view(registered).model_dump(),
            profile=profile,
            epoch_id=job.payload["epoch_id"],
            job_id=job.job_id,
        )

    def candidate(self, request: CandidateRequest):
        request = CandidateRequest.model_validate(request.model_dump())
        profiles = tuple(self.profile(name)[0] for name in request.source_ids)
        epoch_id = _digest(
            {
                "profiles": [p.model_dump(mode="json") for p in profiles],
                "proposal": request.model_dump(mode="json"),
                **provider_epoch_context(self.runtime),
            }
        )
        candidate = compile_proposal(
            CandidateProposal(**request.model_dump()),
            profiles,
            epoch_id=epoch_id,
            forecast_provider=self.runtime.required_provider or "seasonal_naive",
        )
        if candidate.executable:
            compile_graph(
                candidate.graph,
                {k: p.capabilities() for k, p in self.runtime.providers.items()},
                {k: o.contract() for k, o in self.runtime.operators.items()},
            )
        self.ledger.put_discovery_epoch(
            DiscoveryEpoch(
                epoch_id=epoch_id,
                source_snapshot_ids=(),
                explored_candidate_ids=(candidate.candidate_id,),
                final_origin_ids=(),
            ),
            DiscoveryBudget(),
        )
        self.ledger.register_candidate(candidate)
        if candidate.executable:
            self.ledger.put_graph(candidate.graph)
        return candidate

    def watches(self):
        self.worker._sync_watches(self.now())
        return tuple(WatchView(**w.model_dump()) for w in self.ledger.list_watches())

    def create_question(self, request: QuestionCreateRequest) -> QuestionView:
        return self.ledger.create_question(request)

    def questions(self, *, offset: int, limit: int) -> QuestionPage:
        return self.ledger.list_questions(offset=offset, limit=limit)

    def question(self, question_id: str) -> QuestionView:
        return self.ledger.get_question(question_id)

    def patch_question(
        self, question_id: str, patch: QuestionTitlePatch
    ) -> QuestionView:
        updated = self.ledger.patch_question(question_id, patch)
        references = self.ledger.list_question_references(
            question_id, revision=updated.current_revision, limit=100
        )
        for reference in references.references:
            if reference.target_type != "watch":
                continue
            watch = self.ledger.get_watch(reference.target_id)
            if "status" in patch.model_fields_set:
                if updated.status != "open":
                    other_active = any(
                        link["status"] == "open" and link["question_id"] != question_id
                        for link in self.ledger.question_links_for_watch(watch.watch_id)
                    )
                    if (
                        not other_active
                        and watch.lifecycle != "unsupported"
                        and watch.lifecycle != "paused"
                    ):
                        self.ledger.advance_watch(
                            watch.watch_id,
                            {"kind": "paused"},
                            self.now(),
                            event_id=f"question-pause/{question_id}/{uuid4().hex}",
                        )
                elif watch.lifecycle == "paused":
                    self.ledger.advance_watch(
                        watch.watch_id,
                        {"kind": "resumed"},
                        self.now(),
                        event_id=f"question-resume/{question_id}/{uuid4().hex}",
                    )
            if "priority" in patch.model_fields_set:
                priorities = [
                    link["priority"]
                    for link in self.ledger.question_links_for_watch(watch.watch_id)
                    if link["status"] == "open"
                ]
                priority = min(priorities, default=updated.priority)
                if watch.priority != priority:
                    self.ledger.advance_watch(
                        watch.watch_id,
                        {"kind": "priority_changed", "priority": priority},
                        self.now(),
                        event_id=f"question-priority/{watch.watch_id}/{uuid4().hex}",
                    )
                self.queue.reprioritize_pending_watch(watch.watch_id, priority)
        return updated

    def source_subscriptions(
        self, *, offset: int, limit: int
    ) -> SourceSubscriptionPage:
        return self.ledger.list_source_subscriptions(offset=offset, limit=limit)

    def set_source_subscription(
        self, source_id: str, *, active: bool
    ) -> SourceSubscription:
        self.catalog.get(source_id)
        subscription = self.ledger.set_source_subscription(source_id, active=active)
        for watch in self.ledger.list_watches():
            if source_id not in watch.candidate.source_ids:
                continue
            kind = (
                "source_subscription_activated"
                if active
                else "source_subscription_revoked"
            )
            transition_id = f"{kind}/{source_id}/{watch.watch_id}"
            self.ledger.advance_watch(
                watch.watch_id,
                {"kind": kind},
                self.now(),
                event_id=transition_id,
            )
            for link in self.worker._question_links_for_watch(watch.watch_id):
                self.ledger.record_inbox_event(
                    question_id=link["question_id"],
                    revision=link["revision"],
                    event_kind=kind,
                    transition_id=transition_id,
                    watch_id=watch.watch_id,
                    summary=(
                        "La sottoscrizione worker alla fonte è stata riattivata."
                        if active
                        else "La sottoscrizione worker alla fonte è stata revocata. I refresh e i run in coda verranno soppressi."
                    ),
                    payload={"source_id": source_id, "active": active},
                )
        if active:
            self.worker._schedule_sources(self.now())
        return subscription

    def create_webhook_subscription(
        self, request: WebhookSubscriptionRequest
    ) -> WebhookSubscription:
        return self.ledger.create_webhook_subscription(request)

    def webhook_subscriptions(
        self, *, offset: int, limit: int
    ) -> WebhookSubscriptionPage:
        return self.ledger.list_webhook_subscriptions(offset=offset, limit=limit)

    def patch_webhook_subscription(
        self, subscription_id: str, patch: WebhookSubscriptionPatch
    ) -> WebhookSubscription:
        return self.ledger.set_webhook_subscription_active(
            subscription_id, active=patch.active
        )

    def webhook_deliveries(
        self, subscription_id: str, *, offset: int, limit: int
    ) -> WebhookDeliveryPage:
        return self.ledger.list_webhook_deliveries(
            subscription_id, offset=offset, limit=limit
        )

    def inbox_events(self, *, question_id: str | None, offset: int, limit: int):
        return self.ledger.list_inbox_events(
            question_id=question_id, offset=offset, limit=limit
        )

    def revise_question(
        self, question_id: str, request: QuestionRevisionRequest
    ) -> QuestionView:
        return self.ledger.revise_question(question_id, request)

    def question_revisions(
        self, question_id: str, *, offset: int, limit: int
    ) -> QuestionRevisionPage:
        return self.ledger.list_question_revisions(
            question_id, offset=offset, limit=limit
        )

    def question_revision(self, question_id: str, revision: int):
        return self.ledger.get_question_revision(question_id, revision)

    def link_question_reference(
        self, question_id: str, request: QuestionReferenceRequest
    ):
        self.ledger.get_question_revision(question_id, request.revision)
        if request.target_type == "candidate":
            self.ledger.get_candidate(request.target_id)
        elif request.target_type == "run":
            self.ledger.get_run(request.target_id)
        elif request.target_type == "watch":
            self.ledger.get_watch(request.target_id)
        elif request.target_type == "evaluation":
            self.ledger.get_evaluation(request.target_id)
        elif request.target_type == "backtest":
            self.backtest(request.target_id)
        elif request.target_type == "operation":
            self.ledger.get_operation(request.target_id)
        return self.ledger.link_question_reference(question_id, request)

    def question_references(
        self, question_id: str, *, revision: int | None, offset: int, limit: int
    ) -> QuestionReferencePage:
        return self.ledger.list_question_references(
            question_id, revision=revision, offset=offset, limit=limit
        )

    def snapshot_summary(self, snapshot_id: str) -> SnapshotSummary:
        from ..presentations import summarize_snapshot

        return summarize_snapshot(self.ledger.get_snapshot(snapshot_id))

    def snapshot_series(
        self, snapshot_id: str, *, offset: int, limit: int
    ) -> SnapshotSeriesPage:
        from ..presentations import snapshot_series_page

        return snapshot_series_page(
            self.ledger.get_snapshot(snapshot_id), offset=offset, limit=limit
        )

    def forecast_presentation(self, run_id: str):
        from ..presentations import present_run

        return present_run(self.ledger.get_run(run_id))

    def backtest_presentation(self, backtest_id: str, *, watch_id: str | None):
        from ..presentations import present_backtest, summarize_backtest_records

        report = self.backtest(backtest_id)
        origins = []
        offset = 0
        while True:
            page = self.backtest_origins(backtest_id, offset=offset, limit=50)
            origins.extend(page.origins)
            if len(origins) > 150:
                raise DomainError("invalid_backtest_record", {})
            if page.next_offset is None:
                break
            if page.next_offset <= offset or page.next_offset > 150:
                raise DomainError("invalid_backtest_record", {})
            offset = page.next_offset
        watch = self.watch(watch_id) if watch_id is not None else None
        return present_backtest(
            summarize_backtest_records(report, tuple(origins), watch)
        )

    def question_presentation(self, question_id: str, *, offset: int, limit: int):
        from ..presentations import present_question

        question = self.ledger.get_question(question_id)
        page = self.ledger.list_question_references(
            question_id, offset=offset, limit=limit
        )
        inbox = self.ledger.list_inbox_events(question_id=question_id, limit=10)
        return present_question(
            question,
            page.references,
            next_offset=page.next_offset,
            inbox_events=inbox.events,
            inbox_total_count=inbox.total_count,
        )

    def create_operation(self, request: OperationCreateRequest) -> OperationView:
        return self.ledger.create_operation(request)

    def operation(self, operation_id: str) -> OperationView:
        return self._operation_view(self.ledger.get_operation(operation_id))

    def operations(
        self, *, question_id: str | None, offset: int, limit: int
    ) -> OperationPage:
        page = self.ledger.list_operations(
            question_id=question_id, offset=offset, limit=limit
        )
        return page.model_copy(
            update={
                "operations": tuple(
                    self._operation_view(item) for item in page.operations
                )
            }
        )

    def update_operation(
        self, operation_id: str, request: OperationUpdateRequest
    ) -> OperationView:
        return self._operation_view(self.ledger.update_operation(operation_id, request))

    def _operation_view(self, view: OperationView) -> OperationView:
        if view.job_id is None:
            return view
        try:
            job = self.job(view.job_id)
        except DomainError as error:
            if error.code == "not_found":
                return view
            raise
        state = {
            "pending": "submitted",
            "running": "submitted",
            "completed": "completed",
            "failed": "failed",
        }.get(job.state, view.state)
        return view.model_copy(
            update={"state": state, "job_state": job.state, "job_error": job.error}
        )

    def _operation_source_ids(self, request: OperationSubmitRequest) -> tuple[str, ...]:
        job = request.request
        if job.kind == "run":
            candidate = self.ledger.get_candidate(request.candidate_id)
            if (
                not candidate.executable
                or candidate.unresolved
                or candidate.graph != job.graph
            ):
                raise DomainError("candidate_not_executable", {})
            declared = {
                config.source_id
                for node in job.graph.nodes
                if node.kind == "source"
                and isinstance((config := parse_node_config(node)), SourceConfig)
            }
            if set(job.snapshot_ids) != declared:
                raise DomainError("invalid_snapshot_bindings", {})
            return ()
        if job.kind == "backtest":
            return (job.source_id,)
        if job.kind == "configured_run":
            return ()
        if job.kind == "evaluation":
            self.ledger.run_bindings(job.run_id)
            return ()
        raise DomainError("invalid_operation_job", {})

    def submit_operation(
        self, operation_id: str, request: OperationSubmitRequest
    ) -> OperationView:
        request = OperationSubmitRequest.model_validate(request.model_dump())
        source_ids = self._operation_source_ids(request)
        self.ledger.reserve_operation_submission(
            operation_id, request, source_ids=source_ids
        )
        stored_view, stored_request = self.ledger.operation_submission(operation_id)
        logical_key = f"operation/{operation_id}"
        if stored_view.job_id is None:
            raise DomainError("operation_job_reservation_missing", {})
        try:
            job = self.queue.get(stored_view.job_id)
            if job.key != logical_key:
                raise DomainError("operation_job_mismatch", {})
        except DomainError as error:
            if error.code != "not_found":
                raise
            accepted = self.submit(stored_request.request, logical_key=logical_key)
            if accepted.job_id != stored_view.job_id:
                raise DomainError("operation_job_mismatch", {})
        self.ledger.mark_operation_enqueued(operation_id, stored_view.job_id)
        return self.operation(operation_id)

    def resume_operation(self, operation_id: str) -> OperationView:
        view, request = self.ledger.operation_submission(operation_id)
        logical_key = f"operation/{operation_id}"
        try:
            job = self.queue.get(view.job_id)
        except DomainError as error:
            if error.code != "not_found":
                raise
            return self.submit_operation(operation_id, request)
        if job.key != logical_key:
            raise DomainError("operation_job_mismatch", {})
        self.ledger.mark_operation_enqueued(operation_id, view.job_id)
        return self.operation(operation_id)

    def watch(self, watch_id: str):
        return WatchView(**self.ledger.get_watch(watch_id).model_dump())

    def watch_history(self, watch_id: str, *, offset: int, limit: int):
        entries, next_offset = self.ledger.watch_history_page(
            watch_id, offset=offset, limit=limit
        )
        return WatchHistoryPage(
            entries=tuple(
                WatchHistoryEntry(
                    **{
                        **entry,
                        "watch": WatchView(**entry["watch"].model_dump()),
                    }
                )
                for entry in entries
            ),
            next_offset=next_offset,
        )

    def watch_change_summary(
        self, watch_id: str, previous_run_id: str, current_run_id: str
    ) -> OpaqueDictionary:
        result = summarize_watch_change(
            self.ledger.get_watch(watch_id),
            self.ledger.get_run(previous_run_id),
            self.ledger.get_run(current_run_id),
        )
        return OpaqueDictionary(result)

    def create_watch(self, request: WatchRequest):
        request = WatchRequest.model_validate(request.model_dump())
        candidate = self.ledger.get_candidate(request.candidate_id)
        from ..forecast_policy import validate_primary_provider

        validate_primary_provider(candidate.graph, self.runtime.required_provider)
        watch = create_watch(
            candidate,
            watch_id=_digest(request.model_dump(mode="json")),
            next_due_at=request.next_due_at,
        )
        try:
            self.ledger.get_watch(watch.watch_id)
        except DomainError as error:
            if error.code != "not_found":
                raise
            self.ledger.put_watch(watch, now=self.now())
        return next(w for w in self.watches() if w.watch_id == watch.watch_id)

    def patch_watch(self, watch_id, patch: WatchPatch):
        patch = WatchPatch.model_validate(patch.model_dump(exclude_unset=True))
        self.worker._sync_watches(self.now())
        current = self.ledger.get_watch(watch_id)
        for name in ("muted", "priority"):
            if name not in patch.model_fields_set:
                continue
            value = getattr(patch, name)
            if getattr(current, name) == value:
                continue
            current = self.ledger.advance_watch(
                watch_id,
                {
                    "kind": "muted" if name == "muted" else "priority_changed",
                    name: value,
                },
                self.now(),
                event_id=uuid4().hex,
            )
        return WatchView(**current.model_dump())

    def _replay_run(self, request):
        from ..backtesting.contracts import canonical_json

        job_id = sha256(f"api/{request.key}".encode()).hexdigest()
        try:
            payload = self.queue.original_payload(job_id)
        except DomainError as error:
            if error.code == "not_found":
                return None
            raise
        if payload.get("kind") != "run":
            raise DomainError("idempotency_conflict", {"key": request.key})
        original = {
            "kind": "run",
            "graph": payload["graph"],
            "snapshot_ids": {
                name: snap["snapshot_id"] for name, snap in payload["snapshots"].items()
            },
            "as_of": payload["as_of"],
            "previous_run_id": payload.get("previous_run_id"),
            **(
                {"primary_node_id": payload["primary_node_id"]}
                if "primary_node_id" in payload
                else {}
            ),
        }
        original = backtesting.original_request(
            RunJobRequest.model_validate({**original, "key": request.key})
        )
        if canonical_json(original) != canonical_json(
            backtesting.original_request(request)
        ):
            raise DomainError("idempotency_conflict", {"key": request.key})
        return self.queue.get(job_id)

    def _enqueue_submission(self, key: str, payload: dict, *, replay_reserved: bool):
        try:
            return self.queue.enqueue(key, payload)
        except DomainError as error:
            if not replay_reserved or error.code != "idempotency_conflict":
                raise
            # The operation ledger has already bound this logical key to one
            # canonical confirmed request. If enqueue won before a crash, its
            # original payload is authoritative even if mutable source metadata
            # changed before the reconnect.
            job = self.queue.get(sha256(key.encode()).hexdigest())
            if job.key != key:
                raise DomainError("operation_job_mismatch", {}) from None
            return job

    def submit(self, request, *, logical_key: str | None = None):
        configured = None
        if isinstance(request, (ConfiguredRunJobRequest, BacktestJobRequest)):
            request = type(request).model_validate_json(request.model_dump_json())
            prior = (
                backtesting.replay_job(self.queue, request)
                if logical_key is None
                else None
            )
            if prior is not None:
                return self.job(prior.job_id)
            if isinstance(request, BacktestJobRequest):
                payload = backtesting.backtest_payload(
                    self.runtime, self.catalog, request
                )
                if logical_key is None:
                    try:
                        job = self.queue.enqueue(f"api/{request.key}", payload)
                    except DomainError as error:
                        if error.code != "idempotency_conflict":
                            raise
                        # A competing insert may bind a different current revision.
                        # Its original public intent, not derived metadata, wins.
                        job = backtesting.replay_job(self.queue, request)
                        if job is None:
                            raise
                else:
                    job = self._enqueue_submission(
                        logical_key, payload, replay_reserved=True
                    )
                return self.job(job.job_id)
            from ..forecast_policy import validate_selection

            validate_selection(self.runtime, request.selection)
            configured = request
            request = backtesting.configured_run(self.ledger, self.catalog, configured)
        if isinstance(request, RunJobRequest):
            request = RunJobRequest.model_validate(request.model_dump())
            prior = (
                self._replay_run(request)
                if configured is None and logical_key is None
                else None
            )
            if prior is not None:
                return self.job(prior.job_id)
            snapshots = {
                name: self.ledger.get_snapshot(sid)
                for name, sid in request.snapshot_ids.items()
            }
            validate_run(
                self.runtime,
                request.graph,
                snapshots,
                request.as_of,
                request.primary_node_id,
            )
            if self.ledger.scenario_for_graph(
                request.graph.graph_id, request.graph.version
            ) or any(
                any(a.startswith("assumed:") for a in s.assumptions)
                for s in snapshots.values()
            ):
                raise DomainError("scenario_required", {})
            for name, snapshot in snapshots.items():
                self.catalog.get(name)  # source registration precedes all A1 reads
                revisions = {
                    f"source_revision={r.revision}" for r in self.catalog.history(name)
                }
                if not revisions.intersection(snapshot.assumptions):
                    raise DomainError(
                        "source_snapshot_lineage_mismatch", {"source_id": name}
                    )
            if request.previous_run_id:
                prior = self.ledger.get_run(request.previous_run_id)
                if (
                    prior.graph_id,
                    prior.graph_version,
                    prior.as_of,
                    prior.scenario_id,
                    prior.state,
                ) != (
                    request.graph.graph_id,
                    request.graph.version,
                    request.as_of,
                    None,
                    "completed",
                ):
                    raise DomainError("run_lineage_mismatch", {})
            payload = {
                "kind": "run",
                "graph": request.graph.model_dump(mode="json"),
                "snapshots": {
                    name: s.model_dump(mode="json") for name, s in snapshots.items()
                },
                "as_of": request.as_of.isoformat(),
                "previous_run_id": request.previous_run_id,
                **(
                    {"primary_node_id": request.primary_node_id}
                    if request.primary_node_id is not None
                    else {}
                ),
            }
        elif isinstance(request, EvaluationJobRequest):
            run = self.ledger.get_run(request.run_id)
            actuals = self.ledger.get_snapshot(request.actuals_snapshot_id)
            if run.scenario_id or any(
                a.startswith("assumed:") for a in actuals.assumptions
            ):
                raise DomainError("assumed_evaluation_forbidden", {})
            if run.state != "completed":
                raise DomainError("run_lineage_mismatch", {})
            # One actuals Snapshot has no per-forecast source discriminator.
            # Derive target provenance from the stored graph, never from all
            # source bindings (which can include unrelated/known-future inputs).
            graph = self.ledger.get_graph(run.graph_id, run.graph_version)
            configs = {node.node_id: parse_node_config(node) for node in graph.nodes}
            bindings = self.ledger.run_bindings(run.run_id)
            history_sources = set()
            for node_id in run.results:
                config = configs.get(node_id)
                if isinstance(config, ForecastConfig):
                    history = configs.get(config.history)
                    if (
                        not isinstance(history, SourceConfig)
                        or history.source_id not in bindings
                    ):
                        raise DomainError("run_lineage_mismatch", {})
                    history_sources.add(history.source_id)
            if len(history_sources) != 1:
                raise DomainError("ambiguous_actuals_bindings", {})
            source_id = next(iter(history_sources))
            revisions = {
                f"source_revision={r.revision}" for r in self.catalog.history(source_id)
            }
            if not revisions.intersection(actuals.assumptions):
                raise DomainError("source_snapshot_lineage_mismatch", {})
            payload = request.model_dump(exclude={"key"})
        elif isinstance(request, ResumeJobRequest):
            self.worker._sync_watches(self.now())
            self.ledger.get_watch(request.watch_id)
            payload = request.model_dump(exclude={"key"})
        else:
            raise DomainError("invalid_job", {})
        if configured is not None:
            payload = {
                **payload,
                "kind": "configured_run",
                "request": backtesting.original_request(configured),
            }
        job = self._enqueue_submission(
            logical_key or f"api/{request.key}",
            payload,
            replay_reserved=logical_key is not None,
        )
        return self.job(job.job_id)

    def report_by_id(self, report_id):
        return BacktestStore(self.ledger).get_report_by_id(report_id)

    def backtest(self, backtest_id):
        return BacktestStore(self.ledger).get_report(backtest_id)

    def backtest_origins(self, backtest_id, *, offset=0, limit=25):
        store = BacktestStore(self.ledger)
        store.get_report(backtest_id)
        return store.list_origins(backtest_id, offset=offset, limit=limit)

    def events(self, after, limit=100):
        return tuple(
            public_event(event) for event in self.ledger.events_after(after, limit)
        )

    def job(self, job_id):
        job = self.queue.get(job_id)
        history = self.queue.history(job_id)
        current = next((h for h in history if h["attempt"] == job.attempt), {})
        return JobView(
            job_id=job.job_id,
            state=job.state,
            attempt=job.attempt,
            result=current.get("result"),
            error=public_failure(current.get("error")),
        )
