"""Shared graph and snapshot fixtures for runtime integration tests."""

from datetime import UTC, datetime, timedelta

from forecast_anything.contracts import (
    GraphSpec,
    Node,
    Observation,
)
from forecast_anything.temporal import freeze

T = datetime(2026, 10, 24, tzinfo=UTC)


def snapshot():
    return freeze(
        tuple(
            Observation(
                series_id="s",
                event_time=T - timedelta(hours=4 - i),
                available_at=T,
                revision="1",
                value=v,
                unit="count",
            )
            for i, v in enumerate((10, 20, 10, 20))
        ),
        T,
    )


def graph(provider="seasonal_naive", extra=()):
    return GraphSpec(
        graph_id="g",
        version=1,
        nodes=(
            Node(
                node_id="history",
                kind="source",
                inputs=(),
                config={
                    "source_id": "data",
                    "series_ids": ["s"],
                    "units": ["count"],
                    "frequency": "1h",
                },
            ),
            Node(
                node_id="prediction",
                kind="forecast",
                inputs=("history",),
                config={
                    "provider": provider,
                    "history": "history",
                    "horizon": 3,
                    "frequency": "1h",
                    "options": {"period": 2},
                    "relation_type": {"history": "statistical"},
                },
            ),
            *extra,
        ),
    )
