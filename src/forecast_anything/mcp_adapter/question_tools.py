"""Question history, references, and update delivery."""

from __future__ import annotations

from ..contracts import (
    Contract,
    InboxPage,
    QuestionPage,
    QuestionReference,
    QuestionReferencePage,
    QuestionRevision,
    QuestionRevisionPage,
    QuestionView,
    WebhookDeliveryPage,
    WebhookSubscription,
    WebhookSubscriptionPage,
    WebhookSubscriptionPatch,
    WebhookSubscriptionRequest,
)
from ..presentations import QuestionPresentation
from .arguments import (
    InboxListArguments,
    QuestionCreateArguments,
    QuestionIdArguments,
    QuestionListArguments,
    QuestionPatchArguments,
    QuestionPresentationArguments,
    QuestionReferenceLinkArguments,
    QuestionReferencePageArguments,
    QuestionReviseArguments,
    QuestionRevisionArguments,
    QuestionRevisionPageArguments,
    WebhookDeliveryListArguments,
    WebhookSubscriptionCreateArguments,
    WebhookSubscriptionListArguments,
    WebhookSubscriptionPatchArguments,
)
from .client import CoreRequestError, encode_identifier
from .dispatch import ToolContext
from .protocol import Tool

TOOLS = (
    Tool(
        "create_question",
        QuestionCreateArguments,
        QuestionView,
        "Create or replay a durable research question with its first semantic revision.",
        mutating=True,
    ),
    Tool(
        "list_questions",
        QuestionListArguments,
        QuestionPage,
        "Read a bounded, stable page of durable questions.",
    ),
    Tool(
        "list_inbox_events",
        InboxListArguments,
        InboxPage,
        "Read a bounded page of durable question updates, including mute and webhook delivery state.",
    ),
    Tool(
        "get_question",
        QuestionIdArguments,
        QuestionView,
        "Read a question's current semantic revision and compact reference counts.",
    ),
    Tool(
        "update_question",
        QuestionPatchArguments,
        QuestionView,
        "Update the question title, lifecycle, mute setting or priority without a semantic revision. Pause suppresses forecast work; mute suppresses notifications. Shared polling is controlled by set_source_subscription. Priority runs from 0 (highest) to 5 (lowest).",
        mutating=True,
    ),
    Tool(
        "revise_question",
        QuestionReviseArguments,
        QuestionView,
        "Append a semantic revision using expected_revision compare-and-swap and an idempotency key.",
        mutating=True,
    ),
    Tool(
        "list_question_revisions",
        QuestionRevisionPageArguments,
        QuestionRevisionPage,
        "Read a bounded page of immutable semantic question revisions.",
    ),
    Tool(
        "get_question_revision",
        QuestionRevisionArguments,
        QuestionRevision,
        "Read one immutable historical semantic question revision by number.",
    ),
    Tool(
        "link_question_reference",
        QuestionReferenceLinkArguments,
        QuestionReference,
        "Attach an existing candidate, run, backtest, watch, evaluation or operation to an exact saved question revision. Reuse the same key to replay the link.",
        mutating=True,
    ),
    Tool(
        "list_question_references",
        QuestionReferencePageArguments,
        QuestionReferencePage,
        "Read a bounded page of revision-bound references.",
    ),
    Tool(
        "get_question_presentation",
        QuestionPresentationArguments,
        QuestionPresentation,
        "Read a question with bounded references and explicit applicability to the current semantic revision.",
    ),
    Tool(
        "create_webhook_subscription",
        WebhookSubscriptionCreateArguments,
        WebhookSubscription,
        "Opt in to question update webhooks. The optional signing secret is write-only and is never returned by read tools.",
        mutating=True,
        open_world=True,
    ),
    Tool(
        "list_webhook_subscriptions",
        WebhookSubscriptionListArguments,
        WebhookSubscriptionPage,
        "Read a bounded page of webhook destinations and active status; signing secrets are never returned.",
    ),
    Tool(
        "update_webhook_subscription",
        WebhookSubscriptionPatchArguments,
        WebhookSubscription,
        "Enable or disable one webhook destination. This does not change inbox history.",
        mutating=True,
        open_world=True,
    ),
    Tool(
        "list_webhook_deliveries",
        WebhookDeliveryListArguments,
        WebhookDeliveryPage,
        "Read a bounded page of delivery attempts, retry times and final states for one webhook subscription.",
    ),
)


async def delegate(context: ToolContext, name: str, arguments: Contract):
    client = context.client
    if name == "create_question":
        return await client.request(
            "POST", "/v1/questions", body=arguments.model_dump(mode="json")
        )
    if name == "list_questions":
        return await client.request(
            "GET",
            "/v1/questions",
            params={"offset": arguments.offset, "limit": arguments.limit},
        )
    if name == "list_inbox_events":
        params = arguments.model_dump(mode="json", exclude_none=True)
        return await client.request("GET", "/v1/inbox", params=params)
    if name == "get_question":
        return await client.request(
            "GET", "/v1/questions/" + encode_identifier(arguments.question_id)
        )
    if name == "update_question":
        return await client.request(
            "PATCH",
            "/v1/questions/" + encode_identifier(arguments.question_id),
            body=arguments.model_dump(
                mode="json", exclude={"question_id"}, exclude_unset=True
            ),
        )
    if name == "revise_question":
        return await client.request(
            "POST",
            "/v1/questions/" + encode_identifier(arguments.question_id) + "/revisions",
            body=arguments.model_dump(mode="json", exclude={"question_id"}),
        )
    if name == "list_question_revisions":
        return await client.request(
            "GET",
            "/v1/questions/" + encode_identifier(arguments.question_id) + "/revisions",
            params={"offset": arguments.offset, "limit": arguments.limit},
        )
    if name == "get_question_revision":
        return await client.request(
            "GET",
            "/v1/questions/"
            + encode_identifier(arguments.question_id)
            + f"/revisions/{arguments.revision}",
        )
    if name == "link_question_reference":
        return await client.request(
            "POST",
            "/v1/questions/" + encode_identifier(arguments.question_id) + "/references",
            body=arguments.model_dump(mode="json", exclude={"question_id"}),
        )
    if name == "list_question_references":
        params = {"offset": arguments.offset, "limit": arguments.limit}
        if arguments.revision is not None:
            params["revision"] = arguments.revision
        return await client.request(
            "GET",
            "/v1/questions/" + encode_identifier(arguments.question_id) + "/references",
            params=params,
        )
    if name == "get_question_presentation":
        return await client.request(
            "GET",
            "/v1/questions/"
            + encode_identifier(arguments.question_id)
            + "/presentation",
            params={"offset": arguments.offset, "limit": arguments.limit},
        )
    if name == "create_webhook_subscription":
        request = WebhookSubscriptionRequest.model_validate(
            arguments.model_dump(mode="json")
        )
        return await client.request(
            "POST", "/v1/webhook-subscriptions", body=request.model_dump(mode="json")
        )
    if name == "list_webhook_subscriptions":
        return await client.request(
            "GET",
            "/v1/webhook-subscriptions",
            params=arguments.model_dump(mode="json"),
        )
    if name == "update_webhook_subscription":
        request = WebhookSubscriptionPatch(active=arguments.active)
        return await client.request(
            "PATCH",
            "/v1/webhook-subscriptions/" + encode_identifier(arguments.subscription_id),
            body=request.model_dump(mode="json"),
        )
    if name == "list_webhook_deliveries":
        return await client.request(
            "GET",
            "/v1/webhook-subscriptions/"
            + encode_identifier(arguments.subscription_id)
            + "/deliveries",
            params={"offset": arguments.offset, "limit": arguments.limit},
        )
    raise CoreRequestError("unknown_tool")
