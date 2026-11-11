"""Availability-correct numerical replay over an immutable stored plan."""

from __future__ import annotations

from collections.abc import Iterable
from fractions import Fraction
from math import fsum, isfinite
from time import monotonic

from pydantic import ValidationError

from ..contracts import Capabilities, DomainError
from ..evaluation.metrics import relative_mae, scoring_version_from_assumptions
from ..evaluation.records import evaluate_run
from ..jobs import LeaseGuard
from ..providers.base import ForecastProvider
from ..runtime import Runtime
from ..temporal import freeze
from .contracts import (
    BacktestPlan,
    BacktestReport,
    OriginOutcome,
    Partition,
    PartitionScore,
)
from .planning import PARTITIONS, actuals_from_archive, build_forecast_graph
from .store import BacktestStore


def _optional(read, *args):
    try:
        return read(*args)
    except DomainError as error:
        if error.code != "not_found":
            raise
        return None


def _capability(provider: ForecastProvider) -> Capabilities:
    try:
        return Capabilities.model_validate_json(
            provider.capabilities().model_dump_json()
        )
    except (ValidationError, ValueError, TypeError):
        raise DomainError("provider_contract_changed", {}) from None


def _check_contracts(runtime: Runtime, plan: BacktestPlan) -> None:
    for name, expected in plan.provider_contracts.items():
        provider = runtime.providers.get(name)
        if provider is None or _capability(provider) != expected:
            raise DomainError("provider_contract_changed", {"provider_id": name})


class _BoundProvider:
    """Check actual adapter identities before Runtime can publish a result."""

    def __init__(self, provider, contract):
        self.provider, self.contract = provider, contract

    def capabilities(self):
        current = _capability(self.provider)
        if current != self.contract:
            raise DomainError(
                "provider_contract_changed", {"provider_id": self.contract.provider_id}
            )
        return current

    def forecast(self, request):
        result = self.provider.forecast(request)
        if (result.provider_id, result.provider_revision) != (
            self.contract.provider_id,
            self.contract.provider_revision,
        ):
            raise DomainError(
                "provider_contract_changed", {"provider_id": self.contract.provider_id}
            )
        return result


def _failure(ledger, run):
    events = ledger.run_events(run.run_id)
    failures = [event for event in events if event.kind == "run_failed"]
    if len(failures) != 1:
        raise DomainError("corrupt_backtest_run", {"run_id": run.run_id})
    failure = failures[0].payload
    code = failure.get("error", {}).get("code")
    if code in {"provider_contract_changed", "lease_lost"}:
        raise DomainError(code, {"run_id": run.run_id})
    # Runtime's error details can contain adapter messages. Only stable codes escape.
    return (
        "insufficient_history"
        if code == "insufficient_history"
        else "provider_output_invalid"
        if code == "invalid_provider_output"
        else "execution_error"
    )


def _history(plan, origin):
    history = freeze(
        tuple(
            row
            for row in plan.archive.observations
            if row.event_time <= origin.nominal_origin
        ),
        origin.issuance_time,
        (f"source_revision={plan.archive.source_revision}", *plan.archive.assumptions),
    )
    expected = tuple(
        timestamp for timestamp in plan.calendar if timestamp <= origin.nominal_origin
    )
    if tuple(row.event_time for row in history.observations) != expected:
        return None, "missing_history"
    if any(row.value is None for row in history.observations):
        return None, "missing_history"
    return history, None


def _validate_results(run, plan, origin, graph):
    expected = tuple(
        timestamp
        for timestamp in plan.calendar
        if origin.target_start <= timestamp <= origin.target_end
    )
    source = graph.nodes[0].config
    for node_id, result in run.results.items():
        if node_id not in {"baseline", "model"}:
            raise DomainError("corrupt_backtest_run", {"run_id": run.run_id})
        name = "seasonal_naive" if node_id == "baseline" else plan.selection.provider
        capability = plan.provider_contracts[name]
        if (result.provider_id, result.provider_revision) != (
            capability.provider_id,
            capability.provider_revision,
        ):
            raise DomainError("provider_contract_changed", {"provider_id": name})
        if (
            result.timestamps != expected
            or result.series_ids != tuple(source["series_ids"])
            or result.units != tuple(source["units"])
        ):
            raise DomainError("invalid_provider_output", {"run_id": run.run_id})
    if run.state == "completed" and set(run.results) != {"baseline", "model"}:
        raise DomainError("corrupt_backtest_run", {"run_id": run.run_id})


def _execute_origin(runtime, store, plan, actuals, origin, lease_guard):
    base = dict(
        backtest_id=plan.backtest_id, plan_id=plan.plan_id, **origin.model_dump()
    )
    history, reason = _history(plan, origin)
    if history is None:
        return OriginOutcome(**base, status="excluded", reason_code=reason)
    graph = build_forecast_graph(
        plan.archive.source_id,
        history,
        plan.selection,
        plan.frequency,
        graph_id=f"backtest-{plan.backtest_id}-{origin.ordinal}",
    )
    run = runtime.run(
        graph,
        {plan.archive.source_id: history},
        origin.issuance_time,
        f"backtest/{plan.backtest_id}/{origin.ordinal}",
        lease_guard=lease_guard,
    )
    _check_contracts(runtime, plan)
    _validate_results(run, plan, origin, graph)
    base["run_id"] = run.run_id
    if run.state != "completed":
        reason = _failure(store.ledger, run)
        return OriginOutcome(
            **base,
            status="excluded" if reason == "insufficient_history" else "failed",
            reason_code=reason,
        )
    try:
        evaluation = evaluate_run(
            run,
            actuals,
            graph,
            operators=runtime.operators,
            scoring_version=scoring_version_from_assumptions(plan.assumptions),
        )
    except DomainError as error:
        # Runtime checks shape; scoring additionally validates quantile semantics.
        # Keep poisoned emissions durable and non-scored without hiding other errors.
        if error.code not in {"invalid_quantiles", "numerical_score_unrepresentable"}:
            raise
        return OriginOutcome(
            **base,
            status="failed",
            reason_code="provider_output_invalid"
            if error.code == "invalid_quantiles"
            else error.code,
        )
    store.ledger.append_evaluation(evaluation, lease_guard=lease_guard)
    # Aggregate exactly the published record, including replayed evaluations.
    evaluation = store.ledger.get_evaluation(evaluation.evaluation_id)
    base["evaluation_id"] = evaluation.evaluation_id
    model, baseline = (
        evaluation.metrics.get("model", {}),
        evaluation.metrics.get("baseline", {}),
    )
    if (
        evaluation.status != "evaluated"
        or model.get("status") != "evaluated"
        or baseline.get("status") != "evaluated"
        or model.get("mae") is None
        or baseline.get("mae") is None
    ):
        return OriginOutcome(
            **base,
            status="insufficient_evidence",
            reason_code="unsupported_score_representation"
            if any(
                score.get("reason") == "no_supported_score_representation"
                or (score.get("status") == "evaluated" and score.get("mae") is None)
                for score in (model, baseline)
            )
            else "incomplete_actuals",
        )
    if model.get("count") != baseline.get("count") or not model.get("count"):
        raise DomainError(
            "incompatible_backtest_scores", {"evaluation_id": evaluation.evaluation_id}
        )
    return OriginOutcome(
        **base,
        status="evaluated",
        matched_count=model["count"],
        model_mae=model["mae"],
        baseline_mae=baseline["mae"],
    )


def _weighted_mean(outcomes, field, count):
    try:
        score = fsum(getattr(o, field) * o.matched_count for o in outcomes) / count
        if isfinite(score):
            return score
    except OverflowError:
        pass
    # A weighted average of finite nonnegative scores is bounded by their max;
    # only the intermediate numerator can overflow, never this exact average.
    return float(
        sum(Fraction(getattr(o, field)) * o.matched_count for o in outcomes) / count
    )


def partition_score(
    partition: Partition, outcomes: Iterable[OriginOutcome]
) -> PartitionScore:
    """Count-weight aggregate persisted same-cell scores, preserving all outcomes."""
    members = tuple(outcome for outcome in outcomes if outcome.partition == partition)
    evaluated = tuple(outcome for outcome in members if outcome.status == "evaluated")
    count = sum(outcome.matched_count for outcome in evaluated)
    scores = {}
    if count:
        model = _weighted_mean(evaluated, "model_mae", count)
        baseline = _weighted_mean(evaluated, "baseline_mae", count)
        ratio, reason = relative_mae(model, baseline)
        scores = dict(
            model_mae=model,
            baseline_mae=baseline,
            relative_mae=ratio,
            relative_mae_reason=reason,
        )
    return PartitionScore(
        partition=partition,
        planned=len(members),
        evaluated=len(evaluated),
        excluded=sum(outcome.status == "excluded" for outcome in members),
        failed=sum(outcome.status == "failed" for outcome in members),
        insufficient=sum(
            outcome.status == "insufficient_evidence" for outcome in members
        ),
        matched_count=count,
        **scores,
    )


def execute_backtest(
    runtime: Runtime,
    store: BacktestStore,
    plan: BacktestPlan,
    *,
    lease_guard: LeaseGuard | None,
    max_elapsed_seconds: int | None = None,
) -> BacktestReport:
    """Persist before inference, then reuse stable emissions/outcomes on recovery."""
    if runtime.ledger is not store.ledger:
        raise DomainError("backtest_ledger_mismatch", {})
    plan = BacktestPlan.model_validate_json(plan.model_dump_json())
    existing = _optional(store.get_report, plan.backtest_id)
    if existing is not None:
        # Identity and parent fencing still apply to an acknowledgement-only retry.
        store.put_plan(plan, lease_guard=lease_guard)
        return existing
    _check_contracts(runtime, plan)
    actuals = actuals_from_archive(plan.archive)
    if actuals.snapshot_id != plan.actuals_snapshot_id:
        raise DomainError("invalid_backtest_actuals", {})
    store.ledger.put_snapshot(actuals, lease_guard=lease_guard)
    store.put_plan(plan, lease_guard=lease_guard)
    plan = store.get_plan(plan.backtest_id)
    # The original registry and frozen plan cannot be mutated by adapter requests.
    bound_runtime = Runtime(
        runtime.ledger,
        {
            name: _BoundProvider(
                runtime.providers[name],
                Capabilities.model_validate_json(contract.model_dump_json()),
            )
            for name, contract in plan.provider_contracts.items()
        },
        runtime.operators,
        runtime.clock,
    )
    outcomes = []
    started = monotonic()
    for origin in plan.origins:
        if (
            max_elapsed_seconds is not None
            and monotonic() - started >= max_elapsed_seconds
        ):
            raise DomainError(
                "backtest_time_budget_exceeded",
                {"seconds": max_elapsed_seconds},
            )
        _check_contracts(runtime, plan)
        outcome = _optional(store.get_origin, plan.backtest_id, origin.ordinal)
        if outcome is None:
            outcome = _execute_origin(
                bound_runtime, store, plan, actuals, origin, lease_guard
            )
        store.put_origin(outcome, lease_guard=lease_guard)
        outcomes.append(outcome)
        if (
            max_elapsed_seconds is not None
            and monotonic() - started >= max_elapsed_seconds
        ):
            raise DomainError(
                "backtest_time_budget_exceeded",
                {"seconds": max_elapsed_seconds},
            )
    _check_contracts(runtime, plan)
    partitions = tuple(partition_score(partition, outcomes) for partition in PARTITIONS)
    report = BacktestReport(
        backtest_id=plan.backtest_id,
        plan_id=plan.plan_id,
        archive_id=plan.archive.archive_id,
        source_id=plan.archive.source_id,
        source_revision=plan.archive.source_revision,
        captured_at=plan.archive.captured_at,
        actuals_snapshot_id=actuals.snapshot_id,
        selection=plan.selection,
        settings=plan.settings,
        provider_contracts=plan.provider_contracts,
        frequency=plan.frequency,
        status="completed" if partitions[-1].matched_count else "insufficient_evidence",
        partitions=partitions,
        assumptions=plan.assumptions,
    )
    store.put_report(report, lease_guard=lease_guard)
    return store.get_report(plan.backtest_id)
