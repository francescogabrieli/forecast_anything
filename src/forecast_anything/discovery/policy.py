"""Fail-closed qualification of frozen questions using Plan 02 evaluation records.

Thirty origins and positive skill are operational thresholds, not global false
positive control. Exploratory/corrected selection is never silently certified.
The Timestral acceptance and event-method gates remain pending.
"""

from datetime import timezone
from math import fsum, isfinite

from ..contracts import Candidate, DiscoveryEpoch, EligibilityDecision, EvaluationRecord
from .candidates import validate_candidate


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
