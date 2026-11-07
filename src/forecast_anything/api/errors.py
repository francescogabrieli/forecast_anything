"""Safe HTTP diagnostics without submitted validation values or messages."""

import re
from typing import Any


def public_error_details(value: Any) -> Any:
    """Preserve error structure while allowlisting Pydantic error metadata.

    DomainError payloads can wrap validation errors at any depth. Their input,
    context and message may contain credentials, so expose only location/type.
    """
    if isinstance(value, dict):
        if "loc" in value and "type" in value:
            return {"loc": list(value["loc"]), "type": value["type"]}
        return {key: public_error_details(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [public_error_details(item) for item in value]
    return value


def public_failure(value: Any) -> Any:
    """Expose stable failure codes, never arbitrary adapter diagnostics.

    Historical persisted failures are untrusted too. Allow only bounded codes
    and known structural metadata; a message-key denylist misses custom fields.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        return {"code": "execution_error", "details": {}}
    code = value.get("code")
    if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code):
        code = "execution_error"
    details = value.get("details")
    safe = {}
    if isinstance(details, dict):
        if isinstance(details.get("reason"), str) and details["reason"] in {
            "csv_read_failed",
            "unsafe_redirect",
            "insecure_credentials",
            "credentials_in_url",
        }:
            safe["reason"] = details["reason"]
        status = details.get("status")
        if type(status) is int and 100 <= status <= 599:
            safe["status"] = status
    return {"code": code, "details": safe}


def public_event(event):
    """Detach a safe public view without mutating immutable event diagnostics."""
    if event.kind != "run_failed":
        return event
    return event.model_copy(
        update={
            "payload": {
                **event.payload,
                "error": public_failure(event.payload.get("error")),
            }
        }
    )
