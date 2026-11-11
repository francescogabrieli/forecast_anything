"""Group watch notifications and compare successive forecast emissions."""

from .contracts import DomainError, RunRecord, Watch


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
        or previous.state != "completed"
        or current.state != "completed"
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

            def target(t, node_id=node_id, series_id=series_id):
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
