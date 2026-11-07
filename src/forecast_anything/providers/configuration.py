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


def pinned_timestral_provider() -> TimestralProvider:
    return TimestralProvider(
        TIMESTRAL_CHECKPOINT, TIMESTRAL_REVISION, TIMESTRAL_CODE_REVISION
    )


def configured_providers():
    """Always register Timestral; reject obsolete disable or mismatched pins."""
    expected = {
        "ENABLED": "1",
        "CHECKPOINT": TIMESTRAL_CHECKPOINT,
        "REVISION": TIMESTRAL_REVISION,
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
        "timestral": pinned_timestral_provider(),
        "seasonal_naive": SeasonalNaiveProvider(1),
    }
