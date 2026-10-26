"""Experimental empirical paths from complete historical forecast-error worlds.

The caller owns source provenance and frozen split selection. Optional provider
and target-grid metadata, when supplied, are checked rather than inferred.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import isfinite
from random import Random

from ..contracts import DomainError, ForecastResult


@dataclass(frozen=True)
class ResidualPanel:
    origin: datetime
    horizon: int
    series_ids: tuple[str, ...]
    errors: list[list[float]]
    available_at: datetime
    provider_id: str | None = None
    provider_revision: str | None = None
    target_timestamps: tuple[datetime, ...] | None = None


def _utc(value, field):
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise DomainError("naive_timestamp", {"field": field})
    return value.astimezone(timezone.utc)


def _digest(value):
    return sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class ResidualPanelSampler:
    """Resample one shared origin per draw, never separate series or cells.

    A regular future UTC grid is required. Without explicit historical targets,
    the same grid step is assumed and maturity is checked against its endpoint.
    No statistical sufficiency or stationarity is implied by nonempty support.
    """

    def sample(
        self,
        base: ForecastResult,
        panels: tuple[ResidualPanel, ...],
        as_of: datetime,
        draws: int,
        seed: int,
    ) -> ForecastResult:
        as_of = _utc(as_of, "as_of")
        if type(draws) is not int or draws <= 0 or type(seed) is not int:
            raise DomainError(
                "invalid_sampling_request",
                {"reason": "integer seed and positive draws required"},
            )
        if not panels:
            raise DomainError(
                "insufficient_joint_support",
                {"available_panels": 0, "as_of": as_of.isoformat()},
            )
        base = ForecastResult.model_validate(base.model_dump())
        targets = tuple(_utc(t, "timestamps") for t in base.timestamps)
        if (
            base.point is None
            or not targets
            or not base.series_ids
            or len(set(base.series_ids)) != len(base.series_ids)
        ):
            raise DomainError(
                "invalid_sampling_request",
                {"reason": "point forecast and unique series required"},
            )
        step = targets[0] - as_of
        if step.total_seconds() <= 0 or any(
            t != as_of + step * (i + 1) for i, t in enumerate(targets)
        ):
            raise DomainError(
                "invalid_sampling_request",
                {"reason": "regular future UTC grid required"},
            )
        eligible, origins = [], set()
        for panel in panels:
            try:
                origin = _utc(panel.origin, "panel.origin")
                available = _utc(panel.available_at, "panel.available_at")
                expected = tuple(origin + step * (i + 1) for i in range(len(targets)))
                grid = (
                    tuple(_utc(t, "panel.targets") for t in panel.target_timestamps)
                    if panel.target_timestamps is not None
                    else expected
                )
                if (
                    type(panel.horizon) is not int
                    or panel.horizon != len(targets)
                    or panel.series_ids != base.series_ids
                    or len(panel.errors) != len(base.series_ids)
                    or any(len(row) != len(targets) for row in panel.errors)
                    or any(
                        isinstance(x, bool) or not isfinite(x)
                        for row in panel.errors
                        for x in row
                    )
                    or (as_of - origin) % step != timedelta(0)
                    or grid != expected
                    or available < expected[-1]
                    or origin in origins
                    or (panel.provider_id is None) != (panel.provider_revision is None)
                    or (
                        panel.provider_id is not None
                        and (panel.provider_id, panel.provider_revision)
                        != (base.provider_id, base.provider_revision)
                    )
                ):
                    raise ValueError(
                        "incomplete, unaligned, duplicate, or mismatched provider support"
                    )
            except (DomainError, ValueError, TypeError, AttributeError) as error:
                raise DomainError(
                    "invalid_residual_panel", {"reason": str(error)}
                ) from error
            origins.add(origin)
            if available <= as_of:
                eligible.append(
                    {
                        "origin": origin.isoformat(),
                        "available_at": available.isoformat(),
                        "errors": [[float(x) for x in row] for row in panel.errors],
                    }
                )
        if not eligible:
            raise DomainError(
                "insufficient_joint_support",
                {"available_panels": 0, "as_of": as_of.isoformat()},
            )
        eligible.sort(key=lambda p: p["origin"])
        rng = Random(seed)
        indices = [rng.randrange(len(eligible)) for _ in range(draws)]
        paths = tuple(
            tuple(
                tuple(p + e for p, e in zip(point, errors, strict=True))
                for point, errors in zip(
                    base.point, eligible[index]["errors"], strict=True
                )
            )
            for index in indices
        )
        support_id = _digest(eligible)
        identity = _digest(
            {
                "method": "residual_panel_sampler@1",
                "base": base.model_dump(mode="json"),
                "support": support_id,
                "as_of": as_of.isoformat(),
                "seed": seed,
                "draws": draws,
            }
        )
        return ForecastResult(
            provider_id="residual_panel_sampler",
            provider_revision="1",
            series_ids=base.series_ids,
            timestamps=targets,
            units=base.units,
            point=base.point,
            quantiles=None,
            paths=paths,
            sample_group_id=identity,
            assumptions=base.assumptions
            + (
                "status=experimental; evidence=provisional",
                f"base_provider={base.provider_id}@{base.provider_revision}",
                "assumption=residual transferability across origins; shared-origin series/horizon dependence preserved",
                f"support={support_id}; available_panels={len(eligible)}; excluded_unmatured={len(panels) - len(eligible)}",
                f"seed={seed}; draws={draws}; draw_origin_indices_sha256={_digest(indices)}",
            ),
        )
