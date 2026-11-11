"""Source and webhook subscription routes."""

from typing import Annotated

from fastapi import Query

from ..contracts import (
    SourceSubscription,
    SourceSubscriptionPage,
    SourceSubscriptionRequest,
    WebhookDeliveryPage,
    WebhookSubscription,
    WebhookSubscriptionPage,
    WebhookSubscriptionPatch,
    WebhookSubscriptionRequest,
)


def register_subscriptions(api, service):
    @api.get("/source-subscriptions", response_model=SourceSubscriptionPage)
    def source_subscriptions(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.source_subscriptions(offset=offset, limit=limit)

    @api.put("/source-subscriptions/{source_id}", response_model=SourceSubscription)
    def set_source_subscription(source_id: str, request: SourceSubscriptionRequest):
        return service.set_source_subscription(source_id, active=request.active)

    @api.post(
        "/webhook-subscriptions",
        response_model=WebhookSubscription,
        status_code=201,
    )
    def create_webhook_subscription(request: WebhookSubscriptionRequest):
        return service.create_webhook_subscription(request)

    @api.get("/webhook-subscriptions", response_model=WebhookSubscriptionPage)
    def webhook_subscriptions(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.webhook_subscriptions(offset=offset, limit=limit)

    @api.patch(
        "/webhook-subscriptions/{subscription_id}",
        response_model=WebhookSubscription,
    )
    def patch_webhook_subscription(
        subscription_id: str, patch: WebhookSubscriptionPatch
    ):
        return service.patch_webhook_subscription(subscription_id, patch)

    @api.get(
        "/webhook-subscriptions/{subscription_id}/deliveries",
        response_model=WebhookDeliveryPage,
    )
    def webhook_deliveries(
        subscription_id: str,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ):
        return service.webhook_deliveries(subscription_id, offset=offset, limit=limit)
