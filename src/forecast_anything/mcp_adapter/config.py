"""Operator-owned configuration and the local shared-filesystem boundary."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from ..contracts import SourceSpec

_LOOPBACK_ORIGIN = re.compile(r"https?://(?:127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?/?")


class McpConfigError(Exception):
    """A public code without private configuration values or source locations."""

    def __init__(self, code: str = "configuration_error"):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class McpConfig:
    api_url: str = "http://127.0.0.1:8000"
    workspace_token: str = field(default="", repr=False)
    csv_roots: tuple[Path, ...] = field(default=(), repr=False)
    source_ids: frozenset[str] = field(default_factory=frozenset, repr=False)

    def __post_init__(self):
        try:
            if not isinstance(self.api_url, str) or not _LOOPBACK_ORIGIN.fullmatch(
                self.api_url
            ):
                raise ValueError
            port = urlsplit(self.api_url).port
            if port is not None and not 1 <= port <= 65535:
                raise ValueError
            if (
                not isinstance(self.workspace_token, str)
                or not self.workspace_token
                or any(not 33 <= ord(char) <= 126 for char in self.workspace_token)
            ):
                raise ValueError
            roots = []
            for root in self.csv_roots:
                path = Path(root)
                if not path.is_absolute():
                    raise ValueError
                path = path.resolve(strict=True)
                if not path.is_dir():
                    raise ValueError
                roots.append(path)
            if any(
                not isinstance(item, str) or not item.strip()
                for item in self.source_ids
            ):
                raise ValueError
            object.__setattr__(self, "api_url", self.api_url.rstrip("/"))
            object.__setattr__(self, "csv_roots", tuple(roots))
            object.__setattr__(self, "source_ids", frozenset(self.source_ids))
        except (ValueError, TypeError, OSError):
            raise McpConfigError() from None

    @classmethod
    def from_env(cls) -> McpConfig:
        try:
            roots = json.loads(os.environ.get("FORECAST_ANYTHING_MCP_CSV_ROOTS", "[]"))
            ids = json.loads(os.environ.get("FORECAST_ANYTHING_MCP_SOURCE_IDS", "[]"))
            if not isinstance(roots, list) or not all(
                isinstance(root, str) for root in roots
            ):
                raise ValueError
            if not isinstance(ids, list) or not all(
                isinstance(item, str) for item in ids
            ):
                raise ValueError
            return cls(
                api_url=os.environ.get(
                    "FORECAST_ANYTHING_MCP_API_URL", "http://127.0.0.1:8000"
                ),
                workspace_token=os.environ.get("FORECAST_ANYTHING_WORKSPACE_TOKEN", ""),
                csv_roots=tuple(Path(root) for root in roots),
                source_ids=frozenset(ids),
            )
        except (ValueError, TypeError, OSError):
            raise McpConfigError() from None

    def validate_csv(self, spec: SourceSpec) -> SourceSpec:
        """Allow existing CSV files inside operator roots, after resolving symlinks.

        The API must share this filesystem namespace. This guard is a workspace
        policy, not protection against another process replacing files afterward.
        """
        try:
            if spec.kind != "csv" or spec.secret_ref is not None:
                raise ValueError
            path = Path(spec.location)
            if not path.is_absolute():
                raise ValueError
            resolved = path.resolve(strict=True)
            if not resolved.is_file() or not any(
                resolved.is_relative_to(root) for root in self.csv_roots
            ):
                raise ValueError
            return spec.model_copy(update={"location": str(resolved)})
        except (ValueError, TypeError, OSError):
            raise McpConfigError("source_forbidden") from None
