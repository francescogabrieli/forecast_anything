"""Shared validation, resource identities, and domain errors."""

from __future__ import annotations

from math import isfinite
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _require_finite_nested(value: Any) -> Any:
    """Validate opaque JSON-like data without changing its structure."""
    if isinstance(value, float) and not isfinite(value):
        raise ValueError("opaque dictionary numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            _require_finite_nested(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _require_finite_nested(item)
    return value


OpaqueDictionary = Annotated[dict[str, Any], AfterValidator(_require_finite_nested)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ResourceIdentity(Contract):
    kind: Literal["run", "question", "report"]
    resource_id: Identifier


class WorkspaceIdentity(Contract):
    workspace_id: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


class _ErrorPayload(Contract):
    code: Identifier
    details: OpaqueDictionary


class DomainError(Exception):
    """Structured domain failure; serializable through its validated payload."""

    def __init__(self, code: str, details: dict[str, Any]) -> None:
        self._payload = _ErrorPayload(code=code, details=details)
        self.code = self._payload.code
        self.details = self._payload.details
        super().__init__(self.code)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        return self._payload.model_dump(**kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        return self._payload.model_dump_json(**kwargs)


class ErrorResponse(Contract):
    code: Identifier
    details: OpaqueDictionary
