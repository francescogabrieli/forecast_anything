"""Schedule and bound automatic watch requalification."""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import Event, Timer

from .backtesting.planning import prepare_backtest
from .backtesting.service import _provider_contracts, backtest_payload
from .contracts import BacktestJobRequest, BacktestSettings, DomainError
from .discovery.policy import candidate_backtest_selection
from .jobs import Job
from .runtime import _digest


class RequalificationMixin:
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
                    "origin_target_after": origin_floor.isoformat()
                    if origin_floor is not None
                    else None,
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
