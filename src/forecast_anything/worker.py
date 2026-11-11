"""Single-worker execution with renewable leases and restart-safe emissions."""

from __future__ import annotations

import hmac
import json
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
from threading import Event, Thread
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

from ._worker_discovery import DiscoveryJobsMixin
from ._worker_requalification import RequalificationMixin
from ._worker_sources import SourceRefreshMixin
from ._worker_watches import WatchUpdatesMixin
from .backtesting.service import execute_job as execute_backtest_job
from .connectors.http_json import SecretResolver
from .contracts import (
    DomainError,
    EvaluationContext,
    GraphSpec,
    ModelSelectionEvidence,
    Snapshot,
)
from .evaluation.metrics import LEGACY_SCORING
from .evaluation.records import evaluate_run
from .forecast_policy import provider_epoch_context
from .jobs import Job, JobQueue
from .runtime import Runtime
from .sources.catalog import SourceCatalog


class _NoWebhookRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class Worker(
    DiscoveryJobsMixin, RequalificationMixin, SourceRefreshMixin, WatchUpdatesMixin
):
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
                model_selection=(
                    ModelSelectionEvidence.model_validate(payload["model_selection"])
                    if payload.get("model_selection") is not None
                    else None
                ),
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
                scoring_version=payload.get("scoring_version", LEGACY_SCORING),
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
