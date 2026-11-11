"""Watch lifecycle, source subscriptions, and notification delivery."""

from uuid import uuid4

from ..contracts import (
    DomainError,
    OpaqueDictionary,
    SourceSubscription,
    SourceSubscriptionPage,
    WatchHistoryEntry,
    WatchHistoryPage,
    WatchPatch,
    WatchRequest,
    WatchView,
    WebhookDeliveryPage,
    WebhookSubscription,
    WebhookSubscriptionPage,
    WebhookSubscriptionPatch,
    WebhookSubscriptionRequest,
)
from ..runtime import _digest
from ..watches import create_watch, summarize_watch_change
from .errors import public_event


class UpdateOperations:
    def watches(self):
        self.worker._sync_watches(self.now())
        return tuple(WatchView(**w.model_dump()) for w in self.ledger.list_watches())

    def watch(self, watch_id: str):
        return WatchView(**self.ledger.get_watch(watch_id).model_dump())

    def watch_history(self, watch_id: str, *, offset: int, limit: int):
        entries, next_offset = self.ledger.watch_history_page(
            watch_id, offset=offset, limit=limit
        )
        return WatchHistoryPage(
            entries=tuple(
                WatchHistoryEntry(
                    **{
                        **entry,
                        "watch": WatchView(**entry["watch"].model_dump()),
                    }
                )
                for entry in entries
            ),
            next_offset=next_offset,
        )

    def watch_change_summary(
        self, watch_id: str, previous_run_id: str, current_run_id: str
    ) -> OpaqueDictionary:
        result = summarize_watch_change(
            self.ledger.get_watch(watch_id),
            self.ledger.get_run(previous_run_id),
            self.ledger.get_run(current_run_id),
        )
        return OpaqueDictionary(result)

    def create_watch(self, request: WatchRequest):
        request = WatchRequest.model_validate(request.model_dump())
        candidate = self.ledger.get_candidate(request.candidate_id)
        from ..forecast_policy import validate_primary_provider

        validate_primary_provider(candidate.graph, self.runtime.required_provider)
        watch = create_watch(
            candidate,
            watch_id=_digest(request.model_dump(mode="json")),
            next_due_at=request.next_due_at,
        )
        try:
            self.ledger.get_watch(watch.watch_id)
        except DomainError as error:
            if error.code != "not_found":
                raise
            self.ledger.put_watch(watch, now=self.now())
        return next(w for w in self.watches() if w.watch_id == watch.watch_id)

    def patch_watch(self, watch_id, patch: WatchPatch):
        patch = WatchPatch.model_validate(patch.model_dump(exclude_unset=True))
        self.worker._sync_watches(self.now())
        current = self.ledger.get_watch(watch_id)
        for name in ("muted", "priority"):
            if name not in patch.model_fields_set:
                continue
            value = getattr(patch, name)
            if getattr(current, name) == value:
                continue
            current = self.ledger.advance_watch(
                watch_id,
                {
                    "kind": "muted" if name == "muted" else "priority_changed",
                    name: value,
                },
                self.now(),
                event_id=uuid4().hex,
            )
        return WatchView(**current.model_dump())

    def source_subscriptions(
        self, *, offset: int, limit: int
    ) -> SourceSubscriptionPage:
        return self.ledger.list_source_subscriptions(offset=offset, limit=limit)

    def set_source_subscription(
        self, source_id: str, *, active: bool
    ) -> SourceSubscription:
        self.catalog.get(source_id)
        subscription = self.ledger.set_source_subscription(source_id, active=active)
        for watch in self.ledger.list_watches():
            if source_id not in watch.candidate.source_ids:
                continue
            kind = (
                "source_subscription_activated"
                if active
                else "source_subscription_revoked"
            )
            transition_id = f"{kind}/{source_id}/{watch.watch_id}"
            self.ledger.advance_watch(
                watch.watch_id,
                {"kind": kind},
                self.now(),
                event_id=transition_id,
            )
            for link in self.worker._question_links_for_watch(watch.watch_id):
                self.ledger.record_inbox_event(
                    question_id=link["question_id"],
                    revision=link["revision"],
                    event_kind=kind,
                    transition_id=transition_id,
                    watch_id=watch.watch_id,
                    summary=(
                        "La sottoscrizione worker alla fonte è stata riattivata."
                        if active
                        else "La sottoscrizione worker alla fonte è stata revocata. I refresh e i run in coda verranno soppressi."
                    ),
                    payload={"source_id": source_id, "active": active},
                )
        if active:
            self.worker._schedule_sources(self.now())
        return subscription

    def create_webhook_subscription(
        self, request: WebhookSubscriptionRequest
    ) -> WebhookSubscription:
        return self.ledger.create_webhook_subscription(request)

    def webhook_subscriptions(
        self, *, offset: int, limit: int
    ) -> WebhookSubscriptionPage:
        return self.ledger.list_webhook_subscriptions(offset=offset, limit=limit)

    def patch_webhook_subscription(
        self, subscription_id: str, patch: WebhookSubscriptionPatch
    ) -> WebhookSubscription:
        return self.ledger.set_webhook_subscription_active(
            subscription_id, active=patch.active
        )

    def webhook_deliveries(
        self, subscription_id: str, *, offset: int, limit: int
    ) -> WebhookDeliveryPage:
        return self.ledger.list_webhook_deliveries(
            subscription_id, offset=offset, limit=limit
        )

    def inbox_events(self, *, question_id: str | None, offset: int, limit: int):
        return self.ledger.list_inbox_events(
            question_id=question_id, offset=offset, limit=limit
        )

    def events(self, after, limit=100):
        return tuple(
            public_event(event) for event in self.ledger.events_after(after, limit)
        )
