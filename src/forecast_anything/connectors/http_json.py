"""Bounded HTTP JSON GET adapter with injected, source-scoped credentials.

Only this adapter resolves secret_ref. Authenticated reads require HTTPS and use
Authorization: Bearer. Plain HTTP is restricted to loopback (test/local sources).
Redirects retain the exact origin or fail; no cross-origin credential forwarding.
JSON is decoded as data and never evaluated. records_path selects an explicitly
configured dotted object path to an array; omission requires a top-level array.
"""

from __future__ import annotations

import ipaddress
import json
import math
import re
from collections.abc import Callable
from http.client import HTTPException
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..contracts import DomainError, SourceSpec

SecretResolver = Callable[[str, str], str]
_MAX_BYTES = 5 * 1024 * 1024
_SENSITIVE = re.compile(
    r"authorization|password|passwd|secret|credential|api[_-]?key|token|cookie",
    re.IGNORECASE,
)


def sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE.search(key))


def sanitize_text(value: str, secrets: tuple[str, ...] = ()) -> str:
    """Conservatively redact known credentials and credential-shaped content."""
    if any(secret and secret in value for secret in secrets):
        return "[redacted]"
    if re.search(
        r"bearer\s+|authorization\s*[:=]|password\s*[:=]|api[_-]?key\s*[:=]|token\s*[:=]",
        value,
        re.I,
    ):
        return "[redacted]"
    if "://" in value:
        try:
            parts = urlsplit(value)
            if parts.username or any(
                sensitive_key(key) for key, _ in parse_qsl(parts.query)
            ):
                return "[redacted]"
        except ValueError:
            return "[redacted]"
    return value


def _reject_mapping_credentials(mapping: Any, secrets: tuple[str, ...]) -> None:
    """Check literals before discarding the adapter's credential context."""
    if isinstance(mapping, dict):
        for key, value in mapping.items():
            _reject_mapping_credentials(key, secrets)
            _reject_mapping_credentials(value, secrets)
    elif isinstance(mapping, (list, tuple)):
        for value in mapping:
            _reject_mapping_credentials(value, secrets)
    elif isinstance(mapping, str) and any(
        secret and secret in mapping for secret in secrets
    ):
        raise DomainError("invalid_source_mapping", {"reason": "credential_in_mapping"})


def sanitize_rows(
    rows: tuple[dict[str, Any], ...],
    secrets: tuple[str, ...] = (),
    *,
    mapping: dict[str, Any] | None = None,
    limit: int | None = None,
) -> tuple[dict[str, Any], ...]:
    """Discover credentials across all rows before limiting the emitted sample."""
    secrets = (
        *secrets,
        *(
            value
            for row in rows
            for key, value in row.items()
            if sensitive_key(key) and isinstance(value, str) and value
        ),
    )
    _reject_mapping_credentials(mapping, secrets)
    return tuple(
        {
            key: sanitize_text(value, secrets) if isinstance(value, str) else value
            for key, value in row.items()
            if not sensitive_key(key) and sanitize_text(key, secrets) == key
        }
        for row in (rows[:limit] if limit is not None else rows)
    )


def _origin(url: str) -> tuple[str, str | None, int | None]:
    parts = urlsplit(url)
    return (
        parts.scheme.lower(),
        parts.hostname,
        parts.port or (443 if parts.scheme == "https" else 80),
    )


class _OriginRedirect(HTTPRedirectHandler):
    def __init__(
        self, origin: tuple[str, str | None, int | None], secrets: tuple[str, ...] = ()
    ):
        self.origin = origin
        self.secrets = secrets

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        try:
            parts = urlsplit(target)
            unsafe = _origin(target) != self.origin or parts.username or parts.password
            unsafe = unsafe or any(secret in unquote(target) for secret in self.secrets)
            unsafe = unsafe or any(
                sensitive_key(key) for key, _ in parse_qsl(parts.query)
            )
        except ValueError:
            unsafe = True
        if unsafe:
            raise DomainError("source_unavailable", {"reason": "unsafe_redirect"})
        return super().redirect_request(req, fp, code, msg, headers, target)


def load_http_json(
    spec: SourceSpec,
    *,
    limit: int | None = None,
    secret_resolver: SecretResolver | None = None,
) -> tuple[dict[str, Any], ...]:
    try:
        parts = urlsplit(spec.location)
        origin = _origin(spec.location)
    except ValueError:
        raise DomainError(
            "source_unavailable", {"reason": "invalid_location"}
        ) from None
    if (
        parts.scheme not in {"https", "http"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise DomainError("source_unavailable", {"reason": "invalid_location"})
    if any(sensitive_key(key) for key, _ in parse_qsl(parts.query)):
        raise DomainError("source_unavailable", {"reason": "credentials_in_url"})
    if spec.secret_ref and parts.scheme != "https":
        raise DomainError("source_unavailable", {"reason": "insecure_credentials"})
    if parts.scheme == "http":
        try:
            loopback = ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            loopback = parts.hostname == "localhost"
        if not loopback:
            raise DomainError("source_unavailable", {"reason": "https_required"})
    headers = {"Accept": "application/json"}
    secrets = (spec.secret_ref,) if spec.secret_ref else ()
    if spec.secret_ref:
        if secret_resolver is None:
            raise DomainError(
                "source_unavailable", {"reason": "credentials_unavailable"}
            )
        try:
            credential = secret_resolver(spec.source_id, spec.secret_ref)
            if (
                not isinstance(credential, str)
                or not credential
                or "\r" in credential
                or "\n" in credential
            ):
                raise ValueError
        except Exception:
            raise DomainError(
                "source_unavailable", {"reason": "credentials_unavailable"}
            ) from None
        secrets = (*secrets, credential)
        headers["Authorization"] = f"Bearer {credential}"
    if any(secret in unquote(spec.location) for secret in secrets):
        raise DomainError("source_unavailable", {"reason": "credentials_in_url"})
    # No source-controlled credential may escape through mapping literals.
    _reject_mapping_credentials(spec.mapping, secrets)
    try:
        opener = build_opener(_OriginRedirect(origin, secrets))
        with opener.open(
            Request(spec.location, headers=headers, method="GET"), timeout=10
        ) as response:
            payload = response.read(_MAX_BYTES + 1)
        if len(payload) > _MAX_BYTES:
            raise DomainError("source_unavailable", {"reason": "response_too_large"})
        data = json.loads(payload)
    except HTTPError as error:
        raise DomainError("source_unavailable", {"status": error.code}) from None
    except (URLError, OSError, HTTPException, ValueError, UnicodeError):
        raise DomainError(
            "source_unavailable", {"reason": "http_read_failed"}
        ) from None
    path = spec.mapping.get("records_path", "")
    if not isinstance(path, str):
        raise DomainError("invalid_source_mapping", {"reason": "invalid_records_path"})
    try:
        for key in path.split(".") if path else ():
            data = data[key]
    except (KeyError, TypeError):
        raise DomainError(
            "invalid_source_data", {"reason": "records_path_missing"}
        ) from None
    if not isinstance(data, list) or any(
        not isinstance(row, dict)
        or any(
            not isinstance(key, str) or isinstance(value, (list, dict))
            for key, value in row.items()
        )
        for row in data
    ):
        raise DomainError("invalid_source_data", {"reason": "expected_scalar_records"})
    if any(
        isinstance(value, float) and not math.isfinite(value)
        for row in data
        for value in row.values()
    ):
        raise DomainError("invalid_source_data", {"reason": "nonfinite_number"})
    return sanitize_rows(
        tuple(data),
        secrets,
        mapping=spec.mapping,
        limit=limit,
    )
