"""Explicit watch transitions and explanations of observed forecast differences.

Pure transitions accept trusted EligibilityDecision objects. Durable callers use
Ledger.advance_watch, which additionally requires a Ledger-validated decision.
No event or score rewrite is needed to change current evidence applicability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, TypeAdapter, ValidationError

from .contracts import Candidate, DomainError, EligibilityDecision, RunRecord, Watch


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
        updates = {"quality": "stale", "reevaluation_required": True}
    elif kind == "quality_degraded":
        updates = {"quality": "degraded", "reevaluation_required": True}
    elif kind == "muted":
        if type(event.get("muted")) is not bool:
            raise DomainError("invalid_watch_control", {"field": "muted"})
        updates = {"muted": event["muted"]}
    elif kind == "priority_changed":
        updates = {"priority": event.get("priority")}
    elif kind == "paused":
        if watch.lifecycle != "unsupported":
            updates = {"lifecycle": "paused"}
    elif kind == "resumed":
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


def group_notifications(notifications: tuple[dict, ...]) -> tuple[dict, ...]:
    """Group alert payloads by observed update origin, retaining each watch item.

    Callers assign origin IDs from source updates, not from coincident forecasts.
    Muted, paused or unqualified watches remain stored and visible separately.
    """
    groups: dict[str, dict] = {}
    for notification in notifications:
        watch = Watch.model_validate(notification["watch"].model_dump())
        if not watch.operational:
            continue
        origin = notification.get("origin_id")
        if not isinstance(origin, str) or not origin.strip():
            raise DomainError("missing_notification_origin", {})
        group = groups.setdefault(
            origin, {"origin_id": origin, "watch_ids": [], "notifications": []}
        )
        if watch.watch_id not in group["watch_ids"]:
            group["watch_ids"].append(watch.watch_id)
        group["notifications"].append(
            {
                **{key: value for key, value in notification.items() if key != "watch"},
                "watch_id": watch.watch_id,
                "priority": watch.priority,
            }
        )
    return tuple(
        {
            **group,
            "watch_ids": tuple(group["watch_ids"]),
            "notifications": tuple(group["notifications"]),
        }
        for group in groups.values()
    )


def summarize_change(previous: RunRecord, current: RunRecord) -> dict:
    """Compare common node/series/target identities, never horizon row positions.

    Marginal quantiles are compared only at identical levels. Joint paths have no
    stable sample identity across issues, so no sample-by-sample delta is claimed.
    Different graphs, vintages of a graph, and scenarios require explicit mapping.
    """
    previous = RunRecord.model_validate(previous.model_dump())
    current = RunRecord.model_validate(current.model_dump())
    if (
        (previous.graph_id, previous.graph_version, previous.scenario_id)
        != (current.graph_id, current.graph_version, current.scenario_id)
        or previous.state != "succeeded"
        or current.state != "succeeded"
        or current.as_of < previous.as_of
    ):
        raise DomainError("incomparable_runs", {})
    changes, added, removed, incomparable = [], [], [], []
    common_targets = 0
    for node_id in sorted(previous.results.keys() & current.results.keys()):
        left, right = previous.results[node_id], current.results[node_id]
        for result in (left, right):
            if len(set(result.series_ids)) != len(result.series_ids) or len(
                set(result.timestamps)
            ) != len(result.timestamps):
                raise DomainError("ambiguous_forecast_identity", {"node_id": node_id})
        left_times = {t: i for i, t in enumerate(left.timestamps)}
        right_times = {t: i for i, t in enumerate(right.timestamps)}
        for series_id in sorted(set(left.series_ids) & set(right.series_ids)):
            a, b = left.series_ids.index(series_id), right.series_ids.index(series_id)
            if left.units[a] != right.units[b]:
                incomparable.append(
                    {
                        "node_id": node_id,
                        "series_id": series_id,
                        "reason": "unit_changed",
                    }
                )
                continue

            def target(t):
                return {
                    "node_id": node_id,
                    "series_id": series_id,
                    "timestamp": t.isoformat(),
                }

            added.extend(
                target(t) for t in sorted(right_times.keys() - left_times.keys())
            )
            removed.extend(
                target(t) for t in sorted(left_times.keys() - right_times.keys())
            )
            matrices = []
            if left.point is not None and right.point is not None:
                matrices.append(("point", left.point, right.point))
            for level in sorted(
                (left.quantiles or {}).keys() & (right.quantiles or {}).keys()
            ):
                matrices.append(
                    (f"quantile:{level}", left.quantiles[level], right.quantiles[level])
                )
            for t in sorted(left_times.keys() & right_times.keys()):
                common_targets += 1
                for representation, before, after in matrices:
                    old, new = before[a][left_times[t]], after[b][right_times[t]]
                    if old != new:
                        changes.append(
                            {
                                **target(t),
                                "representation": representation,
                                "previous": old,
                                "current": new,
                                "delta": new - old,
                                "unit": left.units[a],
                            }
                        )
    return {
        "previous_run_id": previous.run_id,
        "current_run_id": current.run_id,
        "changes": changes,
        "added_targets": added,
        "removed_targets": removed,
        "common_target_count": common_targets,
        "incomparable": incomparable,
        "new_snapshot_ids": sorted(
            set(current.snapshot_ids) - set(previous.snapshot_ids)
        ),
        "new_evidence_ids": sorted(
            set(current.evidence_ids) - set(previous.evidence_ids)
        ),
        "explanation": "Observed forecast differences at common targets and newly available input snapshots; input dependencies do not establish causal effects.",
    }


def summarize_watch_change(
    watch: Watch, previous: RunRecord, current: RunRecord
) -> dict:
    """Add distinct question semantics even when templates share a level graph."""
    watch = Watch.model_validate(watch.model_dump())
    if (current.graph_id, current.graph_version) != (
        watch.graph_id,
        watch.graph_version,
    ):
        raise DomainError("watch_run_lineage_mismatch", {})
    return {
        **summarize_change(previous, current),
        "watch_id": watch.watch_id,
        "candidate_id": watch.candidate_id,
        "template_id": watch.candidate.template_id if watch.candidate else None,
        "question": watch.candidate.reason if watch.candidate else None,
        "dependencies": watch.candidate.source_ids if watch.candidate else (),
    }
