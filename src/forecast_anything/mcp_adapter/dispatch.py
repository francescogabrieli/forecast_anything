"""Connection state used when delegating MCP tools to the core API."""

from __future__ import annotations

from dataclasses import dataclass

from .client import CoreClient
from .config import McpConfig


@dataclass(frozen=True)
class ToolContext:
    client: CoreClient
    allowed: set[str]
    config: McpConfig
    adapter_session: str
