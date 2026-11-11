"""Synchronize watches and publish forecast and source changes."""

from __future__ import annotations

from datetime import datetime

from .contracts import DomainError, QuestionReferenceRequest
from .jobs import Job
from .sources.catalog import source_revision


class WatchUpdatesMixin:
    def _sync_watches(self, now: datetime, *, lease_guard=None):
        """Apply expiry and registered mapping revisions before reading operational."""
        now = self._now(now)
        ledger = self.runtime.ledger
        for watch in ledger.list_watches():
            if self.runtime.required_provider is not None:
                from .forecast_policy import validate_primary_provider

                try:
                    if watch.candidate is None:
                        raise DomainError("missing_candidate_lineage", {})
                    validate_primary_provider(
                        watch.candidate.graph, self.runtime.required_provider
                    )
                except DomainError:
                    if watch.migration_reason is None:
                        ledger.advance_watch(
                            watch.watch_id,
                            {
                                "kind": "provider_migration_required",
                                "provider": self.runtime.required_provider,
                            },
                            now,
                            event_id=f"provider-migration/{self.runtime.required_provider}",
                            lease_guard=lease_guard,
                        )
                    continue
            if watch.next_due_at <= now:
                ledger.advance_watch(
                    watch.watch_id,
                    {"kind": "refresh_expired"},
                    now,
                    event_id=f"expiry/{watch.next_due_at.isoformat()}",
                    lease_guard=lease_guard,
                )
            if (
                watch.forecast_horizon_end is not None
                and watch.forecast_horizon_end < now
                and watch.quality_reason != "horizon_expired"
            ):
                current = ledger.advance_watch(
                    watch.watch_id,
                    {"kind": "horizon_expired"},
                    now,
                    event_id=f"horizon/{watch.last_run_id or watch.watch_id}",
                    lease_guard=lease_guard,
                )
                for link in self._question_links_for_watch(watch.watch_id):
                    ledger.record_inbox_event(
                        question_id=link["question_id"],
                        revision=link["revision"],
                        event_kind="horizon_expired",
                        transition_id=watch.last_run_id or watch.watch_id,
                        run_id=watch.last_run_id,
                        watch_id=watch.watch_id,
                        summary="L'orizzonte della previsione registrata è trascorso. Le evidenze storiche restano consultabili; non ci sono date future coperte.",
                        payload={
                            "quality": current.quality,
                            "reason": "horizon_expired",
                        },
                        lease_guard=lease_guard,
                    )
            for profile in watch.candidate.source_profiles:
                try:
                    registered = self.catalog.get(profile.source_id)
                except DomainError:
                    continue
                revision = source_revision(registered.spec)
                if revision != profile.source_revision:
                    ledger.advance_watch(
                        watch.watch_id,
                        {
                            "kind": "source_revised",
                            "source_id": profile.source_id,
                            "revision": revision,
                        },
                        now,
                        event_id=f"source/{profile.source_id}/{revision}",
                        lease_guard=lease_guard,
                    )

    def resume_watch(
        self, watch_id: str, now: datetime, *, event_id: str, lease_guard=None
    ):
        now = self._now(now)
        self._sync_watches(now, lease_guard=lease_guard)
        self.runtime.ledger.advance_watch(
            watch_id,
            {"kind": "resumed"},
            now,
            event_id=event_id,
            lease_guard=lease_guard,
        )
        # A replayed control event returns the current relevance, not a historic activation.
        return self.runtime.ledger.get_watch(watch_id)

    def _question_links_for_watch(self, watch_id: str) -> tuple[dict, ...]:
        return tuple(
            {
                "question_id": link["question_id"],
                "revision": link["revision"],
                "priority": link["priority"],
            }
            for link in self.runtime.ledger.question_links_for_watch(watch_id)
            if link["status"] == "open"
        )

    def _queue_watch_run(self, watch, snapshot, links, *, lease_guard=None):
        if watch.candidate is None or watch.lifecycle in {"paused", "unsupported"}:
            return None
        priorities = [watch.priority, *(link["priority"] for link in links)]
        return self.queue.enqueue(
            f"watch-run/{watch.watch_id}/{snapshot.snapshot_id}",
            {
                "kind": "run",
                "watch_id": watch.watch_id,
                "graph": watch.candidate.graph.model_dump(mode="json"),
                "snapshots": {
                    watch.candidate.source_ids[0]: snapshot.model_dump(mode="json")
                },
                "as_of": snapshot.as_of.isoformat(),
                "previous_run_id": watch.last_run_id,
                "snapshot_id": snapshot.snapshot_id,
                "question_links": links,
                "priority": min(priorities),
            },
            lease_guard=lease_guard,
        )

    def _queue_watch_rediscovery(
        self, watch, snapshot, profile, links, *, lease_guard=None
    ):
        return self.queue.enqueue(
            f"rediscover/{watch.watch_id}/{snapshot.snapshot_id}",
            {
                "kind": "discover_refresh",
                "watch_id": watch.watch_id,
                "snapshot_id": snapshot.snapshot_id,
                "profile": profile,
                "question_links": links,
            },
            lease_guard=lease_guard,
        )

    def _record_source_transition(
        self, watch, event, transition_id: str, links, *, lease_guard=None
    ):
        kind = event["kind"]
        summaries = {
            "historical_availability_altered": "È cambiata la disponibilità storica di un dato. La qualifica precedente è stata invalidata e un nuovo candidato è in preparazione.",
            "historical_correction": "La fonte ha corretto un dato passato. La qualifica precedente è stata invalidata e un nuovo candidato è in preparazione.",
            "historical_deletion": "La fonte ha rimosso un dato storico. La qualifica precedente è stata invalidata e un nuovo candidato è in preparazione.",
            "invalid_append": "La nuova riga non è un append valido. La qualifica precedente è stata invalidata e un nuovo candidato è in preparazione.",
            "source_revised": "È cambiata la mappatura o la revisione della fonte. La qualifica precedente è stata invalidata e un nuovo candidato è in preparazione.",
        }
        for link in links:
            self.runtime.ledger.record_inbox_event(
                question_id=link["question_id"],
                revision=link["revision"],
                event_kind=kind,
                transition_id=transition_id,
                watch_id=watch.watch_id,
                summary=summaries.get(
                    kind,
                    "La fonte è cambiata e la domanda richiede una nuova valutazione.",
                ),
                payload={
                    "source_id": event.get("source_id"),
                    "reason": kind,
                    "quality": "provisional",
                    "evidence_applicable": False,
                    "candidate_invalidated": True,
                },
                lease_guard=lease_guard,
            )

    def _publish_watch_run(self, run, payload: dict, job: Job) -> None:
        ledger = self.runtime.ledger
        watch = ledger.get_watch(payload["watch_id"])
        horizon_end = max(
            (
                timestamp
                for result in run.results.values()
                for timestamp in result.timestamps
            ),
            default=run.as_of,
        )
        watch = ledger.advance_watch(
            watch.watch_id,
            {
                "kind": "run_issued",
                "run_id": run.run_id,
                "forecast_horizon_end": horizon_end,
                "snapshot_ids": tuple(run.snapshot_ids),
            },
            self._now(run.as_of),
            event_id=f"run/{run.run_id}",
            lease_guard=job.guard,
        )
        for link in payload.get("question_links", ()):
            question_id, revision = link["question_id"], link["revision"]
            ledger.link_question_reference(
                question_id,
                QuestionReferenceRequest(
                    key=f"worker-run-{run.run_id}",
                    revision=revision,
                    target_type="run",
                    target_id=run.run_id,
                    note="Background forecast update",
                ),
                lease_guard=job.guard,
            )
            question = ledger.get_question(question_id)
            if question.status != "open" or question.current_revision != revision:
                continue
            provisional = (
                not watch.evidence_applicable or watch.quality == "provisional"
            )
            summary = (
                "Previsione aggiornata sui nuovi dati. Lo stato resta provvisorio in attesa della riqualifica scientifica su nuove origini."
                if provisional
                else "Nuova previsione disponibile; la qualifica scientifica corrente resta applicabile."
            )
            ledger.record_inbox_event(
                question_id=question_id,
                revision=revision,
                event_kind="forecast_issued",
                transition_id=run.run_id,
                run_id=run.run_id,
                watch_id=watch.watch_id,
                summary=summary,
                payload={
                    "quality": watch.quality,
                    "evidence_applicable": watch.evidence_applicable,
                },
                lease_guard=job.guard,
            )
