"""Single-worker execution with renewable leases and restart-safe emissions."""

from __future__ import annotations

import hmac
import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from hashlib import sha256
from threading import Event, Thread, Timer
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

from .backtesting.planning import prepare_backtest
from .backtesting.service import _provider_contracts, backtest_payload
from .backtesting.service import execute_job as execute_backtest_job
from .connectors.http_json import SecretResolver
from .continuity import classify_snapshot_change
from .contracts import (
    BacktestJobRequest,
    BacktestSettings,
    Candidate,
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EvaluationContext,
    GraphSpec,
    QuestionReferenceRequest,
    Snapshot,
    SourceProfile,
)
from .discovery.candidates import TEMPLATES, CandidateProposal, compile_proposal
from .discovery.policy import candidate_backtest_selection
from .evaluation.records import evaluate_run
from .forecast_policy import provider_epoch_context
from .jobs import Job, JobQueue
from .runtime import Runtime, _digest
from .sources.catalog import SourceCatalog, source_revision
from .sources.profiling import ingest_source, inspect_source
from .watches import create_watch


class _NoWebhookRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class Worker:
    def __init__(
        self,
        runtime: Runtime,
        queue: JobQueue,
        *,
        secret_resolver: SecretResolver | None = None,
        discovery_gateway=None,
        lease_seconds: int = 60,
        execution_timeout_handler=None,
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
        self.execution_timeout_handler = execution_timeout_handler

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

    @contextmanager
    def liveness(self, interval_seconds: float = 2, *, model_status=None):
        """Publish process liveness while the worker loop can be idle or busy."""
        if interval_seconds <= 0:
            raise DomainError("invalid_heartbeat_interval", {})
        stopped = Event()

        def publish():
            self.runtime.ledger.update_worker_heartbeat(
                self.owner,
                self.runtime.clock(),
                model_status=model_status() if model_status else None,
            )

        publish()

        def heartbeat_loop():
            while not stopped.wait(interval_seconds):
                publish()

        thread = Thread(target=heartbeat_loop, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join()
            self.runtime.ledger.clear_worker_heartbeat(self.owner)

    def _now(self, supplied: datetime) -> datetime:
        return max(supplied, self.runtime.clock(), self.runtime.ledger.clock())

    def run_due(self, now: datetime, limit: int = 10) -> tuple[str, ...]:
        if type(limit) is not int or limit <= 0:
            raise DomainError("invalid_limit", {})
        self._sync_watches(self._now(now))
        self._schedule_sources(self._now(now))
        self._schedule_requalifications(self._now(now))
        completed = []
        for _ in range(limit):
            job = self.queue.claim(self.owner, self._now(now), self.lease_seconds)
            if job is None:
                break
            with self._lease(job):
                try:
                    result = self._execute_with_budget(job, self._now(now))
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
                        automatic_requalification = bool(
                            job.payload.get("automatic_requalification")
                        )
                        webhook_delivery = job.payload.get("kind") == "webhook_delivery"
                        migration = details["code"] in {
                            "required_forecast_provider",
                            "ambiguous_primary_output",
                            "invalid_primary_output",
                        }
                        if migration:
                            details = {
                                "code": "required_provider_migration",
                                "details": {"provider": self.runtime.required_provider},
                            }
                        self.queue.fail(
                            job,
                            self._now(now),
                            details,
                            retry_seconds=(
                                details.get("details", {}).get("retry_after", 30)
                                if webhook_delivery
                                else 30
                            ),
                            max_attempts=1000000
                            if webhook_delivery
                            else 1
                            if migration
                            or details["code"]
                            in {
                                "model_not_prepared",
                                "required_model_unavailable",
                                "required_provider_migration",
                            }
                            or automatic_requalification
                            else 3,
                        )
                        if automatic_requalification:
                            self._record_requalification_failure(job, self._now(now))
                    except DomainError as lost:
                        if lost.code != "lease_lost":
                            raise
                else:
                    if result is not None:
                        # An acknowledgement error leaves the attempt recoverable.
                        # It must never turn a published emission into a new attempt.
                        self.queue.complete(job, self._now(now), result)
            completed.append(job.job_id)
            self._schedule_requalifications(self._now(now))
        return tuple(completed)

    def _execute_with_budget(self, job: Job, now: datetime):
        if not job.payload.get("automatic_requalification"):
            return self._execute(job, now)
        if self._has_persisted_requalification_report(job):
            # The immutable report is sufficient to finish publication without
            # starting inference again, even when the original deadline passed.
            return self._execute(job, now)
        deadline_text = job.payload.get("execution_deadline_at")
        remaining = (
            (datetime.fromisoformat(deadline_text) - now).total_seconds()
            if deadline_text
            else float(job.payload.get("execution_budget_seconds", 300))
        )
        if remaining <= 0:
            raise DomainError(
                "backtest_time_budget_exceeded",
                {"seconds": job.payload.get("execution_budget_seconds", 300)},
            )

        expired = Event()

        def on_timeout():
            expired.set()
            if self.execution_timeout_handler is not None:
                self.execution_timeout_handler()

        timer = Timer(remaining, on_timeout)
        timer.daemon = True
        timer.start()
        try:
            result = self._execute(job, now)
        finally:
            timer.cancel()
        if expired.is_set():
            raise DomainError(
                "backtest_time_budget_exceeded",
                {"seconds": job.payload.get("execution_budget_seconds", 300)},
            )
        return result

    def _has_persisted_requalification_report(self, job: Job) -> bool:
        if not job.payload.get("automatic_requalification"):
            return False
        from .backtesting.store import BacktestStore

        try:
            BacktestStore(self.runtime.ledger).get_report(job.job_id)
        except DomainError as error:
            if error.code == "not_found":
                return False
            raise
        return True

    def _execute(self, job: Job, now: datetime) -> dict | None:
        payload = job.payload
        context = provider_epoch_context(self.runtime)
        if (
            context
            and payload.get("kind") in {"discovery_templates", "discovery"}
            and payload.get("provider_context") != context
        ):
            raise DomainError(
                "required_forecast_provider",
                {"provider": self.runtime.required_provider},
            )
        if payload.get("kind") == "backtest":
            if payload.get("watch_id"):
                recovering_report = self._has_persisted_requalification_report(job)
                if not recovering_report:
                    watch = self.runtime.ledger.get_watch(payload["watch_id"])
                    if watch.lifecycle in {"paused", "unsupported"}:
                        return {
                            "suppressed": "watch_not_active",
                            "watch_id": watch.watch_id,
                        }
                    if watch.candidate_invalidated:
                        return {
                            "suppressed": "watch_candidate_invalidated",
                            "watch_id": watch.watch_id,
                        }
                    if payload.get("automatic_requalification") and (
                        not watch.source_snapshot_ids
                        or payload.get("snapshot_id") != watch.source_snapshot_ids[-1]
                    ):
                        return {
                            "suppressed": "source_snapshot_superseded",
                            "watch_id": watch.watch_id,
                        }
            return execute_backtest_job(
                self.runtime,
                self.catalog,
                job,
                now,
                secret_resolver=self.secret_resolver,
            )
        if payload.get("kind") == "webhook_delivery":
            return self._deliver_webhook(job, now)
        if payload.get("kind") in {"run", "configured_run"}:
            watch_id = payload.get("watch_id")
            if watch_id is not None:
                watch = self.runtime.ledger.get_watch(watch_id)
                if watch.lifecycle in {"paused", "unsupported"}:
                    return {"suppressed": "watch_not_active", "watch_id": watch_id}
                if watch.candidate_invalidated:
                    return {
                        "suppressed": "watch_candidate_invalidated",
                        "watch_id": watch_id,
                    }
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
                primary_node_id=payload.get("primary_node_id"),
            )
            if run.state == "failed":
                raise DomainError("run_failed", {"run_id": run.run_id})
            if watch_id is not None:
                self._publish_watch_run(run, payload, job)
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

    def _deliver_webhook(self, job: Job, now: datetime) -> dict:
        ledger = self.runtime.ledger
        attempt = ledger.begin_webhook_delivery(
            job.payload["delivery_id"], now, lease_guard=job.guard
        )
        if attempt["state"] == "pending":
            self.queue.checkpoint(
                job,
                job.payload,
                now,
                next_due_at=datetime.fromisoformat(attempt["next_attempt_at"]),
            )
            return None
        if attempt["state"] != "delivering":
            return {
                "delivery_id": job.payload["delivery_id"],
                "state": attempt["state"],
            }
        body = json.dumps(
            attempt["body"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Forecast-Event-Id": attempt["body"]["event_id"],
            "User-Agent": "ForecastAnything/1.0",
        }
        if attempt["secret"] is not None:
            signature = hmac.new(
                attempt["secret"].encode("utf-8"), body, sha256
            ).hexdigest()
            headers["X-Forecast-Signature"] = f"sha256={signature}"
        request = Request(
            attempt["target_url"], data=body, headers=headers, method="POST"
        )
        opener = build_opener(ProxyHandler({}), _NoWebhookRedirect())
        error_code = None
        try:
            with opener.open(request, timeout=10) as response:
                if not 200 <= response.status < 300:
                    error_code = f"http_status_{response.status}"
        except HTTPError as error:
            error_code = f"http_status_{error.code}"
        except (URLError, TimeoutError, OSError, ValueError):
            error_code = "delivery_request_failed"
        delivery = ledger.finish_webhook_delivery(
            job.payload["delivery_id"],
            now,
            error_code=error_code,
            lease_guard=job.guard,
        )
        if error_code is not None and delivery.state == "pending":
            retry_after = 30 if delivery.attempts == 1 else 120
            raise DomainError(
                "webhook_delivery_failed",
                {"retry_after": retry_after, "attempts": delivery.attempts},
            )
        return {
            "delivery_id": delivery.delivery_id,
            "state": delivery.state,
            "attempts": delivery.attempts,
        }

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

    def _wait_for_requalification(
        self, watch, links, now: datetime, *, reason: str, new_origins: int, due_at
    ) -> None:
        ledger = self.runtime.ledger
        if due_at <= now:
            due_at = now + timedelta(seconds=60)
        transition = f"{watch.source_snapshot_ids[-1] if watch.source_snapshot_ids else 'none'}/{reason}"
        current = ledger.advance_watch(
            watch.watch_id,
            {
                "kind": "requalification_waiting",
                "reason": reason,
                "new_origins": new_origins,
                "requalification_due_at": due_at,
            },
            now,
            event_id=(
                f"requalification-wait/{watch.watch_id}/{transition}/{due_at.isoformat()}"
            ),
        )
        for link in links:
            summary = (
                "La previsione resta provvisoria: la riqualifica attende 30 origini finali indipendenti. "
                f"Disponibili: {new_origins}."
                if reason == "insufficient_new_final_origins"
                else "La previsione resta provvisoria: il budget automatico di riqualifica è in cooldown."
                if reason == "automatic_requalification_budget_exhausted"
                else "La previsione resta provvisoria: i prerequisiti per riqualificare non sono ancora disponibili."
            )
            ledger.record_inbox_event(
                question_id=link["question_id"],
                revision=link["revision"],
                event_kind="requalification_waiting",
                transition_id=transition,
                watch_id=watch.watch_id,
                summary=summary,
                payload={
                    "reason": reason,
                    "new_final_origins": new_origins,
                    "quality": current.quality,
                },
            )

    def _schedule_requalifications(self, now: datetime) -> None:
        ledger = self.runtime.ledger
        for watch in ledger.list_watches():
            if (
                watch.lifecycle in {"paused", "unsupported"}
                or watch.candidate_invalidated
                or watch.quality not in {"provisional", "stale"}
                or watch.requalification_due_at is None
                or watch.requalification_due_at > now
                or not watch.source_snapshot_ids
            ):
                continue
            links = self._question_links_for_watch(watch.watch_id)
            if not links:
                continue
            try:
                if len(watch.candidate.source_ids) != 1:
                    raise DomainError("unsupported_watch_backtest", {})
                source_id = watch.candidate.source_ids[0]
                revision = self.catalog.get(source_id)
                qualification_snapshot = (
                    ledger.get_snapshot(watch.qualification_snapshot_id)
                    if watch.qualification_snapshot_id is not None
                    else None
                )
                latest_snapshot = ledger.get_snapshot(watch.source_snapshot_ids[-1])
                origin_floor = (
                    max(
                        (
                            row.event_time
                            for row in qualification_snapshot.observations
                            if row.available_at <= qualification_snapshot.as_of
                        ),
                        default=None,
                    )
                    if qualification_snapshot is not None
                    else None
                )
                selection = candidate_backtest_selection(watch.candidate)
                settings = BacktestSettings(max_origins_per_partition=30)
                contracts = _provider_contracts(self.runtime, selection)
                preview = prepare_backtest(
                    "requalification-preview",
                    revision,
                    latest_snapshot.observations,
                    selection,
                    settings,
                    latest_snapshot.as_of,
                    provider_contracts=contracts,
                    watch_id=watch.watch_id,
                    candidate_id=watch.candidate_id,
                    origin_target_after=origin_floor,
                )
            except (DomainError, ValueError):
                self._wait_for_requalification(
                    watch,
                    links,
                    now,
                    reason="insufficient_new_final_origins",
                    new_origins=0,
                    due_at=max(watch.next_due_at, now + timedelta(seconds=60)),
                )
                continue
            new_origins = sum(origin.partition == "final" for origin in preview.origins)
            if new_origins < 30:
                self._wait_for_requalification(
                    watch,
                    links,
                    now,
                    reason="insufficient_new_final_origins",
                    new_origins=new_origins,
                    due_at=max(watch.next_due_at, now + timedelta(seconds=60)),
                )
                continue

            cutoff = (now - timedelta(hours=24)).timestamp()
            eligible, blocked_until = [], []
            with ledger._connection() as connection:
                for link in links:
                    row = connection.execute(
                        "SELECT MIN(scheduled_at) FROM requalification_budgets WHERE question_id = ? AND scheduled_at > ?",
                        (link["question_id"], cutoff),
                    ).fetchone()
                    if row is None or row[0] is None:
                        eligible.append(link)
                    else:
                        blocked_until.append(
                            datetime.fromtimestamp(row[0] + 86400, now.tzinfo)
                        )
            if not eligible:
                self._wait_for_requalification(
                    watch,
                    links,
                    now,
                    reason="automatic_requalification_budget_exhausted",
                    new_origins=new_origins,
                    due_at=min(blocked_until, default=now + timedelta(hours=24)),
                )
                continue

            request_key = "auto-requalification/" + _digest(
                {
                    "watch_id": watch.watch_id,
                    "qualification_snapshot_id": watch.qualification_snapshot_id,
                    "source_snapshot_id": latest_snapshot.snapshot_id,
                    "questions": [link["question_id"] for link in eligible],
                    "budget_window": int(now.timestamp() // 86400),
                }
            )
            request = BacktestJobRequest(
                kind="backtest",
                key=request_key,
                source_id=source_id,
                selection=selection,
                settings=settings,
                watch_id=watch.watch_id,
            )
            payload = backtest_payload(self.runtime, self.catalog, request)
            payload.update(
                {
                    "automatic_requalification": True,
                    "origin_target_after": origin_floor.isoformat(),
                    "qualification_snapshot_id": watch.qualification_snapshot_id,
                    "snapshot_id": latest_snapshot.snapshot_id,
                    "question_links": eligible,
                    "priority": min(
                        ledger.get_question(link["question_id"]).priority
                        for link in eligible
                    ),
                    "execution_budget_seconds": 300,
                }
            )
            with ledger._transaction() as connection:
                job = self.queue.enqueue(request_key, payload, connection=connection)
                for link in eligible:
                    connection.execute(
                        """INSERT OR IGNORE INTO requalification_budgets
                        (question_id, watch_id, job_id, scheduled_at) VALUES (?, ?, ?, ?)""",
                        (
                            link["question_id"],
                            watch.watch_id,
                            job.job_id,
                            now.timestamp(),
                        ),
                    )
            ledger.advance_watch(
                watch.watch_id,
                {"kind": "requalification_scheduled", "new_origins": new_origins},
                now,
                event_id=f"requalification-scheduled/{job.job_id}",
            )
            for link in eligible:
                ledger.record_inbox_event(
                    question_id=link["question_id"],
                    revision=link["revision"],
                    event_kind="requalification_started",
                    transition_id=job.job_id,
                    watch_id=watch.watch_id,
                    summary="La riqualifica automatica è stata avviata con almeno 30 nuove origini finali indipendenti.",
                    payload={"new_final_origins": new_origins, "job_id": job.job_id},
                )

    def _record_requalification_failure(self, job: Job, now: datetime) -> None:
        watch_id = job.payload.get("watch_id")
        if not watch_id:
            return
        try:
            watch = self.runtime.ledger.get_watch(watch_id)
        except DomainError:
            return
        links = tuple(job.payload.get("question_links", ()))
        self._wait_for_requalification(
            watch,
            links,
            now,
            reason="automatic_requalification_failed",
            new_origins=max(30, watch.requalification_new_origins),
            due_at=now + timedelta(hours=24),
        )
        for link in links:
            self.runtime.ledger.record_inbox_event(
                question_id=link["question_id"],
                revision=link["revision"],
                event_kind="requalification_failed",
                transition_id=job.job_id,
                watch_id=watch_id,
                summary="La riqualifica automatica non è riuscita. La previsione resta provvisoria e potrà riprovare dopo il cooldown.",
                payload={"reason": "automatic_requalification_failed"},
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
            ):
                if len(watch.candidate.source_ids) == 1:
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
