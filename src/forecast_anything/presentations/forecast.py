"""Bounded forecast projections for time-series views."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, FiniteFloat

from ..contracts import (
    Contract,
    Identifier,
    ModelSelectionEvidence,
    RunRecord,
)


class ForecastProviderUse(Contract):
    node_id: Identifier
    requested_provider: Identifier | None
    actual_provider: Identifier | None


class ForecastPresentationPoint(Contract):
    node_id: Identifier
    series_id: Identifier
    timestamp: AwareDatetime
    unit: Identifier
    representation: Literal["point", "marginal_quantiles", "joint_paths"]
    point: FiniteFloat | None
    quantiles: Annotated[dict[str, FiniteFloat], Field(max_length=3)]
    quantiles_truncated: bool
    sample_count: Annotated[int, Field(ge=0, strict=True)]


class ForecastPresentation(Contract):
    schema_version: Literal["forecast-presentation-v1"] = "forecast-presentation-v1"
    visual_destination: Literal["time_series"] = "time_series"
    run_id: Identifier
    model_selection: ModelSelectionEvidence | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    primary_node_id: Identifier | None = None
    baseline_node_id: Identifier | None = None
    graph_id: Identifier
    graph_version: Annotated[int, Field(ge=1, strict=True)]
    as_of: AwareDatetime
    state: Identifier
    snapshot_ids: Annotated[tuple[Identifier, ...], Field(max_length=16)]
    snapshot_ids_truncated: bool
    providers: Annotated[tuple[ForecastProviderUse, ...], Field(max_length=16)]
    providers_truncated: bool
    points: Annotated[tuple[ForecastPresentationPoint, ...], Field(max_length=64)]
    total_point_count: Annotated[int, Field(ge=0, strict=True)]
    truncated: bool


def present_run(run: RunRecord) -> ForecastPresentation:
    points = []
    providers = [
        ForecastProviderUse(
            node_id=node_id,
            requested_provider=run.requested_provider.get(node_id),
            actual_provider=run.actual_provider.get(node_id),
        )
        for node_id in sorted(run.results)[:16]
    ]
    total_point_count = sum(
        len(result.series_ids) * len(result.timestamps)
        for result in run.results.values()
    )

    def make_point(node_id, result, series_index, time_index):
        representation = (
            "joint_paths"
            if result.paths is not None
            else "marginal_quantiles"
            if result.quantiles is not None
            else "point"
        )
        all_quantile_keys = tuple(sorted(result.quantiles or {}))
        quantile_keys = tuple(
            key for key in all_quantile_keys if len(key.encode("utf-8")) <= 32
        )[:3]
        quantiles_truncated = len(quantile_keys) < len(all_quantile_keys)
        return ForecastPresentationPoint(
            node_id=node_id,
            series_id=result.series_ids[series_index],
            timestamp=result.timestamps[time_index],
            unit=result.units[series_index],
            representation=representation,
            point=(
                result.point[series_index][time_index]
                if result.point is not None
                else None
            ),
            quantiles={
                key: result.quantiles[key][series_index][time_index]
                for key in quantile_keys
            },
            quantiles_truncated=quantiles_truncated,
            sample_count=len(result.paths or ()),
        )

    def node_points(node_id, result):
        for series_index in range(len(result.series_ids)):
            for time_index in range(len(result.timestamps)):
                yield make_point(node_id, result, series_index, time_index)

    selected = set()
    primary_id = run.primary_node_id or ("model" if "model" in run.results else None)
    baseline_id = (
        "baseline"
        if run.graph_id.startswith("configured-")
        and primary_id == "model"
        and primary_id in run.results
        and "baseline" in run.results
        and run.actual_provider.get("baseline") == "seasonal_naive"
        else None
    )
    baseline = run.results.get(baseline_id) if baseline_id else None
    if primary_id in run.results and baseline is not None:
        baseline_series = {
            (s, baseline.units[i]): i for i, s in enumerate(baseline.series_ids)
        }
        baseline_times = {
            timestamp: i for i, timestamp in enumerate(baseline.timestamps)
        }
        for point in node_points(primary_id, run.results[primary_id]):
            key = (point.series_id, point.timestamp, point.unit)
            series_index = baseline_series.get((point.series_id, point.unit))
            time_index = baseline_times.get(point.timestamp)
            if (
                series_index is not None
                and time_index is not None
                and len(points) <= 62
            ):
                comparison = make_point("baseline", baseline, series_index, time_index)
                points.extend((point, comparison))
                selected.update(((primary_id, *key), ("baseline", *key)))
            if len(points) >= 63:
                break
    order = sorted(
        run.results, key=lambda node: (node != primary_id, node != "baseline", node)
    )
    for node_id in order:
        for point in node_points(node_id, run.results[node_id]):
            key = (node_id, point.series_id, point.timestamp, point.unit)
            if key not in selected and len(points) < 64:
                points.append(point)
            if len(points) == 64:
                break
        if len(points) == 64:
            break
    snapshots = tuple(sorted(set(run.snapshot_ids)))
    all_provider_nodes = sorted(run.actual_provider)
    return ForecastPresentation(
        run_id=run.run_id,
        model_selection=run.model_selection,
        primary_node_id=primary_id,
        baseline_node_id=baseline_id,
        graph_id=run.graph_id,
        graph_version=run.graph_version,
        as_of=run.as_of,
        state=run.state,
        snapshot_ids=snapshots[:16],
        snapshot_ids_truncated=len(snapshots) > 16,
        providers=tuple(providers),
        providers_truncated=len(all_provider_nodes) > 16,
        points=tuple(points),
        total_point_count=total_point_count,
        truncated=total_point_count > len(points),
    )
