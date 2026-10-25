"""Narrow authenticated client for the optional Eve discovery bridge."""

from __future__ import annotations

import json
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from pydantic import Field, ValidationError

from ..contracts import Candidate, Contract, DomainError, Identifier, JsonValue

_MAX_RESPONSE_BYTES = 1_000_000


class AgentOperationRequest(Contract):
    job_id: Identifier
    epoch_id: Identifier
    session_id: Identifier
    call_key: Identifier
    tool: Literal["inspectSource", "proposeCandidates", "explainRun"]
    input: dict[str, JsonValue] = Field(default_factory=dict)


class AgentOperationResponse(Contract):
    operation_id: Identifier
    result: dict[str, JsonValue]


class AgentGateway:
    """Only start and poll durable sessions; no provider secret enters the core."""

    def __init__(
        self, base_url: str, *, token: str, timeout_seconds: float = 10
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            not isinstance(token, str)
            or not token.strip()
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme == "http"
                and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            )
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise DomainError("invalid_agent_gateway_config", {})
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def _request(self, path: str, payload: dict | None = None) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, separators=(",", ":")).encode()
            if payload is not None
            else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST" if payload is not None else "GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            code = (
                "agent_gateway_unauthorized"
                if error.code in {401, 403}
                else "agent_gateway_unavailable"
            )
            raise DomainError(code, {}) from None
        except (URLError, OSError, TimeoutError):
            raise DomainError("agent_gateway_unavailable", {}) from None
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise DomainError("invalid_agent_response", {})
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DomainError("invalid_agent_response", {}) from error
        if not isinstance(value, dict):
            raise DomainError("invalid_agent_response", {})
        return value

    def start(self, epoch_id: str, source_ids: tuple[str, ...], key: str) -> str:
        if not epoch_id or not source_ids or not key:
            raise DomainError("invalid_agent_request", {})
        response = self._request(
            "/forecast/discover",
            {"epochId": epoch_id, "sourceIds": list(source_ids), "idempotencyKey": key},
        )
        session_id = response.get("sessionId")
        if not isinstance(session_id, str) or not session_id.strip():
            raise DomainError("invalid_agent_response", {})
        return session_id

    def poll(self, session_id: str) -> tuple[Candidate, ...] | None:
        if not isinstance(session_id, str) or not session_id.strip():
            raise DomainError("invalid_agent_request", {})
        response = self._request(f"/forecast/discover/{quote(session_id, safe='')}")
        state = response.get("state")
        if state == "pending":
            return None
        if state == "failed":
            raise DomainError("agent_session_failed", {})
        if state != "completed" or not isinstance(response.get("candidates"), list):
            raise DomainError("invalid_agent_response", {})
        try:
            return tuple(Candidate.model_validate(c) for c in response["candidates"])
        except (ValidationError, TypeError, ValueError) as error:
            raise DomainError("invalid_agent_response", {}) from error
