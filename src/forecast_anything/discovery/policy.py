"""Fail-closed qualification of frozen questions using Plan 02 evaluation records.

Thirty origins and positive skill are operational thresholds, not global false
positive control. Exploratory/corrected selection is never silently certified.
The Timestral acceptance and event-method gates remain pending.
"""

from datetime import timezone
from math import fsum, isfinite

from ..backtesting.contracts import BacktestPlan, BacktestReport, OriginOutcome
from ..contracts import (
    Candidate,
    DiscoveryEpoch,
    EligibilityDecision,
    EvaluationRecord,
    ForecastSelection,
)
from .candidates import TEMPLATES, validate_candidate


def candidate_backtest_selection(candidate: Candidate) -> ForecastSelection:
    """Derive the only supported replay selection from a frozen watch candidate."""
    candidate = Candidate.model_validate(candidate.model_dump())
    if (
        not candidate.executable
        or candidate.template_id not in {"expected_deviation", "forecast_change"}
        or candidate.protocol.criterion != "mae"
        or candidate.protocol.selection_method != "prespecified_holdout"
        or validate_candidate(candidate)
    ):
        raise ValueError("unsupported_watch_backtest_candidate")
    nodes = {node.node_id: node for node in candidate.graph.nodes}
    source, forecast, reference, question = (
        nodes.get(name) for name in ("source", "forecast", "reference", "question")
    )
    if (
        any(node is None for node in (source, forecast, reference, question))
        or len(candidate.source_ids) != 1
        or len(candidate.source_profiles) != 1
        or candidate.source_profiles[0].source_id != candidate.source_ids[0]
        or candidate.protocol.target_node_id != "question"
        or candidate.protocol.reference_node_id != "reference"
        or question.kind != "transform"
        or question.inputs != ("forecast",)
        or question.config.get("operator") != TEMPLATES[candidate.template_id]
        or forecast.kind != "forecast"
        or reference.kind != "forecast"
        or source.kind != "source"
    ):
        raise ValueError("unsupported_watch_backtest_candidate")
    model, baseline = forecast.config, reference.config
    model_options = model.get("options")
    baseline_options = baseline.get("options")
    if (
        not isinstance(model_options, dict)
        or not isinstance(baseline_options, dict)
        or type(baseline_options.get("period")) is not int
        or baseline_options["period"] < 1
    ):
        raise ValueError("unsupported_watch_backtest_candidate")
    return ForecastSelection(
        provider=model.get("provider"),
        horizon=model.get("horizon"),
        options=model_options,
        baseline_period=baseline_options["period"],
    )


def assess_candidate(
    candidate: Candidate, evidence: tuple[EvaluationRecord, ...], epoch: DiscoveryEpoch
) -> EligibilityDecision:
    candidate = Candidate.model_validate(candidate.model_dump())
    epoch = DiscoveryEpoch.model_validate(epoch.model_dump())
    evidence = tuple(EvaluationRecord.model_validate(e.model_dump()) for e in evidence)
    reject, provisional = list(validate_candidate(candidate)), []
    if not epoch.source_snapshot_ids:
        reject.append("missing_source_provenance")
    if (
        candidate.epoch_id != epoch.epoch_id
        or candidate.candidate_id not in epoch.explored_candidate_ids
    ):
        reject.append("epoch_lineage_mismatch")
    if epoch.final_candidate_id != candidate.candidate_id:
        provisional.append("final_block_not_reserved")
    if candidate.protocol.selection_method != "prespecified_holdout":
        provisional.append("selection_not_validated")
    if candidate.template_id == "declared_limit":
        # Plan 02's path method remains provisional. A proposal or a good Brier
        # score cannot lift its acceptance gate. No correction/CI is invented.
        provisional.append("event_method_provisional")
    if any(n.config.get("provider") == "timestral" for n in candidate.graph.nodes):
        provisional.append("timestral_acceptance_pending")
    losses, references, windows, origins, runs = [], [], [], set(), set()
    criterion = candidate.protocol.criterion
    for record in evidence:
        context = record.discovery
        if context is None or (
            context.candidate_id != candidate.candidate_id
            or context.protocol_id != candidate.protocol_id
            or context.epoch_id != epoch.epoch_id
            or context.source_snapshot_ids != epoch.source_snapshot_ids
        ):
            reject.append("evidence_lineage_mismatch")
            continue
        if (
            context.partition != "final"
            or context.origin_id not in epoch.final_origin_ids
        ):
            reject.append("nonfinal_evidence")
            continue
        if not context.temporal_valid:
            reject.append("temporal_violation")
        if not context.semantic_valid:
            reject.append("semantic_violation")
        if context.origin_id in origins or record.run_id in runs:
            provisional.append("duplicate_final_origin")
            continue
        origins.add(context.origin_id)
        runs.add(record.run_id)
        if record.status != "evaluated" or record.origin_count != 1:
            provisional.append("incomplete_final_evidence")
            continue
        target = record.metrics.get(candidate.protocol.target_node_id, {})
        reference = record.metrics.get(candidate.protocol.reference_node_id, {})
        if not isinstance(target, dict) or not isinstance(reference, dict):
            provisional.append("missing_matched_score")
            continue
        pair = (target.get(criterion), reference.get(criterion))
        if (
            any(
                score.get("status") != "evaluated"
                or type(score.get("count")) is not int
                or score["count"] <= 0
                for score in (target, reference)
            )
            or target.get("count") != reference.get("count")
            or any(
                type(value) not in (float, int) or not isfinite(value) or value < 0
                for value in pair
            )
        ):
            provisional.append("missing_matched_score")
            continue
        losses.append(pair[0])
        references.append(pair[1])
        windows.append(
            (
                context.target_start.astimezone(timezone.utc),
                context.target_end.astimezone(timezone.utc),
            )
        )
    windows.sort()
    if any(b[0] <= a[1] for a, b in zip(windows, windows[1:])):
        reject.append("overlapping_final_windows")
    if origins != set(epoch.final_origin_ids):
        provisional.append("incomplete_final_block")
    if len(losses) < 30:
        provisional.append("insufficient_final_origins")
    mean_loss = fsum(value / len(losses) for value in losses) if losses else None
    mean_reference = (
        fsum(value / len(references) for value in references) if references else None
    )
    if references and mean_reference == 0:
        provisional.append("undefined_reference_skill")
    elif references and mean_loss >= mean_reference:
        reject.append("nonpositive_final_skill")
    return EligibilityDecision(
        action="reject" if reject else "provisional" if provisional else "activate",
        reason_codes=tuple(dict.fromkeys(reject + provisional))
        or ("qualified_final_evidence",),
        candidate_id=candidate.candidate_id,
        protocol_id=candidate.protocol_id,
        epoch_id=epoch.epoch_id,
        evaluation_ids=tuple(record.evaluation_id for record in evidence),
    )


def assess_candidate_backtest(
    candidate: Candidate,
    report: BacktestReport,
    plan: BacktestPlan,
    outcomes: tuple[OriginOutcome, ...],
) -> EligibilityDecision:
    """Apply the watch policy to a report explicitly bound to its frozen candidate."""
    candidate = Candidate.model_validate(candidate.model_dump())
    report = BacktestReport.model_validate(report.model_dump())
    plan = BacktestPlan.model_validate(plan.model_dump())
    outcomes = tuple(
        OriginOutcome.model_validate(item.model_dump()) for item in outcomes
    )
    reject, provisional = [], []
    try:
        selection = candidate_backtest_selection(candidate)
    except ValueError as error:
        reject.append(str(error))
        selection = None
    profile_revision = (
        candidate.source_profiles[0].source_revision
        if len(candidate.source_profiles) == 1
        else None
    )
    if (
        plan.watch_id is None
        or plan.candidate_id != candidate.candidate_id
        or plan.backtest_id != report.backtest_id
        or report.backtest_id != plan.backtest_id
        or report.source_id
        != (candidate.source_ids[0] if len(candidate.source_ids) == 1 else None)
        or not profile_revision
        or report.source_revision != profile_revision
        or report.source_revision != plan.archive.source_revision
        or plan.archive.source_id != report.source_id
        or report.selection != selection
        or plan.selection != selection
    ):
        reject.append("backtest_lineage_mismatch")
    if report.protocol_version != "backtest-v1":
        reject.append("unsupported_backtest_protocol")

    final_score = next(
        (score for score in report.partitions if score.partition == "final"), None
    )
    final = tuple(item for item in outcomes if item.partition == "final")
    if final_score is None or len(final) != final_score.planned:
        provisional.append("incomplete_final_block")
    if report.status != "completed":
        provisional.append("incomplete_backtest")
    if any(item.status != "evaluated" for item in final):
        provisional.append("incomplete_final_evidence")

    windows = sorted((item.target_start, item.target_end) for item in final)
    if any(
        current[0] <= previous[1] for previous, current in zip(windows, windows[1:])
    ):
        reject.append("overlapping_final_windows")
    evaluation_ids = tuple(
        item.evaluation_id
        for item in final
        if item.status == "evaluated" and item.evaluation_id is not None
    )
    if len(set(evaluation_ids)) != len(evaluation_ids):
        provisional.append("duplicate_final_evidence")
    if len(evaluation_ids) < 30:
        provisional.append("insufficient_final_origins")

    losses = tuple(item.model_mae for item in final if item.status == "evaluated")
    references = tuple(
        item.baseline_mae for item in final if item.status == "evaluated"
    )
    if losses and all(value is not None for value in (*losses, *references)):
        mean_loss = fsum(value / len(losses) for value in losses)
        mean_reference = fsum(value / len(references) for value in references)
        if mean_reference == 0:
            provisional.append("undefined_reference_skill")
        elif mean_loss >= mean_reference:
            reject.append("nonpositive_final_skill")
    elif final:
        provisional.append("missing_matched_score")

    return EligibilityDecision(
        action="reject" if reject else "provisional" if provisional else "activate",
        reason_codes=tuple(dict.fromkeys(reject + provisional))
        or ("qualified_final_backtest_evidence",),
        candidate_id=candidate.candidate_id,
        protocol_id=candidate.protocol_id,
        epoch_id=candidate.epoch_id,
        evaluation_ids=evaluation_ids,
        backtest_id=report.backtest_id,
    )
