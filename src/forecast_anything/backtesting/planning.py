"""Pure trusted graph construction and capture-time backtest planning."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

from ..contracts import (
    BacktestSettings,
    Capabilities,
    DomainError,
    ForecastSelection,
    GraphSpec,
    Node,
    Observation,
    Snapshot,
)
from ..evaluation.splits import build_splits
from ..providers.base import frequency_step, observation_grid
from ..sources.catalog import SourceRevision
from ..temporal import freeze
from .contracts import BacktestPlan, ObservationArchive, PlannedOrigin

PARTITIONS = ("exploration", "selection", "final")


def _observed(assumptions: tuple[str, ...]) -> None:
    if any(item.startswith("assumed:") for item in assumptions):
        raise DomainError("assumed_backtest_input", {})


def _metadata(observations: tuple[Observation, ...]) -> tuple[str, str]:
    metadata = {(row.series_id, row.unit) for row in observations}
    if len(metadata) != 1 or next(iter(metadata))[1].lower() in {"unknown", "?"}:
        raise DomainError("unsupported_source_metadata", {})
    return next(iter(metadata))


def build_forecast_graph(
    source_id: str,
    snapshot: Snapshot,
    selection: ForecastSelection,
    frequency: str,
    *,
    graph_id: str,
) -> GraphSpec:
    """Build one explicit selected model and one independent seasonal comparator."""
    snapshot = Snapshot.model_validate_json(snapshot.model_dump_json())
    selection = ForecastSelection.model_validate_json(selection.model_dump_json())
    _observed(snapshot.assumptions)
    series_id, unit = _metadata(snapshot.observations)
    observation_grid(snapshot, frequency)
    nodes = [
        Node(
            node_id="source",
            kind="source",
            inputs=(),
            config={
                "source_id": source_id,
                "series_ids": (series_id,),
                "units": (unit,),
                "frequency": frequency,
            },
        )
    ]
    model_options = deepcopy(selection.options)
    if selection.provider == "seasonal_naive":
        # Bind the protocol default, rather than an adapter instance's constructor.
        model_options.setdefault("period", 1)
    for node_id, provider, options in (
        ("baseline", "seasonal_naive", {"period": selection.baseline_period}),
        ("model", selection.provider, model_options),
    ):
        nodes.append(
            Node(
                node_id=node_id,
                kind="forecast",
                inputs=("source",),
                config={
                    "provider": provider,
                    "history": "source",
                    "known_future": None,
                    "horizon": selection.horizon,
                    "frequency": frequency,
                    "options": deepcopy(options),
                    "relation_type": {"source": "statistical"},
                },
            )
        )
    return GraphSpec(graph_id=graph_id, version=1, nodes=tuple(nodes))


def actuals_from_archive(archive: ObservationArchive) -> Snapshot:
    """Freeze only occurred observations from the captured same-source archive."""
    archive = ObservationArchive.model_validate_json(archive.model_dump_json())
    _observed(archive.assumptions)
    return freeze(
        tuple(
            row for row in archive.observations if row.event_time <= archive.captured_at
        ),
        archive.captured_at,
        (f"source_revision={archive.source_revision}", *archive.assumptions),
    )


def _source_frequency(source_revision: SourceRevision) -> tuple[str, timedelta]:
    """Resolve the declared fixed frequency without reading the source."""
    spec = source_revision.spec
    frequency = spec.mapping.get("frequency", {})
    if not isinstance(frequency, dict) or set(frequency) != {"constant"}:
        raise DomainError("unsupported_frequency", {})
    frequency = frequency["constant"]
    frequency = (
        {"D": "1d", "H": "1h"}.get(frequency, frequency)
        if isinstance(frequency, str)
        else ""
    )
    try:
        step = frequency_step(frequency)
    except (ValueError, OverflowError) as error:
        raise DomainError("unsupported_frequency", {}) from error
    return frequency, step


def prepare_backtest(
    backtest_id: str,
    source_revision: SourceRevision,
    observations: tuple[Observation, ...],
    selection: ForecastSelection,
    settings: BacktestSettings,
    captured_at: datetime,
    *,
    provider_contracts: dict[str, Capabilities],
    watch_id: str | None = None,
    candidate_id: str | None = None,
    origin_target_after: datetime | None = None,
) -> BacktestPlan:
    """Freeze source/configuration/calendar/membership without I/O or inference."""
    source_revision = SourceRevision.model_validate_json(
        source_revision.model_dump_json()
    )
    selection = ForecastSelection.model_validate_json(selection.model_dump_json())
    settings = BacktestSettings.model_validate_json(settings.model_dump_json())
    spec = source_revision.spec
    if spec.kind != "csv":
        raise DomainError("unsupported_backtest_source", {})
    _observed(source_revision.assumptions)
    frequency, step = _source_frequency(source_revision)
    # Compare integers before constructing timedelta: offsets can be arbitrarily large.
    if settings.origin_offset_seconds >= step // timedelta(seconds=1):
        raise DomainError("invalid_origin_offset", {})
    offset = timedelta(seconds=settings.origin_offset_seconds)
    archive = ObservationArchive(
        source_id=spec.source_id,
        source_revision=source_revision.revision,
        captured_at=captured_at,
        observations=observations,
        assumptions=source_revision.assumptions,
    )
    eligible = tuple(
        row
        for row in archive.observations
        if row.event_time <= archive.captured_at
        and row.available_at <= archive.captured_at
    )
    _metadata(eligible)
    timestamps = sorted({row.event_time for row in eligible})
    start, end = timestamps[0], timestamps[-1]
    if any((timestamp - start) % step for timestamp in timestamps):
        raise DomainError("off_grid_observation", {})
    cardinality = (end - start) // step + 1
    if cardinality > 100000:
        raise DomainError("backtest_calendar_limit", {"max_instants": 100000})
    calendar = tuple(start + step * index for index in range(cardinality))
    actuals = actuals_from_archive(archive)
    origins = []
    if len(calendar) >= 4:
        splits = build_splits(calendar, selection.horizon)
        positions = {timestamp: index for index, timestamp in enumerate(calendar)}
        for partition in PARTITIONS:
            members = splits.origins_for(partition, calendar)
            if partition == "final" and origin_target_after is not None:
                members = tuple(
                    nominal
                    for nominal in members
                    if calendar[positions[nominal] + 1] > origin_target_after
                )
            for nominal in members[: settings.max_origins_per_partition]:
                index = positions[nominal]
                origins.append(
                    PlannedOrigin(
                        ordinal=len(origins),
                        partition=partition,
                        nominal_origin=nominal,
                        issuance_time=nominal + offset,
                        target_start=calendar[index + 1],
                        target_end=calendar[index + selection.horizon],
                    )
                )
    if origin_target_after is not None:
        if (
            origin_target_after.tzinfo is None
            or origin_target_after.utcoffset() is None
        ):
            raise DomainError("invalid_origin_target_floor", {})
        origins = [
            origin.model_copy(update={"ordinal": index})
            for index, origin in enumerate(origins)
        ]
    plan = BacktestPlan(
        backtest_id=backtest_id,
        watch_id=watch_id,
        candidate_id=candidate_id,
        archive=archive,
        selection=selection,
        settings=settings,
        origin_target_after=origin_target_after,
        provider_contracts=provider_contracts,
        frequency=frequency,
        calendar=calendar,
        origins=tuple(origins),
        actuals_snapshot_id=actuals.snapshot_id,
        assumptions=(
            "Only supplied revisions are replayed; upstream-discarded vintages cannot be reconstructed.",
            "Frozen 50/25/25 partitions; earliest bounded origins; no tuning or imputation.",
            *(
                (
                    "Requalification final targets occur strictly after the prior qualification snapshot floor.",
                )
                if origin_target_after is not None
                else ()
            ),
            *(
                (
                    "backtest-v1 selected seasonal_naive default period=1; comparator uses baseline_period.",
                )
                if selection.provider == "seasonal_naive"
                and "period" not in selection.options
                else ()
            ),
            *archive.assumptions,
        ),
    )
    # Pydantic nested instances/dicts may alias callers; JSON is the freeze boundary.
    return BacktestPlan.model_validate_json(plan.model_dump_json())
