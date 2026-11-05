"""Authenticated, bounded HTTP delegation to fixed local runtime routes."""

from __future__ import annotations

import asyncio
import json
import re
from math import isfinite
from urllib.parse import quote

import httpx

from .config import McpConfig

_MAX_BYTES = 1024 * 1024
_TIMEOUT_SECONDS = 15.0
_SEGMENT = r"(?!\.{1,2}(?:/|$))(?:[A-Za-z0-9_.~-]|%[0-9A-Fa-f]{2})+"
_ROUTES = {
    "GET": re.compile(
        rf"/v1/(?:capabilities|sources|events|"
        rf"(?:jobs|candidates|runs|snapshots|graphs|evaluations)/{_SEGMENT}|"
        rf"backtests/{_SEGMENT}(?:/origins)?|"
        rf"watches(?:/{_SEGMENT}(?:/(?:history|changes))?)?|"
        rf"sources/{_SEGMENT}/profile|runs/{_SEGMENT}/evaluations)"
    ),
    "POST": re.compile(rf"/v1/(?:sources|jobs|watches|sources/{_SEGMENT}/refresh)"),
    "PATCH": re.compile(rf"/v1/watches/{_SEGMENT}"),
}
_STATUS_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


class CoreRequestError(Exception):
    """Stable public failure code; upstream content is never retained."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def encode_identifier(value: str) -> str:
    """Encode exactly one identifier, including percent signs and dot segments."""
    if (
        not isinstance(value, str)
        or not value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise CoreRequestError("invalid_request")
    try:
        if value in {".", ".."}:
            return "%2E" * len(value)
        return quote(value, safe="")
    except (ValueError, UnicodeError):
        raise CoreRequestError("invalid_request") from None


def _serialize_body(body: dict | None) -> bytes | None:
    if body is None:
        return None
    if not isinstance(body, dict):
        raise CoreRequestError("invalid_request")
    encoded = bytearray()
    try:
        encoder = json.JSONEncoder(
            ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        for chunk in encoder.iterencode(body):
            part = chunk.encode("utf-8")
            if len(encoded) + len(part) > _MAX_BYTES:
                raise CoreRequestError("request_too_large")
            encoded.extend(part)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CoreRequestError("invalid_request") from None
    return bytes(encoded)


def _reject_nonfinite(value: str):
    raise ValueError


def _finite_float(value: str) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError
    return number


class CoreClient:
    """One attempt per request; accepted mutations use caller-owned replay keys."""

    def __init__(
        self, config: McpConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._client = httpx.AsyncClient(
            base_url=config.api_url,
            headers={
                "Authorization": f"Bearer {config.workspace_token}",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
            timeout=httpx.Timeout(_TIMEOUT_SECONDS),
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )

    async def __aenter__(self) -> CoreClient:
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self._client.__aexit__(exc_type, exc_value, traceback)

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        params: dict | None = None,
    ) -> dict | list:
        route = _ROUTES.get(method)
        if route is None or not isinstance(path, str) or not route.fullmatch(path):
            raise CoreRequestError("invalid_request")
        if params is not None and not isinstance(params, dict):
            raise CoreRequestError("invalid_request")
        content = _serialize_body(body)
        try:
            async with asyncio.timeout(_TIMEOUT_SECONDS):
                async with self._client.stream(
                    method,
                    path,
                    content=content,
                    headers={"Content-Type": "application/json"} if content else None,
                    params=params,
                ) as response:
                    if not 200 <= response.status_code < 300:
                        raise CoreRequestError(
                            _STATUS_CODES.get(response.status_code, "upstream_error")
                        )
                    # Refuse compression rather than allocate an unbounded decoded
                    # chunk before counting it. The local API serves identity JSON.
                    if (
                        response.headers.get("Content-Encoding", "identity")
                        != "identity"
                    ):
                        raise CoreRequestError("invalid_response")
                    length = response.headers.get("Content-Length")
                    if length is not None:
                        try:
                            size = int(length)
                        except ValueError:
                            raise CoreRequestError("invalid_response") from None
                        if size < 0:
                            raise CoreRequestError("invalid_response")
                        if size > _MAX_BYTES:
                            raise CoreRequestError("response_too_large")
                    payload = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        if len(payload) + len(chunk) > _MAX_BYTES:
                            raise CoreRequestError("response_too_large")
                        payload.extend(chunk)
        except (httpx.HTTPError, TimeoutError):
            raise CoreRequestError("network_error") from None
        try:
            result = json.loads(
                payload, parse_constant=_reject_nonfinite, parse_float=_finite_float
            )
        except (ValueError, UnicodeError, RecursionError):
            raise CoreRequestError("invalid_response") from None
        if not isinstance(result, (dict, list)):
            raise CoreRequestError("invalid_response")
        return result
