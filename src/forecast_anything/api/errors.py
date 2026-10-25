"""Safe HTTP diagnostics without submitted validation values or messages."""

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
