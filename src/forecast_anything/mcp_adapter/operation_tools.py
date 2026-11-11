"""Durable operation creation, submission, and recovery."""

from __future__ import annotations

from ..contracts import Contract, OperationPage, OperationView
from .arguments import (
    OperationCreateArguments,
    OperationIdArguments,
    OperationListArguments,
    OperationSubmitArguments,
    OperationUpdateArguments,
)
from .client import CoreRequestError, encode_identifier
from .config import McpConfigError
from .dispatch import ToolContext
from .protocol import Tool

TOOLS = (
    Tool(
        "create_operation",
        OperationCreateArguments,
        OperationView,
        "Create or replay a durable operation linked to a question revision.",
        mutating=True,
    ),
    Tool(
        "update_operation",
        OperationUpdateArguments,
        OperationView,
        "Update operation phase and missing-data fields with version checks and an idempotency key.",
        mutating=True,
    ),
    Tool(
        "list_operations",
        OperationListArguments,
        OperationPage,
        "Read a bounded page of compact durable operation state, optionally for one question.",
    ),
    Tool(
        "get_operation",
        OperationIdArguments,
        OperationView,
        "Read compact durable operation state and its job status without returning the full request or result.",
    ),
    Tool(
        "submit_operation",
        OperationSubmitArguments,
        OperationView,
        "Freeze a confirmed job request for a saved operation and reserve its durable job ID. Supply the operation version and exact request, then poll get_job. Reuse the same request after interruption.",
        mutating=True,
        open_world=True,
    ),
    Tool(
        "resume_operation",
        OperationIdArguments,
        OperationView,
        "Recover a saved operation after reconnect or interrupted enqueue. The stored request and job ID are reused. Source-reading jobs still require the applicable source grants. Poll get_job once the operation has a job ID.",
        mutating=True,
        open_world=True,
    ),
)


async def delegate(context: ToolContext, name: str, arguments: Contract):
    client, allowed = context.client, context.allowed
    if name == "create_operation":
        return await client.request(
            "POST", "/v1/operations", body=arguments.model_dump(mode="json")
        )
    if name == "update_operation":
        return await client.request(
            "PATCH",
            "/v1/operations/" + encode_identifier(arguments.operation_id),
            body=arguments.model_dump(mode="json", exclude={"operation_id"}),
        )
    if name == "list_operations":
        params = {"offset": arguments.offset, "limit": arguments.limit}
        if arguments.question_id is not None:
            params["question_id"] = arguments.question_id
        return await client.request("GET", "/v1/operations", params=params)
    if name == "get_operation":
        return await client.request(
            "GET", "/v1/operations/" + encode_identifier(arguments.operation_id)
        )
    if name == "submit_operation":
        if (
            arguments.request.kind == "backtest"
            and arguments.request.source_id not in allowed
        ):
            raise McpConfigError("source_forbidden")
        return await client.request(
            "POST",
            "/v1/operations/" + encode_identifier(arguments.operation_id) + "/submit",
            body=arguments.model_dump(mode="json", exclude={"operation_id"}),
        )
    if name == "resume_operation":
        operation_id = encode_identifier(arguments.operation_id)
        current = OperationView.model_validate(
            await client.request("GET", "/v1/operations/" + operation_id)
        )
        if current.request_kind == "backtest" and not set(current.source_ids).issubset(
            allowed
        ):
            raise McpConfigError("source_forbidden")
        return await client.request("POST", f"/v1/operations/{operation_id}/resume")
    raise CoreRequestError("unknown_tool")
