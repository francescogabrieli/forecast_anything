"""Shared forecast results, graphs, runs and actuals."""

from datetime import UTC, datetime, timedelta

from forecast_anything.contracts import (
    ForecastResult,
    GraphSpec,
    Node,
    Observation,
    RunRecord,
)
from forecast_anything.temporal import freeze

T = datetime(2026, 1, 1, tzinfo=UTC)


GRID = (T + timedelta(days=1), T + timedelta(days=2))


def result(values=(2, 4), provider="model", **changes):
    return ForecastResult.model_validate(
        dict(
            provider_id=provider,
            provider_revision="1",
            series_ids=("s",),
            timestamps=GRID,
            units=("count",),
            point=(values,),
            quantiles=None,
            paths=None,
            sample_group_id=None,
            assumptions=(),
        )
        | changes
    )


def graph(event=False):
    nodes = [
        Node(
            node_id="source",
            kind="source",
            inputs=(),
            config={
                "source_id": "source",
                "series_ids": ["s"],
                "units": ["count"],
                "frequency": "1d",
            },
        )
    ]
    for name, provider in (("model", "model"), ("baseline", "seasonal_naive")):
        nodes.append(
            Node(
                node_id=name,
                kind="forecast",
                inputs=("source",),
                config={
                    "provider": provider,
                    "history": "source",
                    "horizon": 2,
                    "frequency": "1d",
                    "relation_type": {"source": "statistical"},
                },
            )
        )
    if event:
        nodes.extend(
            (
                Node(
                    node_id="total",
                    kind="transform",
                    inputs=("model", "baseline"),
                    config={
                        "operator": "sum_aligned",
                        "relation_type": {
                            "model": "accounting",
                            "baseline": "accounting",
                        },
                    },
                ),
                Node(
                    node_id="event",
                    kind="event",
                    inputs=("total",),
                    config={
                        "operator": "any_exceed",
                        "relation_type": {"total": "statistical"},
                        "parameters": {
                            "bindings": {"value": "total"},
                            "threshold": 5,
                            "comparator": "gt",
                        },
                    },
                ),
            )
        )
    return GraphSpec(graph_id="g", version=1, nodes=tuple(nodes))


def run(values=(2, 4), baseline=(1, 3), **changes):
    return RunRecord.model_validate(
        dict(
            run_id="issued",
            graph_id="g",
            graph_version=1,
            as_of=T,
            snapshot_ids=("history",),
            requested_provider={"model": "model", "baseline": "seasonal_naive"},
            actual_provider={"model": "model", "baseline": "seasonal_naive"},
            state="completed",
            results={
                "model": result(values),
                "baseline": result(baseline, "seasonal_naive"),
            },
            evidence_ids=(),
            scenario_id=None,
            parent_run_id=None,
        )
        | changes
    )


def actuals(values=(2, 4), as_of=None, revision="1", available_at=None):
    return freeze(
        tuple(
            Observation(
                series_id="s",
                event_time=t,
                available_at=available_at or t,
                revision=revision,
                value=value,
                unit="count",
            )
            for t, value in zip(GRID, values, strict=False)
        ),
        as_of or GRID[-1],
    )
