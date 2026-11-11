"""Validated application boundary and registered source operations."""

from hashlib import sha256

from ..contracts import (
    CsvConfirmationResult,
    DomainError,
    SnapshotSeriesPage,
    SnapshotSummary,
    SourceProfile,
    SourceRefreshRequest,
    SourceRegistration,
    SourceSpec,
    SourceView,
)
from ..forecast_policy import provider_epoch_context
from ..jobs import JobQueue
from ..runtime import _digest
from ..sources.catalog import SourceCatalog
from ..sources.profiling import capture_confirmed_csv, inspect_source
from ..worker import Worker
from .service_discovery import DiscoveryOperations
from .service_jobs import JobOperations
from .service_jobs import validate_run as validate_run
from .service_questions import QuestionOperations
from .service_updates import UpdateOperations


class Observatory(
    DiscoveryOperations, QuestionOperations, UpdateOperations, JobOperations
):
    def __init__(self, ledger, runtime):
        if ledger.path.resolve() != runtime.ledger.path.resolve():
            raise DomainError("runtime_ledger_mismatch", {})
        self.ledger, self.runtime = ledger, runtime
        self.catalog = SourceCatalog(ledger.path)
        self.queue = JobQueue(ledger)
        self.worker = Worker(runtime, self.queue)

    def now(self):
        return max(self.runtime.clock(), self.ledger.clock())

    @staticmethod
    def source_view(revision):
        return SourceView(
            source_id=revision.spec.source_id,
            revision=revision.revision,
            kind=revision.spec.kind,
            refresh_seconds=revision.spec.refresh_seconds,
        )

    def profile(self, source_id):
        registered = self.catalog.get(source_id)
        profile = inspect_source(registered.spec)
        context = provider_epoch_context(self.runtime)
        epoch_id = _digest({"profile": profile.model_dump(mode="json"), **context})
        job = self.queue.enqueue(
            f"discover/templates/{epoch_id}",
            {
                "kind": "discovery_templates",
                **({"provider_context": context} if context else {}),
                "source_id": source_id,
                "revision": registered.revision,
                "epoch_id": epoch_id,
                "profile": profile.model_dump(mode="json"),
            },
        )
        return profile, epoch_id, job.job_id

    def register_source(self, spec: SourceSpec):
        registered = self.catalog.append(SourceSpec.model_validate(spec.model_dump()))
        profile, epoch_id, job_id = self.profile(spec.source_id)
        return SourceRegistration(
            **self.source_view(registered).model_dump(),
            profile=profile,
            epoch_id=epoch_id,
            job_id=job_id,
        )

    def confirm_csv_source(self, request):
        logical_key = f"guided-csv/{_digest({'key': request.key})}"
        job_id = sha256(logical_key.encode()).hexdigest()
        intent = _digest(request.model_dump(mode="json", exclude={"adapter_session"}))
        try:
            job = self.queue.get(job_id)
        except DomainError as error:
            if error.code != "not_found":
                raise
        else:
            original = self.queue.original_payload(job_id)
            if original.get("confirmation_intent") != intent:
                raise DomainError("idempotency_conflict", {})
            registered = self.catalog.get(original["source_id"], original["revision"])
            return CsvConfirmationResult(
                **self.source_view(registered).model_dump(),
                profile=SourceProfile.model_validate(original["profile"]),
                epoch_id=original["epoch_id"],
                job_id=job.job_id,
                replayed=True,
                session_grant=request.adapter_session is not None
                and request.adapter_session == original.get("adapter_session"),
            )
        profile, snap = capture_confirmed_csv(
            request.spec, request.proposal_version, request.as_of
        )
        context = provider_epoch_context(self.runtime)
        epoch_id = _digest(
            {
                "profile": profile.model_dump(mode="json"),
                "snapshot_id": snap.snapshot_id,
                **context,
            }
        )
        with self.ledger._transaction() as connection:
            # Check again under the shared write lock: another request may have
            # reserved this key while this one captured the file.
            try:
                current = self.queue.get(job_id)
            except DomainError as error:
                if error.code != "not_found":
                    raise
            else:
                original = self.queue.original_payload(job_id)
                if original.get("confirmation_intent") != intent:
                    raise DomainError("idempotency_conflict", {})
                registered = self.catalog.get(
                    original["source_id"], original["revision"]
                )
                return CsvConfirmationResult(
                    **self.source_view(registered).model_dump(),
                    profile=SourceProfile.model_validate(original["profile"]),
                    epoch_id=original["epoch_id"],
                    job_id=current.job_id,
                    replayed=True,
                    session_grant=request.adapter_session is not None
                    and request.adapter_session == original.get("adapter_session"),
                )
            registered = self.catalog.append(request.spec, connection=connection)
            job = self.queue.enqueue(
                logical_key,
                {
                    "kind": "discovery_templates",
                    **({"provider_context": context} if context else {}),
                    "source_id": request.spec.source_id,
                    "revision": registered.revision,
                    "epoch_id": epoch_id,
                    "profile": profile.model_dump(mode="json"),
                    "frozen_snapshot": snap.model_dump(mode="json"),
                    "confirmed_capture": True,
                    "confirmation_intent": intent,
                    "adapter_session": request.adapter_session,
                },
                connection=connection,
            )
        return CsvConfirmationResult(
            **self.source_view(registered).model_dump(),
            profile=profile,
            epoch_id=epoch_id,
            job_id=job.job_id,
            replayed=False,
        )

    def refresh_source(self, source_id: str, request: SourceRefreshRequest):
        request = SourceRefreshRequest.model_validate(request.model_dump())
        registered = self.catalog.get(source_id)
        epoch_id = _digest({"source_id": source_id, "refresh_key": request.key})
        key = f"refresh/templates/{epoch_id}"
        context = provider_epoch_context(self.runtime)
        new_epoch_id = (
            _digest({"legacy_request_epoch": epoch_id, **context})
            if context
            else epoch_id
        )
        job_id = sha256(key.encode()).hexdigest()
        try:
            job = self.queue.get(job_id)
        except DomainError as error:
            if error.code != "not_found":
                raise
            profile = inspect_source(registered.spec)
            try:
                job = self.queue.enqueue(
                    key,
                    {
                        "kind": "discovery_templates",
                        **({"provider_context": context} if context else {}),
                        "source_id": source_id,
                        "revision": registered.revision,
                        "epoch_id": new_epoch_id,
                        "profile": profile.model_dump(mode="json"),
                    },
                )
            except DomainError as conflict:
                if conflict.code != "idempotency_conflict":
                    raise
                job = self.queue.get(job_id)
        if job.payload["revision"] != registered.revision:
            raise DomainError("idempotency_conflict", {"key": key})
        profile = SourceProfile.model_validate(job.payload["profile"])
        return SourceRegistration(
            **self.source_view(registered).model_dump(),
            profile=profile,
            epoch_id=job.payload["epoch_id"],
            job_id=job.job_id,
        )

    def snapshot_summary(self, snapshot_id: str) -> SnapshotSummary:
        from ..presentations import summarize_snapshot

        return summarize_snapshot(self.ledger.get_snapshot(snapshot_id))

    def snapshot_series(
        self, snapshot_id: str, *, offset: int, limit: int
    ) -> SnapshotSeriesPage:
        from ..presentations import snapshot_series_page

        return snapshot_series_page(
            self.ledger.get_snapshot(snapshot_id), offset=offset, limit=limit
        )
