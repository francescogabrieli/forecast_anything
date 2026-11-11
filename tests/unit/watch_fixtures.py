"""Shared watch qualification, lineage and forecast run fixtures."""

from datetime import UTC, datetime, timedelta

from forecast_anything.contracts import (
    EligibilityDecision,
    ForecastResult,
    RunRecord,
    SourceProfile,
)
from forecast_anything.discovery.candidates import CandidateProposal, compile_proposal
from forecast_anything.watches import (
    advance_watch,
    create_watch,
)

NOW = datetime(2026, 10, 24, tzinfo=UTC)


def candidate(template="forecast_change", epoch_id="epoch"):
    mapping = {
        name: {"constant": value}
        for name, value in {
            "event_time": "2026-01-01T00:00:00Z",
            "available_at": "2026-01-01T00:00:00Z",
            "revision": "1",
            "value": 1,
            "series_id": "sales",
            "unit": "count",
            "frequency": "D",
            "timezone": "UTC",
            "calendar": "gregorian",
            "missing_values": [],
        }.items()
    }
    profile = SourceProfile(
        source_id="sales",
        source_revision="mapping-v1",
        fields={},
        proposed_mapping=mapping,
        unresolved=(),
        assumptions=(),
    )
    return compile_proposal(
        CandidateProposal(
            template_id=template, source_ids=("sales",), reason="Review sales"
        ),
        (profile,),
        epoch_id=epoch_id,
    )


def watch(template="forecast_change", watch_id="w"):
    return create_watch(
        candidate(template), watch_id=watch_id, next_due_at=NOW + timedelta(days=1)
    )


def decision(w, action="activate", **changes):
    return EligibilityDecision.model_validate(
        dict(
            action=action,
            reason_codes=("qualified_final_evidence",),
            candidate_id=w.candidate_id,
            protocol_id=w.candidate.protocol_id,
            epoch_id=w.candidate.epoch_id,
            evaluation_ids=("evaluation",),
            policy_version=w.policy_version,
        )
        | changes
    )


def active_watch(**changes):
    w = watch()
    return advance_watch(
        w, {"kind": "evidence_qualified", "decision": decision(w)}, NOW
    ).model_copy(update=changes)


def run(run_id, timestamps, point, series=("sales",), units=("count",), **changes):
    result = ForecastResult(
        provider_id="seasonal_naive",
        provider_revision="1",
        series_ids=series,
        timestamps=tuple(NOW + timedelta(days=d) for d in timestamps),
        units=units,
        point=point,
        quantiles=None,
        paths=None,
        sample_group_id=None,
        assumptions=(),
    )
    return RunRecord.model_validate(
        dict(
            run_id=run_id,
            graph_id=candidate().graph.graph_id,
            graph_version=1,
            as_of=NOW,
            snapshot_ids=(f"snapshot-{run_id}",),
            requested_provider={},
            actual_provider={},
            state="completed",
            results={"question": result},
            evidence_ids=(),
            scenario_id=None,
            parent_run_id=None,
        )
        | changes
    )
