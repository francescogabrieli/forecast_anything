"""Shared discovery candidates, epochs and evaluation evidence."""

from datetime import UTC, datetime, timedelta

from forecast_anything.contracts import (
    DiscoveryEpoch,
    EvaluationContext,
    EvaluationRecord,
    SourceField,
    SourceProfile,
)
from forecast_anything.discovery.candidates import (
    CandidateProposal,
    compile_proposal,
)


def profile(**changes):
    return SourceProfile.model_validate(
        dict(
            source_id="sales",
            source_revision="mapping-v1",
            fields={"date": SourceField(data_type="datetime", nullable=False)},
            proposed_mapping={
                "series_id": {"constant": "sales"},
                "unit": {"constant": "count"},
                "event_time": "date",
                "available_at": "date",
                "revision": {"constant": "1"},
                "value": {"constant": 1},
                "frequency": {"constant": "D"},
                "timezone": {"constant": "UTC"},
                "calendar": {"constant": "gregorian"},
                "missing_values": {"constant": []},
            },
            unresolved=(),
            assumptions=(),
            sample_rows=({"date": "2026-01-01"},),
        )
        | changes
    )


def candidate(template="forecast_change", source=None):
    return compile_proposal(
        CandidateProposal(template_id=template, source_ids=("sales",), reason="Review"),
        (source or profile(),),
        epoch_id="epoch-1",
    )


def epoch_for(c, count=30, **changes):
    return DiscoveryEpoch.model_validate(
        dict(
            epoch_id=c.epoch_id,
            source_snapshot_ids=("snapshot-1",),
            explored_candidate_ids=(c.candidate_id,),
            final_origin_ids=tuple(f"origin-{i}" for i in range(count)),
            final_candidate_id=c.candidate_id,
        )
        | changes
    )


def evidence_for(c, epoch, loss=1.0, reference=2.0, **context_changes):
    # Frozen scripted final suite: one complete, disjoint daily target per origin.
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        EvaluationRecord(
            evaluation_id=f"evaluation-{i}",
            run_id=f"run-{i}",
            actuals_snapshot_id=f"actuals-{i}",
            status="evaluated",
            origin_count=1,
            metrics={
                "question": {"status": "evaluated", "mae": loss, "count": 1},
                "reference": {"status": "evaluated", "mae": reference, "count": 1},
            },
            assumptions=("frozen synthetic fixture; scripted baseline evidence",),
            discovery=EvaluationContext.model_validate(
                dict(
                    candidate_id=c.candidate_id,
                    protocol_id=c.protocol_id,
                    epoch_id=epoch.epoch_id,
                    origin_id=origin,
                    partition="final",
                    source_snapshot_ids=epoch.source_snapshot_ids,
                    target_start=start + timedelta(days=i),
                    target_end=start + timedelta(days=i),
                    temporal_valid=True,
                    semantic_valid=True,
                )
                | context_changes
            ),
        )
        for i, origin in enumerate(epoch.final_origin_ids)
    )
