"""Stored backtest evidence and comparison projections."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from ..backtesting.contracts import BacktestReport, OriginOutcome, PartitionScore
from ..contracts import (
    Contract,
    ForecastSelection,
    Identifier,
    WatchView,
)


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
