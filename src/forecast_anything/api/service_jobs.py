"""Validated job submission and stored forecast and backtest results."""

from hashlib import sha256

from ..backtesting import service as backtesting
from ..backtesting.store import BacktestStore
from ..contracts import (
    BacktestJobRequest,
    ConfiguredRunJobRequest,
    DomainError,
    EvaluationJobRequest,
    JobView,
    ResumeJobRequest,
    RunJobRequest,
)
from ..graph import ForecastConfig, SourceConfig, compile_graph, parse_node_config
from ..providers.base import frequency_step, observation_grid
from .errors import public_failure


def validate_run(
    runtime, graph, snapshots, as_of, primary_node_id=None, *, model_selection=None
):
    from ..forecast_policy import ensure_required_model, validate_primary_provider

    provider = (
        model_selection.provider if model_selection else runtime.required_provider
    )
    validate_primary_provider(graph, provider, primary_node_id)
    if provider == runtime.required_provider:
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
                for s, unit in zip(config.series_ids, config.units, strict=False)
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


class JobOperations:
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
        configured = model_selection = None
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

            if request.selection_report_id is None or (
                self.runtime.required_provider is not None
                and request.selection.provider != self.runtime.required_provider
            ):
                validate_selection(self.runtime, request.selection)
            configured = request
            request, model_selection = backtesting.configured_run(
                self.runtime, self.catalog, configured
            )
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
                model_selection=model_selection,
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
            from ..evaluation.metrics import CURRENT_SCORING

            if logical_key is None:
                prior = backtesting.replay_job(self.queue, request)
                if prior is not None:
                    return self.job(prior.job_id)
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
            payload = {
                **backtesting.original_request(request),
                "scoring_version": CURRENT_SCORING,
            }
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
                **(
                    {"model_selection": model_selection.model_dump(mode="json")}
                    if model_selection
                    else {}
                ),
            }
        job = self._enqueue_submission(
            logical_key or f"api/{request.key}",
            payload,
            replay_reserved=logical_key is not None,
        )
        return self.job(job.job_id)

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

    def report_by_id(self, report_id):
        return BacktestStore(self.ledger).get_report_by_id(report_id)

    def backtest(self, backtest_id):
        return BacktestStore(self.ledger).get_report(backtest_id)

    def backtest_origins(self, backtest_id, *, offset=0, limit=25):
        store = BacktestStore(self.ledger)
        store.get_report(backtest_id)
        return store.list_origins(backtest_id, offset=offset, limit=limit)

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
