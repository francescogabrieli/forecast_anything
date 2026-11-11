"""Browser links and MCP presentation rendering."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote, urlsplit

from mcp import types

from ..contracts import Contract
from ..presentations import (
    BacktestPresentation,
    ForecastPresentation,
    QuestionPresentation,
)
from .arguments import BrowserLinkArguments
from .client import CoreClient, CoreRequestError, encode_identifier
from .config import McpConfigError
from .dispatch import ToolContext
from .protocol import Tool, tool_result


class BrowserLink(Contract):
    kind: Literal["run", "question", "report"]
    resource_id: str
    workspace_id: str
    url: str


class ContextViewResult(Contract):
    kind: Literal["run", "question", "report"]
    browser_link: BrowserLink
    presentation: (
        ForecastPresentation | QuestionPresentation | BacktestPresentation | None
    )
    unavailable_reason: Literal["result_too_large", "response_too_large"] | None = None


async def _get_browser_link(client: CoreClient, arguments: BrowserLinkArguments):
    try:
        base = urlsplit(arguments.browser_url)
        if (
            base.scheme not in {"http", "https"}
            or base.hostname not in {"localhost", "127.0.0.1", "::1"}
            or base.username is not None
            or base.password is not None
            or base.query
            or base.fragment
            or base.path not in {"", "/"}
            or (base.port is not None and not 1 <= base.port <= 65535)
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise McpConfigError("invalid_browser_url") from None
    resource_id = arguments.resource_id
    if resource_id in {".", ".."} or "/" in resource_id or "\\" in resource_id:
        raise McpConfigError("invalid_request")
    workspace = await client.request("GET", "/v1/workspace")
    workspace_id = workspace.get("workspace_id")
    if (
        not isinstance(workspace_id, str)
        or len(workspace_id) != 32
        or any(c not in "0123456789abcdef" for c in workspace_id)
    ):
        raise CoreRequestError("invalid_response")
    item = await client.request(
        "GET",
        f"/v1/resource-identities/{arguments.kind}/{encode_identifier(resource_id)}",
    )
    if item.get("kind") != arguments.kind or item.get("resource_id") != resource_id:
        raise CoreRequestError("invalid_response")
    root = arguments.browser_url.rstrip("/")
    return BrowserLink(
        kind=arguments.kind,
        resource_id=resource_id,
        workspace_id=workspace_id,
        url=f"{root}/#/w/{workspace_id}/{arguments.kind}/{quote(resource_id, safe='')}",
    )


def render_context_view(data: ContextViewResult, payload: dict) -> types.CallToolResult:
    presentation = data.presentation
    if presentation is None:
        text = f"Presentazione troppo grande per MCP. Apri il record nel browser: {data.browser_link.url}"
        return tool_result(payload, text)
    if data.kind == "run" and isinstance(presentation, ForecastPresentation):
        primary = next(
            (
                p
                for p in presentation.points
                if p.node_id == presentation.primary_node_id
            ),
            None,
        )
        answer = (
            f"Primo punto previsto: {primary.point} {primary.unit} per {primary.timestamp.isoformat()}"
            if primary and primary.point is not None
            else "Previsione puntuale non disponibile"
        )
        baseline = next(
            (
                p
                for p in presentation.points
                if primary
                and p.node_id == presentation.baseline_node_id
                and p.series_id == primary.series_id
                and p.timestamp == primary.timestamp
                and p.unit == primary.unit
            ),
            None,
        )
        comparator = (
            baseline.point
            if baseline and baseline.point is not None
            else "non disponibile o non confrontabile"
        )
        summary = f"{answer}; baseline {comparator}; stato {presentation.state}; origine {presentation.as_of.isoformat()}; {'risultati troncati' if presentation.truncated else 'punti disponibili non troncati'}."
    elif data.kind == "question" and isinstance(presentation, QuestionPresentation):
        question = presentation.question
        refs = (
            ", ".join(
                f"{item.reference.target_type} {item.reference.target_id}"
                for item in presentation.references
            )
            or "nessun riferimento"
        )
        summary = f"Domanda {question.title}: {question.revision.meaning}; orizzonte {question.revision.selection.horizon}; stato {question.status}; riferimenti: {refs}."
    elif data.kind == "report" and isinstance(presentation, BacktestPresentation):
        parts = "; ".join(
            f"{p.partition}: valutate {p.evaluated}, escluse {p.excluded}, MAE modello {p.model_mae}, baseline {p.baseline_mae}"
            for p in presentation.summary.partitions
        )
        summary = f"Confronto storico: {presentation.summary.status}; orizzonte {presentation.summary.selection.horizon}. {parts}. {presentation.summary.interpretation_limit}"
    else:
        raise CoreRequestError("invalid_response")
    text = f"{summary[:4000]} ID {data.browser_link.resource_id}. Apri nel browser: {data.browser_link.url}"
    rendered = tool_result(payload, text)
    if rendered.is_error:
        fallback = ContextViewResult(
            kind=data.kind,
            browser_link=data.browser_link,
            presentation=None,
            unavailable_reason="result_too_large",
        )
        return tool_result(
            {"ok": True, "data": fallback.model_dump(mode="json")},
            text
            + " La presentazione completa supera il limite MCP; aprila nel browser.",
        )
    return rendered


TOOLS = (
    Tool(
        "open_context_view",
        BrowserLinkArguments,
        ContextViewResult,
        "Open a saved run, question or report by its exact ID and operator-provided local browser origin. Return a text summary and credential-free browser fallback. Embedded rendering depends on host support.",
    ),
    Tool(
        "get_browser_link",
        BrowserLinkArguments,
        BrowserLink,
        "Create a credential-free local browser link for an existing question, run or backtest report in this workspace.",
    ),
)


async def delegate(context: ToolContext, name: str, arguments: Contract):
    client = context.client
    if name == "open_context_view":
        if len(arguments.resource_id) > 128 or len(arguments.browser_url) > 512:
            raise McpConfigError("invalid_request")
        link = await _get_browser_link(client, arguments)
        path = {"run": "runs", "question": "questions", "report": "reports"}[
            arguments.kind
        ]
        try:
            value = await client.request(
                "GET",
                f"/v1/{path}/{encode_identifier(arguments.resource_id)}/presentation",
            )
        except CoreRequestError as error:
            if error.code != "response_too_large":
                raise
            return ContextViewResult(
                kind=arguments.kind,
                browser_link=link,
                presentation=None,
                unavailable_reason="response_too_large",
            )
        model = {
            "run": ForecastPresentation,
            "question": QuestionPresentation,
            "report": BacktestPresentation,
        }[arguments.kind]
        presentation = model.model_validate(value)
        actual_id = (
            presentation.run_id
            if arguments.kind == "run"
            else presentation.question.question_id
            if arguments.kind == "question"
            else presentation.summary.report_id
        )
        if actual_id != arguments.resource_id:
            raise CoreRequestError("invalid_response")
        return ContextViewResult(
            kind=arguments.kind, browser_link=link, presentation=presentation
        )
    if name == "get_browser_link":
        return await _get_browser_link(client, arguments)
    raise CoreRequestError("unknown_tool")
