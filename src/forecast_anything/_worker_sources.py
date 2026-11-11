"""Schedule and refresh registered sources for watches."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from .continuity import classify_snapshot_change
from .contracts import DomainError, SourceProfile
from .jobs import Job
from .sources.profiling import ingest_source, inspect_source


class SourceRefreshMixin:
    def _schedule_sources(self, now: datetime):
        watches = self.runtime.ledger.list_watches()
        superseded = {w.supersedes_watch_id for w in watches}
        with self.runtime.ledger._transaction() as connection:
            for watch in watches:
                for source_id in watch.candidate.source_ids:
                    connection.execute(
                        """INSERT OR IGNORE INTO source_subscriptions
                        (source_id, active, created_at, updated_at) VALUES (?, 1, ?, ?)""",
                        (source_id, now.isoformat(), now.isoformat()),
                    )
            subscriptions = {
                row[0]
                for row in connection.execute(
                    "SELECT source_id FROM source_subscriptions WHERE active = 1"
                ).fetchall()
            }
        due = {}
        for watch in watches:
            if (
                watch.watch_id in superseded
                or watch.lifecycle in {"unsupported", "paused"}
                or watch.migration_reason is not None
                or watch.next_due_at > now
            ):
                continue
            for source_id in watch.candidate.source_ids:
                if source_id not in subscriptions:
                    continue
                prior = due.get(source_id, (watch.next_due_at, watch.priority))
                due[source_id] = (
                    min(prior[0], watch.next_due_at),
                    min(prior[1], watch.priority),
                )
        for source_id, (deadline, priority) in due.items():
            try:
                registered = self.catalog.get(source_id)
            except DomainError:
                continue  # SourceSpec must be explicitly registered before any I/O.
            with self.runtime.ledger._connection() as connection:
                polling = connection.execute(
                    "SELECT revision, next_due_at FROM source_polling WHERE source_id = ?",
                    (source_id,),
                ).fetchone()
                existing = connection.execute(
                    "SELECT job_id, payload FROM jobs WHERE state IN ('pending', 'running')"
                ).fetchall()
            existing_source_job = next(
                (
                    (row[0], p)
                    for row in existing
                    if (p := json.loads(row[1])).get("kind") == "source_refresh"
                    and p.get("source_id") == source_id
                    and p.get("revision") == registered.revision
                ),
                None,
            )
            if existing_source_job is not None:
                self.queue.update_priority(existing_source_job[0], priority)
                continue
            if polling and polling[0] == registered.revision:
                if polling[1] > now.timestamp():
                    continue
                deadline = datetime.fromtimestamp(polling[1], now.tzinfo)
            self.queue.enqueue(
                f"refresh/{source_id}/{registered.revision}/{deadline.isoformat()}",
                {
                    "kind": "source_refresh",
                    "source_id": source_id,
                    "revision": registered.revision,
                    "as_of": deadline.isoformat(),
                    "priority": priority,
                },
            )

    def _refresh_source(self, job: Job, now: datetime) -> dict:
        payload = job.payload
        try:
            subscription = self.runtime.ledger.get_source_subscription(
                payload["source_id"]
            )
        except DomainError as error:
            if error.code != "not_found":
                raise
            return {"suppressed": "source_subscription_missing"}
        if not subscription.active:
            return {"suppressed": "source_subscription_revoked"}
        registered = self.catalog.get(payload["source_id"], payload["revision"])
        # Superseded configuration cannot invalidate watches or become the latest input.
        if self.catalog.get(payload["source_id"]).revision != registered.revision:
            raise DomainError("source_revision_superseded", {})
        try:
            if "snapshot_id" not in payload:
                snap = ingest_source(
                    registered.spec,
                    datetime.fromisoformat(payload["as_of"]),
                    secret_resolver=self.secret_resolver,
                )
                profile = inspect_source(
                    registered.spec, secret_resolver=self.secret_resolver
                )
                if not self.runtime.ledger.get_source_subscription(
                    payload["source_id"]
                ).active:
                    return {"suppressed": "source_subscription_revoked"}
                self.runtime.ledger.put_snapshot(snap, lease_guard=job.guard)
                payload = {
                    **payload,
                    "snapshot_id": snap.snapshot_id,
                    "profile": profile.model_dump(mode="json"),
                }
                job = self.queue.checkpoint(job, payload, self.runtime.clock())
            snap = self.runtime.ledger.get_snapshot(payload["snapshot_id"])
            if not self.runtime.ledger.get_source_subscription(
                payload["source_id"]
            ).active:
                return {"suppressed": "source_subscription_revoked"}
        except Exception:
            self._source_status(
                job,
                registered.revision,
                now,
                registered.spec.refresh_seconds,
                available=False,
            )
            for watch in self.runtime.ledger.list_watches():
                if payload["source_id"] in watch.candidate.source_ids:
                    self.runtime.ledger.advance_watch(
                        watch.watch_id,
                        {"kind": "quality_degraded"},
                        now,
                        event_id=f"unavailable/{job.emission_key}",
                        lease_guard=job.guard,
                    )
            raise
        watches = self.runtime.ledger.list_watches()
        superseded = {w.supersedes_watch_id for w in watches}
        if "question_links_by_watch" not in payload:
            payload = {
                **payload,
                "question_links_by_watch": {
                    watch.watch_id: list(self._question_links_for_watch(watch.watch_id))
                    for watch in watches
                    if payload["source_id"] in watch.candidate.source_ids
                },
            }
            job = self.queue.checkpoint(job, payload, self.runtime.clock())
        for watch in watches:
            if (
                watch.watch_id in superseded
                or payload["source_id"] not in watch.candidate.source_ids
                or watch.lifecycle == "unsupported"
            ):
                continue
            links = tuple(payload["question_links_by_watch"].get(watch.watch_id, ()))
            if snap.snapshot_id in watch.source_snapshot_ids:
                if watch.source_snapshot_ids[-1] == snap.snapshot_id:
                    event_id_prefix = "snapshot/"
                    history = self.runtime.ledger.watch_history(watch.watch_id)
                    append_transition = next(
                        (
                            entry
                            for entry in history
                            if entry["event_id"] == f"append/{snap.snapshot_id}"
                        ),
                        None,
                    )
                    correction_transition = next(
                        (
                            entry
                            for entry in history
                            if entry["event_id"].startswith(event_id_prefix)
                            and entry["event_id"].endswith(f"/{snap.snapshot_id}")
                        ),
                        None,
                    )
                    if append_transition is not None:
                        self._queue_watch_run(watch, snap, links, lease_guard=job.guard)
                    elif correction_transition is not None:
                        event = correction_transition["event"]
                        self._record_source_transition(
                            watch,
                            event,
                            correction_transition["event_id"],
                            links,
                            lease_guard=job.guard,
                        )
                        self._queue_watch_rediscovery(
                            watch,
                            snap,
                            payload["profile"],
                            links,
                            lease_guard=job.guard,
                        )
                continue
            previous = (
                self.runtime.ledger.get_snapshot(watch.source_snapshot_ids[-1])
                if watch.source_snapshot_ids
                else None
            )
            old_profile = next(
                (
                    item
                    for item in watch.candidate.source_profiles
                    if item.source_id == payload["source_id"]
                ),
                None,
            )
            profile = SourceProfile.model_validate(payload["profile"])
            change = (
                classify_snapshot_change(
                    previous,
                    snap,
                    now,
                    mapping_unchanged=(
                        old_profile is not None
                        and old_profile.source_revision == profile.source_revision
                        and old_profile.proposed_mapping == profile.proposed_mapping
                    ),
                )
                if previous is not None
                else None
            )
            next_due_at = now + timedelta(seconds=registered.spec.refresh_seconds)
            if change is not None and change.kind == "unchanged":
                was_horizon_expired = (
                    watch.forecast_horizon_end is not None
                    and now > watch.forecast_horizon_end
                    and watch.quality_reason != "horizon_expired"
                )
                current = self.runtime.ledger.advance_watch(
                    watch.watch_id,
                    {
                        "kind": "source_unchanged",
                        "next_due_at": next_due_at,
                    },
                    now,
                    event_id=f"unchanged/{snap.snapshot_id}/{next_due_at.isoformat()}",
                    lease_guard=job.guard,
                )
                if was_horizon_expired:
                    for link in self._question_links_for_watch(current.watch_id):
                        self.runtime.ledger.record_inbox_event(
                            question_id=link["question_id"],
                            revision=link["revision"],
                            event_kind="horizon_expired",
                            transition_id=f"horizon/{watch.last_run_id}",
                            run_id=watch.last_run_id,
                            watch_id=watch.watch_id,
                            summary="Dati invariati, ma l'orizzonte dell'ultima previsione è trascorso nel passato. Nessuna previsione attiva per date future.",
                            payload={"quality": "stale", "reason": "horizon_expired"},
                            lease_guard=job.guard,
                        )
                continue

            if (
                change is not None
                and change.kind == "append"
                and not watch.candidate_invalidated
            ) and len(watch.candidate.source_ids) == 1:
                self.runtime.ledger.advance_watch(
                    watch.watch_id,
                    {
                        "kind": "data_appended",
                        "source_id": payload["source_id"],
                        "snapshot_id": snap.snapshot_id,
                        "next_due_at": next_due_at,
                        "requalification_due_at": now,
                    },
                    now,
                    event_id=f"append/{snap.snapshot_id}",
                    lease_guard=job.guard,
                )
                self._queue_watch_run(watch, snap, links, lease_guard=job.guard)
                continue

            if change is None:
                event_kind = "source_revised"
                transition_reason = "mapping_changed"
            elif change.kind == "historical_availability_altered":
                event_kind = "historical_availability_altered"
                transition_reason = change.kind
            elif change.kind in {
                "historical_correction",
                "historical_deletion",
                "invalid_append",
            }:
                event_kind = change.kind
                transition_reason = change.kind
            else:
                event_kind = "source_revised"
                transition_reason = change.kind
            event = {"kind": event_kind, "source_id": payload["source_id"]}
            if event_kind == "source_revised":
                event["revision"] = snap.snapshot_id
            transition_id = f"snapshot/{transition_reason}/{snap.snapshot_id}"
            self.runtime.ledger.advance_watch(
                watch.watch_id,
                event,
                now,
                event_id=transition_id,
                lease_guard=job.guard,
            )
            self._record_source_transition(
                watch,
                event,
                transition_id,
                links,
                lease_guard=job.guard,
            )
            self._queue_watch_rediscovery(
                watch,
                snap,
                payload["profile"],
                links,
                lease_guard=job.guard,
            )
        self._source_status(
            job,
            registered.revision,
            now,
            registered.spec.refresh_seconds,
            snapshot_id=snap.snapshot_id,
            available=True,
        )
        return {"snapshot_id": snap.snapshot_id}

    def _source_status(
        self,
        job: Job,
        revision: str,
        now: datetime,
        seconds: int,
        *,
        snapshot_id=None,
        available: bool,
    ):
        with self.runtime.ledger._transaction(job.guard) as connection:
            connection.execute(
                "INSERT INTO source_polling VALUES (?, ?, ?, ?, ?) ON CONFLICT(source_id) DO UPDATE SET "
                "revision = excluded.revision, snapshot_id = COALESCE(excluded.snapshot_id, source_polling.snapshot_id), "
                "next_due_at = excluded.next_due_at, available = excluded.available",
                (
                    job.payload["source_id"],
                    revision,
                    snapshot_id,
                    (now + timedelta(seconds=seconds)).timestamp(),
                    int(available),
                ),
            )
