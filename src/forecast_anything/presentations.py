"""Bounded core projections shared by HTTP and MCP read surfaces."""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, FiniteFloat

from .backtesting.contracts import BacktestReport, OriginOutcome, PartitionScore
from .contracts import (
    Contract,
    ForecastSelection,
    Identifier,
    QuestionReference,
    QuestionView,
    RunRecord,
    Snapshot,
    SnapshotSeriesPage,
    SnapshotSeriesSummary,
    SnapshotSummary,
    WatchView,
)


class ForecastProviderUse(Contract):
    node_id: Identifier
    requested_provider: Identifier | None
    actual_provider: Identifier | None


class ForecastPresentationPoint(Contract):
    node_id: Identifier
    series_id: Identifier
    timestamp: AwareDatetime
    unit: Identifier
    representation: Literal["point", "marginal_quantiles", "joint_paths"]
    point: FiniteFloat | None
    quantiles: Annotated[dict[str, FiniteFloat], Field(max_length=3)]
    quantiles_truncated: bool
    sample_count: Annotated[int, Field(ge=0, strict=True)]


class ForecastPresentation(Contract):
    schema_version: Literal["forecast-presentation-v1"] = "forecast-presentation-v1"
    visual_destination: Literal["time_series"] = "time_series"
    run_id: Identifier
    primary_node_id: Identifier | None = None
    baseline_node_id: Identifier | None = None
    graph_id: Identifier
    graph_version: Annotated[int, Field(ge=1, strict=True)]
    as_of: AwareDatetime
    state: Identifier
    snapshot_ids: Annotated[tuple[Identifier, ...], Field(max_length=16)]
    snapshot_ids_truncated: bool
    providers: Annotated[tuple[ForecastProviderUse, ...], Field(max_length=16)]
    providers_truncated: bool
    points: Annotated[tuple[ForecastPresentationPoint, ...], Field(max_length=64)]
    total_point_count: Annotated[int, Field(ge=0, strict=True)]
    truncated: bool


class FinalOriginPoint(Contract):
    """Chart-ready per-origin scores, never forecast or source values."""

    ordinal: int
    target_start: AwareDatetime
    target_end: AwareDatetime
    status: Literal["evaluated", "excluded", "failed", "insufficient_evidence"]
    model_mae: float | None = None
    baseline_mae: float | None = None
    evaluation_id: Identifier | None = None
    reason_code: Identifier | None = None


class WatchBacktestSummary(Contract):
    migration_reason: Identifier | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    watch_id: Identifier
    lifecycle: Literal["candidate", "evaluating", "active", "paused", "unsupported"]
    quality: Literal["provisional", "usable", "stale", "degraded"]
    evidence_applicable: bool
    reevaluation_required: bool
    candidate_invalidated: bool
    operational: bool
    linked_to_backtest: bool
    decision_backtest_id: Identifier | None = None
    decision_action: Literal["activate", "provisional", "reject"] | None = None
    reason_codes: tuple[Identifier, ...] = ()
    final_evaluation_count: int | None = None


class BacktestSummary(Contract):
    backtest_id: Identifier
    report_id: Identifier
    source_id: Identifier
    source_revision: Identifier
    captured_at: AwareDatetime
    status: Literal["completed", "insufficient_evidence"]
    selection: ForecastSelection
    frequency: Identifier
    partitions: tuple[PartitionScore, ...]
    final_comparison: Literal[
        "model_lower_mae", "model_higher_mae", "equal_mae", "unavailable"
    ]
    relative_mae: float | None
    relative_mae_reason: (
        Literal["no_matched_cells", "zero_baseline_mae", "ratio_unrepresentable"] | None
    )
    metric_definition: str
    interpretation_limit: str
    final_origin_points: Annotated[tuple[FinalOriginPoint, ...], Field(max_length=50)]
    assumptions: tuple[str, ...]
    watch: WatchBacktestSummary | None = None


class BacktestPresentation(Contract):
    schema_version: Literal["backtest-presentation-v1"] = "backtest-presentation-v1"
    visual_destination: Literal["comparison"] = "comparison"
    summary: BacktestSummary


class QuestionPresentationReference(Contract):
    reference: QuestionReference
    applies_to_current_revision: bool


class QuestionPresentation(Contract):
    schema_version: Literal["question-presentation-v1"] = "question-presentation-v1"
    visual_destination: Literal["question_timeline"] = "question_timeline"
    question: QuestionView
    references: Annotated[
        tuple[QuestionPresentationReference, ...], Field(max_length=3)
    ]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None


def _bounded_samples(
    values, *, count: int, max_bytes: int
) -> tuple[tuple[str, ...], bool]:
    samples = []
    for value in sorted(set(values)):
        if len(samples) >= count:
            return tuple(samples), True
        if len(value.encode("utf-8")) > max_bytes:
            continue
        samples.append(value)
    return tuple(samples), len(samples) < len(set(values))


def _series(snapshot: Snapshot) -> tuple[SnapshotSeriesSummary, ...]:
    groups = defaultdict(list)
    for observation in snapshot.observations:
        groups[observation.series_id].append(observation)
    result = []
    for series_id, observations in sorted(groups.items()):
        units, units_truncated = _bounded_samples(
            (row.unit for row in observations), count=8, max_bytes=128
        )
        event_times = [row.event_time for row in observations]
        availability_times = [row.available_at for row in observations]
        result.append(
            SnapshotSeriesSummary(
                snapshot_id=snapshot.snapshot_id,
                series_id=series_id,
                observation_count=len(observations),
                missing_count=sum(row.value is None for row in observations),
                revision_count=len({row.revision for row in observations}),
                unit_count=len({row.unit for row in observations}),
                units=units,
                units_truncated=units_truncated,
                event_time_start=min(event_times) if event_times else None,
                event_time_end=max(event_times) if event_times else None,
                available_at_start=min(availability_times)
                if availability_times
                else None,
                available_at_end=max(availability_times)
                if availability_times
                else None,
            )
        )
    return tuple(result)


def summarize_snapshot(snapshot: Snapshot) -> SnapshotSummary:
    observations = snapshot.observations
    event_times = [row.event_time for row in observations]
    availability_times = [row.available_at for row in observations]
    assumptions, assumptions_truncated = _bounded_samples(
        snapshot.assumptions, count=16, max_bytes=256
    )
    return SnapshotSummary(
        snapshot_id=snapshot.snapshot_id,
        as_of=snapshot.as_of,
        observation_count=len(observations),
        series_count=len({row.series_id for row in observations}),
        missing_count=sum(row.value is None for row in observations),
        revision_count=len({row.revision for row in observations}),
        event_time_start=min(event_times) if event_times else None,
        event_time_end=max(event_times) if event_times else None,
        available_at_start=min(availability_times) if availability_times else None,
        available_at_end=max(availability_times) if availability_times else None,
        assumption_count=len(snapshot.assumptions),
        assumptions=assumptions,
        assumptions_truncated=assumptions_truncated,
    )


def snapshot_series_page(
    snapshot: Snapshot, *, offset: int = 0, limit: int = 25
) -> SnapshotSeriesPage:
    if (
        type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= 100
    ):
        raise ValueError("invalid snapshot series page")
    series = _series(snapshot)
    end = offset + limit
    return SnapshotSeriesPage(
        snapshot_id=snapshot.snapshot_id,
        series=series[offset:end],
        next_offset=end if end < len(series) else None,
    )


def present_run(run: RunRecord) -> ForecastPresentation:
    points = []
    providers = [
        ForecastProviderUse(
            node_id=node_id,
            requested_provider=run.requested_provider.get(node_id),
            actual_provider=run.actual_provider.get(node_id),
        )
        for node_id in sorted(run.results)[:16]
    ]
    total_point_count = sum(
        len(result.series_ids) * len(result.timestamps)
        for result in run.results.values()
    )

    def make_point(node_id, result, series_index, time_index):
        representation = (
            "joint_paths"
            if result.paths is not None
            else "marginal_quantiles"
            if result.quantiles is not None
            else "point"
        )
        all_quantile_keys = tuple(sorted(result.quantiles or {}))
        quantile_keys = tuple(
            key for key in all_quantile_keys if len(key.encode("utf-8")) <= 32
        )[:3]
        quantiles_truncated = len(quantile_keys) < len(all_quantile_keys)
        return ForecastPresentationPoint(
            node_id=node_id,
            series_id=result.series_ids[series_index],
            timestamp=result.timestamps[time_index],
            unit=result.units[series_index],
            representation=representation,
            point=(
                result.point[series_index][time_index]
                if result.point is not None
                else None
            ),
            quantiles={
                key: result.quantiles[key][series_index][time_index]
                for key in quantile_keys
            },
            quantiles_truncated=quantiles_truncated,
            sample_count=len(result.paths or ()),
        )

    def node_points(node_id, result):
        for series_index in range(len(result.series_ids)):
            for time_index in range(len(result.timestamps)):
                yield make_point(node_id, result, series_index, time_index)

    selected = set()
    primary_id = run.primary_node_id or ("model" if "model" in run.results else None)
    baseline_id = (
        "baseline"
        if run.graph_id.startswith("configured-")
        and primary_id == "model"
        and primary_id in run.results
        and "baseline" in run.results
        and run.actual_provider.get("baseline") == "seasonal_naive"
        else None
    )
    baseline = run.results.get(baseline_id) if baseline_id else None
    if primary_id in run.results and baseline is not None:
        baseline_series = {
            (s, baseline.units[i]): i for i, s in enumerate(baseline.series_ids)
        }
        baseline_times = {
            timestamp: i for i, timestamp in enumerate(baseline.timestamps)
        }
        for point in node_points(primary_id, run.results[primary_id]):
            key = (point.series_id, point.timestamp, point.unit)
            series_index = baseline_series.get((point.series_id, point.unit))
            time_index = baseline_times.get(point.timestamp)
            if (
                series_index is not None
                and time_index is not None
                and len(points) <= 62
            ):
                comparison = make_point("baseline", baseline, series_index, time_index)
                points.extend((point, comparison))
                selected.update(((primary_id, *key), ("baseline", *key)))
            if len(points) >= 63:
                break
    order = sorted(
        run.results, key=lambda node: (node != primary_id, node != "baseline", node)
    )
    for node_id in order:
        for point in node_points(node_id, run.results[node_id]):
            key = (node_id, point.series_id, point.timestamp, point.unit)
            if key not in selected and len(points) < 64:
                points.append(point)
            if len(points) == 64:
                break
        if len(points) == 64:
            break
    snapshots = tuple(sorted(set(run.snapshot_ids)))
    all_provider_nodes = sorted(run.actual_provider)
    return ForecastPresentation(
        run_id=run.run_id,
        primary_node_id=primary_id,
        baseline_node_id=baseline_id,
        graph_id=run.graph_id,
        graph_version=run.graph_version,
        as_of=run.as_of,
        state=run.state,
        snapshot_ids=snapshots[:16],
        snapshot_ids_truncated=len(snapshots) > 16,
        providers=tuple(providers),
        providers_truncated=len(all_provider_nodes) > 16,
        points=tuple(points),
        total_point_count=total_point_count,
        truncated=total_point_count > len(points),
    )


def summarize_backtest_records(
    report: BacktestReport,
    origins: tuple[OriginOutcome, ...],
    watch: WatchView | None = None,
) -> BacktestSummary:
    """Project stored report/origin/watch facts without recomputing a score."""
    report = BacktestReport.model_validate(report.model_dump())
    origins = tuple(OriginOutcome.model_validate(item.model_dump()) for item in origins)
    if any(item.backtest_id != report.backtest_id for item in origins) or len(
        {item.ordinal for item in origins}
    ) != len(origins):
        raise ValueError("summary origin lineage mismatch")

    final_score = next(
        score for score in report.partitions if score.partition == "final"
    )
    final_origins = tuple(
        sorted(
            (item for item in origins if item.partition == "final"),
            key=lambda item: item.ordinal,
        )
    )
    if len(final_origins) != final_score.planned:
        raise ValueError("summary final origin count mismatch")

    model_mae, baseline_mae = final_score.model_mae, final_score.baseline_mae
    if model_mae is None or baseline_mae is None:
        comparison = "unavailable"
    elif model_mae < baseline_mae:
        comparison = "model_lower_mae"
    elif model_mae > baseline_mae:
        comparison = "model_higher_mae"
    else:
        comparison = "equal_mae"

    watch_summary = None
    if watch is not None:
        watch = WatchView.model_validate(watch.model_dump())
        decision = watch.eligibility_decision
        linked = decision is not None and decision.backtest_id == report.backtest_id
        watch_summary = WatchBacktestSummary(
            watch_id=watch.watch_id,
            migration_reason=watch.migration_reason,
            lifecycle=watch.lifecycle,
            quality=watch.quality,
            evidence_applicable=watch.evidence_applicable,
            reevaluation_required=watch.reevaluation_required,
            candidate_invalidated=watch.candidate_invalidated,
            operational=watch.operational,
            linked_to_backtest=linked,
            decision_backtest_id=decision.backtest_id if decision else None,
            decision_action=decision.action if linked else None,
            reason_codes=decision.reason_codes if linked else (),
            final_evaluation_count=len(decision.evaluation_ids) if linked else None,
        )

    return BacktestSummary(
        backtest_id=report.backtest_id,
        report_id=report.report_id,
        source_id=report.source_id,
        source_revision=report.source_revision,
        captured_at=report.captured_at,
        status=report.status,
        selection=report.selection,
        frequency=report.frequency,
        partitions=report.partitions,
        final_comparison=comparison,
        relative_mae=final_score.relative_mae,
        relative_mae_reason=final_score.relative_mae_reason,
        metric_definition=(
            "MAE is mean absolute error on matched evaluated cells; lower is better. "
            "relative_mae is model_mae / baseline_mae."
        ),
        interpretation_limit=(
            "These scores describe only the recorded matched cells; they do not "
            "establish future accuracy or statistical significance."
        ),
        final_origin_points=tuple(
            FinalOriginPoint(
                ordinal=item.ordinal,
                target_start=item.target_start,
                target_end=item.target_end,
                status=item.status,
                model_mae=item.model_mae,
                baseline_mae=item.baseline_mae,
                evaluation_id=item.evaluation_id,
                reason_code=item.reason_code,
            )
            for item in final_origins
        ),
        assumptions=report.assumptions,
        watch=watch_summary,
    )


def present_backtest(summary: BacktestSummary) -> BacktestPresentation:
    return BacktestPresentation(summary=summary)


def present_question(
    question: QuestionView,
    references: tuple[QuestionReference, ...],
    *,
    next_offset: int | None,
) -> QuestionPresentation:
    return QuestionPresentation(
        question=question,
        references=tuple(
            QuestionPresentationReference(
                reference=reference,
                applies_to_current_revision=(
                    reference.revision == question.current_revision
                ),
            )
            for reference in references
        ),
        next_offset=next_offset,
    )
