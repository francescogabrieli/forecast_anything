"""Create watches and apply explicit lifecycle transitions.

Pure transitions accept trusted EligibilityDecision objects. Durable callers use
Ledger.advance_watch, which additionally requires a Ledger-validated decision.
No event or score rewrite is needed to change current evidence applicability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, TypeAdapter, ValidationError

from .contracts import Candidate, DomainError, EligibilityDecision, Watch
from .watch_updates import (
    group_notifications as group_notifications,
)
from .watch_updates import (
    summarize_change as summarize_change,
)
from .watch_updates import (
    summarize_watch_change as summarize_watch_change,
)


def create_watch(
    candidate: Candidate,
    *,
    watch_id: str,
    next_due_at: datetime,
    policy_version: str = "discovery-v1",
    source_snapshot_ids: tuple[str, ...] = (),
    supersedes_watch_id: str | None = None,
) -> Watch:
    candidate = Candidate.model_validate(candidate.model_dump())
    return Watch(
        watch_id=watch_id,
        candidate_id=candidate.candidate_id,
        lifecycle="candidate" if candidate.executable else "unsupported",
        quality="provisional",
        graph_id=candidate.graph.graph_id,
        graph_version=candidate.graph.version,
        policy_version=policy_version,
        next_due_at=next_due_at,
        muted=False,
        candidate=candidate,
        source_snapshot_ids=source_snapshot_ids,
        supersedes_watch_id=supersedes_watch_id,
    )


def advance_watch(watch: Watch, event: dict, now: datetime) -> Watch:
    """Return a detached state; reject malformed/unknown events without mutation.

    Revision events name source_id or the replaced snapshot_id. origin_id can
    group notifications, but is never taken as a causal assertion. Pauses survive
    background quality updates. Resuming cannot bypass qualification or staleness.
    """
    watch = Watch.model_validate(watch.model_dump())
    try:
        now = TypeAdapter(AwareDatetime).validate_python(now)
    except ValidationError as error:
        raise DomainError("invalid_watch_time", {}) from error
    kind = event.get("kind")
    updates: dict[str, Any] = {}
    if kind == "evidence_qualified":
        raw = event.get("decision")
        try:
            decision = EligibilityDecision.model_validate(
                raw.model_dump() if isinstance(raw, EligibilityDecision) else raw
            )
        except ValidationError as error:
            raise DomainError("invalid_watch_decision", {}) from error
        candidate = watch.candidate
        if candidate is None or (
            decision.candidate_id,
            decision.protocol_id,
            decision.epoch_id,
            decision.policy_version,
        ) != (
            watch.candidate_id,
            candidate.protocol_id,
            candidate.epoch_id,
            watch.policy_version,
        ):
            raise DomainError("decision_lineage_mismatch", {})
        if decision.action == "activate" and not decision.evaluation_ids:
            raise DomainError("invalid_watch_decision", {})
        if set(decision.evaluation_ids) & set(watch.invalidated_evaluation_ids):
            raise DomainError("invalidated_watch_evidence", {})
        if watch.candidate_invalidated:
            raise DomainError("watch_candidate_invalidated", {})
        qualified = decision.action == "activate" and candidate.executable
        lifecycle = "active" if qualified else "evaluating"
        if watch.lifecycle in {"unsupported", "paused"}:
            lifecycle = watch.lifecycle
        updates = dict(
            lifecycle=lifecycle,
            quality="usable" if qualified else "provisional",
            eligibility_decision=decision,
            evidence_applicable=qualified,
            reevaluation_required=not qualified,
            qualification_snapshot_id=(
                event.get("snapshot_id")
                or (
                    watch.source_snapshot_ids[-1] if watch.source_snapshot_ids else None
                )
            ),
            requalification_due_at=None,
            requalification_reason=None,
            requalification_new_origins=0,
            quality_reason=None,
        )
        if "next_due_at" in event:
            try:
                deadline = TypeAdapter(AwareDatetime).validate_python(
                    event["next_due_at"]
                )
            except ValidationError as error:
                raise DomainError("invalid_refresh_deadline", {}) from error
            if deadline <= now:
                raise DomainError("invalid_refresh_deadline", {})
            updates["next_due_at"] = deadline
        if not qualified and event.get("requalification_due_at") is not None:
            updates["requalification_due_at"] = TypeAdapter(
                AwareDatetime
            ).validate_python(event["requalification_due_at"])
        if not qualified and event.get("requalification_reason") is not None:
            updates["requalification_reason"] = event["requalification_reason"]
        if qualified and updates.get("next_due_at", watch.next_due_at) <= now:
            raise DomainError("invalid_refresh_deadline", {})
    elif kind == "insufficient_evidence":
        updates = dict(
            lifecycle=(
                watch.lifecycle
                if watch.lifecycle in {"unsupported", "paused"}
                else "evaluating"
            ),
            quality="provisional",
            evidence_applicable=False,
            reevaluation_required=True,
        )
    elif kind == "refresh_expired":
        if now < watch.next_due_at:
            raise DomainError("refresh_not_expired", {})
        updates = {
            "quality": "stale",
            "reevaluation_required": True,
            "quality_reason": "polling_expired",
        }
    elif kind == "horizon_expired":
        if watch.forecast_horizon_end is not None and now <= watch.forecast_horizon_end:
            raise DomainError("forecast_horizon_not_expired", {})
        updates = {
            "quality": "stale",
            "reevaluation_required": True,
            "quality_reason": "horizon_expired",
        }
    elif kind == "source_unchanged":
        deadline = TypeAdapter(AwareDatetime).validate_python(event["next_due_at"])
        if deadline <= now:
            raise DomainError("invalid_refresh_deadline", {})
        horizon_end = event.get("forecast_horizon_end", watch.forecast_horizon_end)
        if horizon_end is not None:
            horizon_end = TypeAdapter(AwareDatetime).validate_python(horizon_end)
        expired = horizon_end is not None and now > horizon_end
        qualified = (
            watch.eligibility_decision is not None
            and watch.eligibility_decision.action == "activate"
            and watch.evidence_applicable
            and not watch.candidate_invalidated
        )
        updates = {
            "next_due_at": deadline,
            "quality": "stale" if expired else "usable" if qualified else watch.quality,
            "lifecycle": (
                "active"
                if qualified and not expired and watch.lifecycle != "paused"
                else watch.lifecycle
            ),
            "reevaluation_required": not qualified or expired,
            "quality_reason": "horizon_expired"
            if expired
            else None
            if qualified
            else watch.quality_reason,
        }
    elif kind == "data_appended":
        source_ids = watch.candidate.source_ids if watch.candidate else ()
        if event.get("source_id") not in source_ids:
            return watch
        snapshot_id = event.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise DomainError("invalid_watch_revision", {"field": "snapshot_id"})
        req_due = (
            TypeAdapter(AwareDatetime).validate_python(event["requalification_due_at"])
            if "requalification_due_at" in event
            else now
        )
        updates = dict(
            lifecycle=(
                watch.lifecycle
                if watch.lifecycle in {"unsupported", "paused"}
                else "evaluating"
            ),
            quality="provisional",
            evidence_applicable=False,
            reevaluation_required=True,
            candidate_invalidated=watch.candidate_invalidated,
            requalification_due_at=req_due,
            requalification_reason=None,
            requalification_new_origins=0,
            quality_reason=None,
            qualification_snapshot_id=(
                watch.qualification_snapshot_id
                or (
                    watch.source_snapshot_ids[-1]
                    if watch.eligibility_decision is not None
                    and watch.eligibility_decision.action == "activate"
                    and watch.source_snapshot_ids
                    else None
                )
            ),
            source_snapshot_ids=tuple(
                dict.fromkeys((*watch.source_snapshot_ids, snapshot_id))
            ),
        )
        if "next_due_at" in event:
            updates["next_due_at"] = TypeAdapter(AwareDatetime).validate_python(
                event["next_due_at"]
            )
    elif kind == "historical_availability_altered":
        source_ids = watch.candidate.source_ids if watch.candidate else ()
        if event.get("source_id") not in source_ids:
            return watch
        invalidated = tuple(
            dict.fromkeys(
                (
                    *watch.invalidated_evaluation_ids,
                    *(
                        watch.eligibility_decision.evaluation_ids
                        if watch.eligibility_decision
                        else ()
                    ),
                )
            )
        )
        updates = dict(
            lifecycle=(
                watch.lifecycle
                if watch.lifecycle in {"unsupported", "paused"}
                else "evaluating"
            ),
            quality="provisional",
            evidence_applicable=False,
            reevaluation_required=True,
            invalidated_evaluation_ids=invalidated,
            candidate_invalidated=True,
            next_due_at=now,
            requalification_due_at=now,
            requalification_reason="historical_availability_altered",
            quality_reason="historical_availability_altered",
        )
    elif kind in {"historical_correction", "historical_deletion", "invalid_append"}:
        source_ids = watch.candidate.source_ids if watch.candidate else ()
        if event.get("source_id") not in source_ids:
            return watch
        invalidated = tuple(
            dict.fromkeys(
                (
                    *watch.invalidated_evaluation_ids,
                    *(
                        watch.eligibility_decision.evaluation_ids
                        if watch.eligibility_decision
                        else ()
                    ),
                )
            )
        )
        updates = dict(
            lifecycle=(
                watch.lifecycle
                if watch.lifecycle in {"unsupported", "paused"}
                else "evaluating"
            ),
            quality="provisional",
            evidence_applicable=False,
            reevaluation_required=True,
            invalidated_evaluation_ids=invalidated,
            candidate_invalidated=True,
            next_due_at=now,
            requalification_due_at=now,
            requalification_reason=kind,
            quality_reason=kind,
        )
    elif kind == "run_issued":
        run_id = event.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise DomainError("invalid_watch_run", {})
        horizon_end = TypeAdapter(AwareDatetime).validate_python(
            event["forecast_horizon_end"]
        )
        snapshot_ids = tuple(event.get("snapshot_ids", ()))
        updates = {
            "last_run_id": run_id,
            "forecast_horizon_end": horizon_end,
            "source_snapshot_ids": tuple(
                dict.fromkeys((*watch.source_snapshot_ids, *snapshot_ids))
            ),
            "quality_reason": None
            if watch.quality == "usable"
            else watch.quality_reason,
        }
    elif kind == "requalification_waiting":
        due = TypeAdapter(AwareDatetime).validate_python(
            event["requalification_due_at"]
        )
        if due <= now:
            raise DomainError("invalid_requalification_deadline", {})
        count = event.get("new_origins", 0)
        if type(count) is not int or count < 0:
            raise DomainError("invalid_requalification_count", {})
        updates = {
            "lifecycle": (
                watch.lifecycle
                if watch.lifecycle in {"unsupported", "paused"}
                else "evaluating"
            ),
            "quality": "provisional",
            "evidence_applicable": False,
            "reevaluation_required": True,
            "requalification_due_at": due,
            "requalification_reason": event["reason"],
            "requalification_new_origins": count,
        }
    elif kind == "requalification_scheduled":
        count = event.get("new_origins", 0)
        if type(count) is not int or count < 30:
            raise DomainError("invalid_requalification_count", {})
        updates = {
            "lifecycle": (
                watch.lifecycle
                if watch.lifecycle in {"unsupported", "paused"}
                else "evaluating"
            ),
            "quality": "provisional",
            "evidence_applicable": False,
            "reevaluation_required": True,
            "requalification_due_at": None,
            "requalification_reason": "automatic_requalification_scheduled",
            "requalification_new_origins": count,
        }
    elif kind == "quality_degraded":
        updates = {"quality": "degraded", "reevaluation_required": True}
    elif kind == "muted":
        if type(event.get("muted")) is not bool:
            raise DomainError("invalid_watch_control", {"field": "muted"})
        updates = {"muted": event["muted"]}
    elif kind == "priority_changed":
        priority = event.get("priority")
        if type(priority) is not int or not 0 <= priority <= 5:
            raise DomainError("invalid_watch_control", {"field": "priority"})
        updates = {"priority": priority}
    elif kind == "provider_migration_required":
        updates = dict(
            lifecycle="paused",
            quality="stale",
            evidence_applicable=False,
            reevaluation_required=True,
            migration_reason="required_provider_migration",
        )
    elif kind == "source_subscription_revoked":
        updates = {
            "lifecycle": "unsupported",
            "quality": "stale",
            "reevaluation_required": True,
            "quality_reason": "source_subscription_revoked",
        }
    elif kind == "source_subscription_activated":
        if watch.quality_reason == "source_subscription_revoked":
            qualified = (
                watch.eligibility_decision is not None
                and watch.eligibility_decision.action == "activate"
                and watch.evidence_applicable
                and not watch.candidate_invalidated
                and (
                    watch.forecast_horizon_end is None
                    or now <= watch.forecast_horizon_end
                )
            )
            updates = {
                "lifecycle": "active" if qualified else "evaluating",
                "quality": "usable" if qualified else "provisional",
                "reevaluation_required": not qualified,
                "quality_reason": None,
            }
    elif kind == "paused":
        if watch.lifecycle != "unsupported":
            updates = {"lifecycle": "paused"}
    elif kind == "resumed":
        if watch.migration_reason:
            raise DomainError("required_provider_migration", {})
        if watch.lifecycle == "paused":
            qualified = (
                watch.eligibility_decision is not None
                and watch.eligibility_decision.action == "activate"
                and watch.evidence_applicable
                and not watch.reevaluation_required
            )
            updates = {"lifecycle": "active" if qualified else "evaluating"}
    elif kind in {"source_revised", "mapping_revised", "snapshot_revised"}:
        source_ids = watch.candidate.source_ids if watch.candidate else ()
        if kind == "snapshot_revised":
            dependent = event.get("snapshot_id") in watch.source_snapshot_ids
        else:
            dependent = event.get("source_id") in source_ids
        if not dependent:
            return watch
        if not isinstance(event.get("revision"), str) or not event["revision"].strip():
            raise DomainError("invalid_watch_revision", {})
        invalidated = tuple(
            dict.fromkeys(
                (
                    *watch.invalidated_evaluation_ids,
                    *(
                        watch.eligibility_decision.evaluation_ids
                        if watch.eligibility_decision
                        else ()
                    ),
                )
            )
        )
        updates = dict(
            lifecycle=(
                watch.lifecycle
                if watch.lifecycle in {"unsupported", "paused"}
                else "evaluating"
            ),
            quality="stale",
            evidence_applicable=False,
            reevaluation_required=True,
            invalidated_evaluation_ids=invalidated,
            candidate_invalidated=True,
            next_due_at=now,
        )
    else:
        raise DomainError("unknown_watch_event", {"kind": kind})
    return Watch.model_validate(watch.model_dump() | updates)
