"""Discovery jobs for registered and revised source data."""

from __future__ import annotations

from datetime import datetime, timedelta

from .contracts import (
    Candidate,
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    QuestionReferenceRequest,
    Snapshot,
    SourceProfile,
)
from .discovery.candidates import TEMPLATES, CandidateProposal, compile_proposal
from .forecast_policy import provider_epoch_context
from .jobs import Job
from .runtime import _digest
from .sources.profiling import ingest_source, inspect_source
from .watches import create_watch


class DiscoveryJobsMixin:
    def _discover_templates(self, job: Job, now: datetime) -> dict:
        payload = dict(job.payload)
        registered = self.catalog.get(payload["source_id"])
        if registered.revision != payload["revision"]:
            raise DomainError("source_revision_changed", {})
        if payload.get("confirmed_capture"):
            profile = SourceProfile.model_validate(payload["profile"])
        else:
            profile = inspect_source(
                registered.spec, secret_resolver=self.secret_resolver
            )
            if profile != SourceProfile.model_validate(payload["profile"]):
                raise DomainError("source_profile_changed", {})
        if "frozen_snapshot" not in payload:
            snap = (
                None
                if profile.unresolved
                else ingest_source(
                    registered.spec, now, secret_resolver=self.secret_resolver
                )
            )
            payload["frozen_snapshot"] = snap.model_dump(mode="json") if snap else None
            self.queue.checkpoint(job, payload, self.runtime.clock())
        snap = (
            Snapshot.model_validate(payload["frozen_snapshot"])
            if payload["frozen_snapshot"]
            else None
        )
        candidates = tuple(
            compile_proposal(
                CandidateProposal(
                    template_id=template,
                    source_ids=(profile.source_id,),
                    reason=f"Registered {template} question for {profile.source_id}.",
                ),
                (profile,),
                epoch_id=payload["epoch_id"],
                forecast_provider=self.runtime.required_provider or "seasonal_naive",
            )
            for template in TEMPLATES
            if template != "declared_limit"
            or "operational_limit" in profile.proposed_mapping
        )
        ledger = self.runtime.ledger
        if snap:
            ledger.put_snapshot(snap, lease_guard=job.guard)
        ledger.put_discovery_epoch(
            DiscoveryEpoch(
                epoch_id=payload["epoch_id"],
                source_snapshot_ids=(snap.snapshot_id,) if snap else (),
                explored_candidate_ids=tuple(c.candidate_id for c in candidates),
                final_origin_ids=(),
            ),
            DiscoveryBudget(),
            lease_guard=job.guard,
        )
        for candidate in candidates:
            ledger.register_candidate(candidate, lease_guard=job.guard)
            if candidate.executable:
                ledger.put_graph(candidate.graph)
        if self.discovery_gateway is not None:
            self.queue.enqueue(
                f"discovery/agent/{payload['epoch_id']}",
                {
                    "kind": "discovery",
                    **(
                        {"provider_context": provider_epoch_context(self.runtime)}
                        if self.runtime.required_provider
                        else {}
                    ),
                    "epoch_id": payload["epoch_id"],
                    "source_ids": [profile.source_id],
                },
                lease_guard=job.guard,
            )
        return {
            "epoch_id": payload["epoch_id"],
            "candidate_ids": [c.candidate_id for c in candidates],
            "source_snapshot_ids": [snap.snapshot_id] if snap else [],
        }

    def _poll_discovery(self, job: Job, now: datetime) -> dict | None:
        if self.discovery_gateway is None:
            raise DomainError("discovery_gateway_unavailable", {})
        ledger, payload = self.runtime.ledger, dict(job.payload)
        epoch = ledger.get_discovery_epoch(payload["epoch_id"])
        if "session_id" not in payload:
            session_id = self.discovery_gateway.start(
                epoch.epoch_id, tuple(payload["source_ids"]), job.job_id
            )
            payload["session_id"] = session_id
            self.queue.checkpoint(job, payload, self.runtime.clock())
        candidates = self.discovery_gateway.poll(payload["session_id"])
        if candidates is None:
            self.queue.checkpoint(
                job,
                payload,
                self.runtime.clock(),
                next_due_at=now + timedelta(seconds=30),
            )
            return None
        for raw in candidates:
            candidate = Candidate.model_validate(raw.model_dump())
            if candidate.epoch_id != epoch.epoch_id:
                raise DomainError("epoch_lineage_mismatch", {})
            ledger.register_candidate(candidate, lease_guard=job.guard)
        return {
            "session_id": payload["session_id"],
            "candidate_ids": [c.candidate_id for c in candidates],
        }

    def _discover_refresh(self, job: Job, now: datetime) -> dict:
        ledger = self.runtime.ledger
        old = ledger.get_watch(job.payload["watch_id"])
        try:
            subscription = ledger.get_source_subscription(
                job.payload["profile"]["source_id"]
            )
        except DomainError as error:
            if error.code == "not_found":
                return {"suppressed": "source_subscription_missing"}
            raise
        if not subscription.active or old.lifecycle == "unsupported":
            return {"suppressed": "watch_or_source_inactive"}
        links = tuple(
            job.payload.get("question_links")
            or self._question_links_for_watch(old.watch_id)
        )
        profile = SourceProfile.model_validate(job.payload["profile"])
        snap = ledger.get_snapshot(job.payload["snapshot_id"])
        epoch_id = _digest(
            {
                "predecessor": old.candidate_id,
                **provider_epoch_context(self.runtime),
                "snapshot": snap.snapshot_id,
                "profile": profile.model_dump(mode="json"),
            }
        )
        candidate = compile_proposal(
            CandidateProposal(
                template_id=old.candidate.template_id,
                source_ids=old.candidate.source_ids,
                reason=old.candidate.reason,
                selection_method=old.candidate.protocol.selection_method,
            ),
            (profile,),
            epoch_id=epoch_id,
            forecast_provider=self.runtime.required_provider or "seasonal_naive",
        )
        # Changed inputs receive new reservations/evidence; old final origins are never reused.
        ledger.put_discovery_epoch(
            DiscoveryEpoch(
                epoch_id=epoch_id,
                source_snapshot_ids=(snap.snapshot_id,),
                explored_candidate_ids=(candidate.candidate_id,),
                final_origin_ids=(),
            ),
            ledger.discovery_budget(old.candidate.epoch_id),
            lease_guard=job.guard,
        )
        ledger.register_candidate(candidate, lease_guard=job.guard)
        if self.discovery_gateway is not None:
            self.queue.enqueue(
                f"discovery/agent/{epoch_id}",
                {
                    "kind": "discovery",
                    **(
                        {"provider_context": provider_epoch_context(self.runtime)}
                        if self.runtime.required_provider
                        else {}
                    ),
                    "epoch_id": epoch_id,
                    "source_ids": list(candidate.source_ids),
                },
                lease_guard=job.guard,
            )
        watch_id = _digest(
            {"predecessor": old.watch_id, "candidate": candidate.candidate_id}
        )
        # put_watch validates the initial state, so a retry must not attempt to overwrite later history.
        if not any(w.watch_id == watch_id for w in ledger.list_watches()):
            ledger.put_watch(
                create_watch(
                    candidate,
                    watch_id=watch_id,
                    next_due_at=now
                    + timedelta(
                        seconds=self.catalog.get(profile.source_id).spec.refresh_seconds
                    ),
                    source_snapshot_ids=(snap.snapshot_id,),
                    supersedes_watch_id=old.watch_id,
                ).model_copy(
                    update={
                        "muted": old.muted,
                        "priority": old.priority,
                        "requalification_due_at": now,
                        "qualification_snapshot_id": None,
                    }
                ),
                now=now,
                lease_guard=job.guard,
            )
        if (
            old.lifecycle == "paused"
            and old.migration_reason is None
            and ledger.get_watch(watch_id).lifecycle == "candidate"
        ):
            ledger.advance_watch(
                watch_id,
                {"kind": "paused"},
                now,
                event_id="inherited/pause",
                lease_guard=job.guard,
            )
        successor = ledger.get_watch(watch_id)
        for link in links:
            ledger.link_question_reference(
                link["question_id"],
                QuestionReferenceRequest(
                    key=f"worker-successor-candidate-{candidate.candidate_id}",
                    revision=link["revision"],
                    target_type="candidate",
                    target_id=candidate.candidate_id,
                    note="Candidate after a source revision",
                ),
                lease_guard=job.guard,
            )
            ledger.link_question_reference(
                link["question_id"],
                QuestionReferenceRequest(
                    key=f"worker-successor-watch-{watch_id}",
                    revision=link["revision"],
                    target_type="watch",
                    target_id=watch_id,
                    note="Watch for the revised source candidate",
                ),
                lease_guard=job.guard,
            )
        if candidate.executable:
            self._queue_watch_run(
                successor,
                snap,
                links,
                lease_guard=job.guard,
            )
        return {
            "candidate_id": candidate.candidate_id,
            "watch_id": watch_id,
            "epoch_id": epoch_id,
        }
