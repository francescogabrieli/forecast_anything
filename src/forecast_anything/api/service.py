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
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EvaluationJobRequest,
    JobView,
    ResumeJobRequest,
    RunJobRequest,
    SourceProfile,
    SourceRefreshRequest,
    SourceRegistration,
    SourceSpec,
    SourceView,
    WatchPatch,
    WatchRequest,
    WatchView,
)
from ..discovery.agent_gateway import AgentOperationRequest, AgentOperationResponse
from ..discovery.candidates import CandidateProposal, compile_proposal
from ..graph import ForecastConfig, SourceConfig, compile_graph, parse_node_config
from ..jobs import JobQueue
from ..providers.base import frequency_step, observation_grid
from ..runtime import _digest
from ..sources.catalog import SourceCatalog
from ..sources.profiling import inspect_source
from ..store import _json
from ..watches import create_watch
from ..worker import Worker
from .errors import public_event, public_failure


def validate_run(runtime, graph, snapshots, as_of):
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
                    proposal, selected, epoch_id=request.epoch_id
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
        epoch_id = _digest({"profile": profile.model_dump(mode="json")})
        job = self.queue.enqueue(
            f"discover/templates/{epoch_id}",
            {
                "kind": "discovery_templates",
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

    def refresh_source(self, source_id: str, request: SourceRefreshRequest):
        request = SourceRefreshRequest.model_validate(request.model_dump())
        registered = self.catalog.get(source_id)
        epoch_id = _digest({"source_id": source_id, "refresh_key": request.key})
        key = f"refresh/templates/{epoch_id}"
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
                        "source_id": source_id,
                        "revision": registered.revision,
                        "epoch_id": epoch_id,
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
            epoch_id=epoch_id,
            job_id=job.job_id,
        )

    def candidate(self, request: CandidateRequest):
        request = CandidateRequest.model_validate(request.model_dump())
        profiles = tuple(self.profile(name)[0] for name in request.source_ids)
        epoch_id = _digest(
            {
                "profiles": [p.model_dump(mode="json") for p in profiles],
                "proposal": request.model_dump(mode="json"),
            }
        )
        candidate = compile_proposal(
            CandidateProposal(**request.model_dump()), profiles, epoch_id=epoch_id
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

    def create_watch(self, request: WatchRequest):
        request = WatchRequest.model_validate(request.model_dump())
        candidate = self.ledger.get_candidate(request.candidate_id)
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
        for name in patch.model_fields_set:
            self.ledger.advance_watch(
                watch_id,
                {
                    "kind": "muted" if name == "muted" else "priority_changed",
                    name: getattr(patch, name),
                },
                self.now(),
                event_id=uuid4().hex,
            )
        return next(w for w in self.watches() if w.watch_id == watch_id)

    def submit(self, request):
        configured = None
        if isinstance(request, (ConfiguredRunJobRequest, BacktestJobRequest)):
            request = type(request).model_validate_json(request.model_dump_json())
            prior = backtesting.replay_job(self.queue, request)
            if prior is not None:
                return self.job(prior.job_id)
            if isinstance(request, BacktestJobRequest):
                payload = backtesting.backtest_payload(
                    self.runtime, self.catalog, request
                )
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
                return self.job(job.job_id)
            configured = request
            request = backtesting.configured_run(self.ledger, self.catalog, configured)
        if isinstance(request, RunJobRequest):
            request = RunJobRequest.model_validate(request.model_dump())
            snapshots = {
                name: self.ledger.get_snapshot(sid)
                for name, sid in request.snapshot_ids.items()
            }
            validate_run(self.runtime, request.graph, snapshots, request.as_of)
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
        job = self.queue.enqueue(f"api/{request.key}", payload)
        return self.job(job.job_id)

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
