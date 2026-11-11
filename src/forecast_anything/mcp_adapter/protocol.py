"""MCP tool schemas and bounded protocol responses.

The combined result, including duplicated text and structured data, is 64 KiB.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeVar

from mcp import types
from pydantic import ConfigDict, ValidationError

from ..contracts import Contract

T = TypeVar("T")


class InputErrors(Contract):
    loc: list[str | int]
    type: str


class Envelope[T](Contract):
    model_config = ConfigDict(
        json_schema_extra={
            "oneOf": [
                {
                    "properties": {
                        "ok": {"const": True},
                        "data": {"not": {"type": "null"}},
                    },
                    "required": ["data"],
                    "not": {
                        "anyOf": [{"required": ["code"]}, {"required": ["errors"]}]
                    },
                },
                {
                    "properties": {
                        "ok": {"const": False},
                        "code": {"type": "string", "minLength": 1},
                    },
                    "required": ["code"],
                    "not": {"required": ["data"]},
                },
            ],
        }
    )
    ok: bool
    data: T | None = None
    code: str | None = None
    errors: list[InputErrors] | None = None


VIEW_URI = "ui://forecast-anything/context.html"
VIEW_MIME = "text/html;profile=mcp-app"
VIEW_META = {"ui": {"csp": {"connectDomains": [], "resourceDomains": []}}}


@dataclass(frozen=True)
class Tool:
    name: str
    arguments: type[Contract]
    result: Any
    description: str
    mutating: bool = False
    open_world: bool = False

    def schema(self) -> types.Tool:
        return types.Tool(
            name=self.name,
            description=self.description,
            input_schema=self.arguments.model_json_schema(),
            output_schema=Envelope[self.result].model_json_schema(mode="serialization"),
            annotations=types.ToolAnnotations(
                read_only_hint=not self.mutating,
                destructive_hint=self.mutating,
                # Only caller-keyed mutations have a replay guarantee; source
                # registration and profiling can advance discovery state.
                idempotent_hint=self.name
                not in {"register_csv_source", "get_source_profile"},
                open_world_hint=self.open_world,
            ),
            meta={"ui": {"resourceUri": VIEW_URI}, "ui/resourceUri": VIEW_URI}
            if self.name == "open_context_view"
            else None,
        )


def tool_result(value: dict, text_summary: str | None = None) -> types.CallToolResult:
    """Bound the entire protocol result, not just either duplicate payload."""
    result = types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text=text_summary
                or json.dumps(
                    value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                ),
            )
        ],
        structured_content=value,
        is_error=not value["ok"],
    )
    if len(result.model_dump_json(by_alias=True).encode("utf-8")) > 64 * 1024:
        return tool_result({"ok": False, "code": "result_too_large"})
    return result


def validation_errors(error: ValidationError, model: type[Contract]) -> list[dict]:
    # Extra fields and dictionary keys are submitted data too. Never render
    # arbitrary strings from a Pydantic location (including secret-like keys).
    fields: set[str] = set()

    def collect(schema):
        if isinstance(schema, dict):
            fields.update(schema.get("properties", {}))
            for child in schema.values():
                collect(child)
        elif isinstance(schema, list):
            for child in schema:
                collect(child)

    collect(model.model_json_schema())
    return [
        {
            "loc": [
                part if isinstance(part, int) or part in fields else "<field>"
                for part in item["loc"]
            ],
            "type": item["type"],
        }
        for item in error.errors(
            include_input=False, include_context=False, include_url=False
        )
    ]
