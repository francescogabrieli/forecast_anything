"""Single-worker execution with renewable leases and restart-safe emissions."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from threading import Event, Thread
from uuid import uuid4

from .connectors.http_json import SecretResolver
from .contracts import (
    Candidate,
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EvaluationContext,
    GraphSpec,
    Snapshot,
    SourceProfile,
)
from .discovery.candidates import TEMPLATES, CandidateProposal, compile_proposal
from .evaluation.records import evaluate_run
from .jobs import Job, JobQueue
from .runtime import Runtime, _digest
from .sources.catalog import SourceCatalog, source_revision
from .sources.profiling import ingest_source, inspect_source
from .watches import create_watch


class Worker:
    def __init__(
        self,
        runtime: Runtime,
        queue: JobQueue,
        *,
        secret_resolver: SecretResolver | None = None,
        discovery_gateway=None,
        lease_seconds: int = 60,
    ):
        if runtime.ledger.path.resolve() != queue.ledger.path.resolve():
            raise DomainError("queue_ledger_mismatch", {})
        if type(lease_seconds) is not int or lease_seconds <= 0:
            raise DomainError("invalid_lease", {})
        self.lease_seconds = lease_seconds
        self.runtime, self.queue = runtime, queue
        self.owner = uuid4().hex
        self.catalog = SourceCatalog(runtime.ledger.path)
        self.secret_resolver = secret_resolver
        self.discovery_gateway = discovery_gateway

    @contextmanager
    def _lease(self, job: Job):
        stopped = Event()

        def renew():
            while not stopped.wait(self.lease_seconds / 3):
                try:
                    self.queue.renew(job, self.runtime.clock(), self.lease_seconds)
                except Exception:
                    # Commit-time fencing remains authoritative after a lost renewal.
                    return

        thread = Thread(target=renew, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join()

    def _now(self, supplied: datetime) -> datetime:
        return max(supplied, self.runtime.clock(), self.runtime.ledger.clock())

    def run_due(self, now: datetime, limit: int = 10) -> tuple[str, ...]:
        if type(limit) is not int or limit <= 0:
            raise DomainError("invalid_limit", {})
        self._sync_watches(self._now(now))
        self._schedule_sources(self._now(now))
        completed = []
        for _ in range(limit):
            job = self.queue.claim(self.owner, self._now(now), self.lease_seconds)
            if job is None:
                break
            with self._lease(job):
                try:
                    result = self._execute(job, self._now(now))
                except Exception as error:
                    details = (
                        error.model_dump()
                        if isinstance(error, DomainError)
                        else {
                            "code": "job_execution_error",
                            "details": {"type": type(error).__name__},
                        }
                    )
                    try:
                        self.queue.fail(job, self._now(now), details)
                    except DomainError as lost:
                        if lost.code != "lease_lost":
                            raise
                else:
                    if result is not None:
                        # An acknowledgement error leaves the attempt recoverable.
                        # It must never turn a published emission into a new attempt.
                        self.queue.complete(job, self._now(now), result)
            completed.append(job.job_id)
        return tuple(completed)

    def _execute(self, job: Job, now: datetime) -> dict | None:
        payload = job.payload
        if payload.get("kind") == "run":
            run = self.runtime.run(
                GraphSpec.model_validate(payload["graph"]),
                {
                    name: Snapshot.model_validate(value)
                    for name, value in payload["snapshots"].items()
                },
                datetime.fromisoformat(payload["as_of"]),
                job.emission_key,
                lease_guard=job.guard,
                previous_run_id=payload.get("previous_run_id"),
                scenario_id=payload.get("scenario_id"),
            )
            if run.state == "failed":
                raise DomainError("run_failed", {"run_id": run.run_id})
            return {"run_id": run.run_id}
        if payload.get("kind") == "evaluation":
            ledger = self.runtime.ledger
            run = ledger.get_run(payload["run_id"])
            record = evaluate_run(
                run,
                ledger.get_snapshot(payload["actuals_snapshot_id"]),
                ledger.get_graph(run.graph_id, run.graph_version),
            )
            if "discovery" in payload:
                record = record.model_copy(
                    update={
                        "discovery": EvaluationContext.model_validate(
                            payload["discovery"]
                        )
                    }
                )
            # The Ledger revalidates numerical scores, temporal lineage and reserved origins.
            ledger.append_evaluation(record, lease_guard=job.guard)
            return {"evaluation_id": record.evaluation_id}
        if payload.get("kind") == "source_refresh":
            return self._refresh_source(job, now)
        if payload.get("kind") == "discover_refresh":
            return self._discover_refresh(job, now)
        if payload.get("kind") == "discovery_templates":
            return self._discover_templates(job, now)
        if payload.get("kind") == "discovery":
            return self._poll_discovery(job, now)
        if payload.get("kind") == "watch_resume":
            watch = self.resume_watch(
                payload["watch_id"],
                now,
                event_id=job.emission_key,
                lease_guard=job.guard,
            )
            return {"watch_id": watch.watch_id}
        raise DomainError("unknown_job_kind", {"kind": payload.get("kind")})

    def _sync_watches(self, now: datetime, *, lease_guard=None):
        """Apply expiry and registered mapping revisions before reading operational."""
        now = self._now(now)
        ledger = self.runtime.ledger
        for watch in ledger.list_watches():
            if watch.next_due_at <= now:
                ledger.advance_watch(
                    watch.watch_id,
                    {"kind": "refresh_expired"},
                    now,
                    event_id=f"expiry/{watch.next_due_at.isoformat()}",
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

    def _schedule_sources(self, now: datetime):
        watches = self.runtime.ledger.list_watches()
        superseded = {w.supersedes_watch_id for w in watches}
        due = {}
        for watch in watches:
            if (
                watch.watch_id in superseded
                or watch.lifecycle == "unsupported"
                or watch.next_due_at > now
            ):
                continue
            for source_id in watch.candidate.source_ids:
                due[source_id] = min(
                    due.get(source_id, watch.next_due_at), watch.next_due_at
                )
        for source_id, deadline in due.items():
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
                    "SELECT payload FROM jobs WHERE state IN ('pending', 'running')"
                ).fetchall()
            if any(
                (p := json.loads(row[0])).get("kind") == "source_refresh"
                and p.get("source_id") == source_id
                and p.get("revision") == registered.revision
                for row in existing
            ):
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
                },
            )

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

    def _refresh_source(self, job: Job, now: datetime) -> dict:
        payload = job.payload
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
                self.runtime.ledger.put_snapshot(snap, lease_guard=job.guard)
                payload = {
                    **payload,
                    "snapshot_id": snap.snapshot_id,
                    "profile": profile.model_dump(mode="json"),
                }
                self.queue.checkpoint(job, payload, self.runtime.clock())
            snap = self.runtime.ledger.get_snapshot(payload["snapshot_id"])
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
        for watch in watches:
            if (
                watch.watch_id in superseded
                or payload["source_id"] not in watch.candidate.source_ids
                or snap.snapshot_id in watch.source_snapshot_ids
            ):
                continue
            self.runtime.ledger.advance_watch(
                watch.watch_id,
                {
                    "kind": "source_revised",
                    "source_id": payload["source_id"],
                    "revision": snap.snapshot_id,
                },
                now,
                event_id=f"snapshot/{snap.snapshot_id}",
                lease_guard=job.guard,
            )
            self.queue.enqueue(
                f"rediscover/{watch.watch_id}/{snap.snapshot_id}",
                {
                    "kind": "discover_refresh",
                    "watch_id": watch.watch_id,
                    "snapshot_id": snap.snapshot_id,
                    "profile": payload["profile"],
                },
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

    def _discover_refresh(self, job: Job, now: datetime) -> dict:
        ledger = self.runtime.ledger
        old = ledger.get_watch(job.payload["watch_id"])
        profile = SourceProfile.model_validate(job.payload["profile"])
        snap = ledger.get_snapshot(job.payload["snapshot_id"])
        epoch_id = _digest(
            {
                "predecessor": old.candidate_id,
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
                    supersedes_watch_id=old.watch_id,
                ).model_copy(update={"muted": old.muted, "priority": old.priority}),
                now=now,
                lease_guard=job.guard,
            )
        if (
            old.lifecycle == "paused"
            and ledger.get_watch(watch_id).lifecycle == "candidate"
        ):
            ledger.advance_watch(
                watch_id,
                {"kind": "paused"},
                now,
                event_id="inherited/pause",
                lease_guard=job.guard,
            )
        if candidate.executable:
            self.queue.enqueue(
                f"evaluate/{candidate.candidate_id}/{snap.snapshot_id}",
                {
                    "kind": "run",
                    "graph": candidate.graph.model_dump(mode="json"),
                    "snapshots": {profile.source_id: snap.model_dump(mode="json")},
                    "as_of": snap.as_of.isoformat(),
                },
                lease_guard=job.guard,
            )
        return {
            "candidate_id": candidate.candidate_id,
            "watch_id": watch_id,
            "epoch_id": epoch_id,
        }

    def _poll_discovery(self, job: Job, now: datetime) -> dict | None:
        if self.discovery_gateway is None:
            raise DomainError("discovery_gateway_unavailable", {})
        ledger, payload = self.runtime.ledger, dict(job.payload)
        epoch = ledger.get_discovery_epoch(payload["epoch_id"])
        if "session_id" not in payload:
            ledger.consume_discovery_tool_call(
                epoch.epoch_id, f"{job.job_id}/start", lease_guard=job.guard
            )
            session_id = self.discovery_gateway.start(
                epoch.epoch_id, tuple(payload["source_ids"]), job.job_id
            )
            payload["session_id"] = session_id
            self.queue.checkpoint(job, payload, self.runtime.clock())
        poll = payload.get("poll", 0)
        ledger.consume_discovery_tool_call(
            epoch.epoch_id, f"{job.job_id}/poll/{poll}", lease_guard=job.guard
        )
        candidates = self.discovery_gateway.poll(payload["session_id"])
        if candidates is None:
            payload["poll"] = poll + 1
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

    def _discover_templates(self, job: Job, now: datetime) -> dict:
        payload = dict(job.payload)
        registered = self.catalog.get(payload["source_id"])
        if registered.revision != payload["revision"]:
            raise DomainError("source_revision_changed", {})
        profile = inspect_source(registered.spec, secret_resolver=self.secret_resolver)
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
