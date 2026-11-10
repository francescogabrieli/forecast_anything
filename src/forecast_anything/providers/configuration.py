"""Pinned product providers. Construction never loads model code or weights.

These immutable pins mirror integrations/models.lock.json and ship in the wheel.
The seasonal provider is retained for explicitly declared comparisons.
"""

import os

from ..contracts import DomainError
from .baseline import SeasonalNaiveProvider
from .timestral import TimestralProvider

TIMESTRAL_CHECKPOINT = "mistralai/Timestral-28M"
TIMESTRAL_REVISION = "49b26409ac87b5935539a5d8ffe7f397b720db47"
TIMESTRAL_CODE_REVISION = "a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff"
DEFAULT_TIMESTRAL_MODEL = "28m"
TIMESTRAL_MODEL_ENV = "FORECAST_ANYTHING_TIMESTRAL_MODEL"
TIMESTRAL_MODELS = {
    "28m": (TIMESTRAL_CHECKPOINT, TIMESTRAL_REVISION),
    "123m": ("mistralai/Timestral-123M", "5a147287addda85f6acd8da3fb8858fe9af7e8f7"),
}


def pinned_timestral_provider(
    model: str = DEFAULT_TIMESTRAL_MODEL,
) -> TimestralProvider:
    if model not in TIMESTRAL_MODELS:
        raise DomainError(
            "invalid_provider_configuration",
            {
                "variable": TIMESTRAL_MODEL_ENV,
                "supported_models": list(TIMESTRAL_MODELS),
            },
        )
    checkpoint, revision = TIMESTRAL_MODELS[model]
    prepare_command = "forecast-anything model prepare"
    if model != DEFAULT_TIMESTRAL_MODEL:
        prepare_command += f" --timestral-model {model}"
    return TimestralProvider(
        checkpoint, revision, TIMESTRAL_CODE_REVISION, prepare_command=prepare_command
    )


def configured_providers(model: str | None = None):
    """Register a supported checkpoint and reject conflicting legacy pins."""
    provider = pinned_timestral_provider(
        os.environ.get(TIMESTRAL_MODEL_ENV, DEFAULT_TIMESTRAL_MODEL)
        if model is None
        else model
    )
    expected = {
        "ENABLED": "1",
        "CHECKPOINT": provider.checkpoint,
        "REVISION": provider.revision,
        "CODE_REVISION": TIMESTRAL_CODE_REVISION,
    }
    for suffix, value in expected.items():
        name = f"FORECAST_ANYTHING_TIMESTRAL_{suffix}"
        if name in os.environ and os.environ[name].strip() != value:
            raise DomainError(
                "invalid_provider_configuration",
                {"variable": name, "expected": value, "required_provider": "timestral"},
            )
    return {
        "timestral": provider,
        "seasonal_naive": SeasonalNaiveProvider(1),
    }
