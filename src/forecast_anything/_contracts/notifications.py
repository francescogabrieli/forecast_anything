"""Inbox events and webhook and source subscriptions."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from .common import Contract, Identifier, OpaqueDictionary


class InboxEvent(Contract):
    event_id: Identifier
    question_id: Identifier
    revision: Annotated[int, Field(ge=1, strict=True)]
    event_kind: Identifier
    transition_id: Identifier
    run_id: Identifier | None = Field(default=None, exclude_if=lambda v: v is None)
    decision_id: Identifier | None = Field(default=None, exclude_if=lambda v: v is None)
    watch_id: Identifier | None = Field(default=None, exclude_if=lambda v: v is None)
    occurred_at: AwareDatetime
    muted: bool = False
    summary: str
    payload: OpaqueDictionary
    delivery_states: tuple[
        Literal[
            "pending",
            "delivering",
            "delivered",
            "delivery_failed",
            "delivery_suppressed_muted",
        ],
        ...,
    ] = ()


class InboxPage(Contract):
    events: tuple[InboxEvent, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None = None
    total_count: Annotated[int, Field(ge=0, strict=True)]


class WebhookSubscription(Contract):
    subscription_id: Identifier
    target_url: str
    active: bool = True
    created_at: AwareDatetime


class WebhookSubscriptionRequest(Contract):
    target_url: str
    secret: str | None = None
    active: bool = True


class WebhookSubscriptionPatch(Contract):
    active: bool


class WebhookDelivery(Contract):
    delivery_id: Identifier
    subscription_id: Identifier
    event_id: Identifier
    state: Literal[
        "pending",
        "delivering",
        "delivered",
        "delivery_failed",
        "delivery_suppressed_muted",
    ]
    attempts: Annotated[int, Field(ge=0, strict=True)] = 0
    max_attempts: Annotated[int, Field(ge=1, strict=True)] = 3
    next_attempt_at: AwareDatetime
    last_error: str | None = Field(default=None, exclude_if=lambda v: v is None)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class SourceSubscription(Contract):
    source_id: Identifier
    active: bool = True
    created_at: AwareDatetime
    updated_at: AwareDatetime


class SourceSubscriptionRequest(Contract):
    active: bool = True


class SourceSubscriptionPage(Contract):
    subscriptions: tuple[SourceSubscription, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None = None


class WebhookSubscriptionPage(Contract):
    subscriptions: tuple[WebhookSubscription, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None = None


class WebhookDeliveryPage(Contract):
    deliveries: tuple[WebhookDelivery, ...]
    next_offset: Annotated[int, Field(ge=0, strict=True)] | None = None
