"""Generated properties for temporal selection and durable publication."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from forecast_anything.backtesting.planning import build_forecast_graph
from forecast_anything.contracts import DomainError, ForecastSelection, Observation
from forecast_anything.jobs import JobQueue
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze

ORIGIN = datetime(2026, 1, 1, tzinfo=UTC)
VALUES = st.lists(st.integers(-10_000, 10_000), min_size=2, max_size=12)


def history(values):
    return tuple(
        Observation(
            series_id="sales",
            event_time=ORIGIN + timedelta(hours=i + 1 - len(values)),
            available_at=ORIGIN + timedelta(hours=i + 1 - len(values)),
            revision="original",
            value=value,
            unit="count",
        )
        for i, value in enumerate(values)
    )


@given(
    values=VALUES,
    selected=st.integers(0, 30),
    delay=st.integers(1, 48),
    offset=st.integers(-12, 14),
)
@settings(max_examples=35, deadline=None)
def test_unavailable_data_cannot_change_an_issued_forecast(
    values, selected, delay, offset
):
    original = history(values)
    row = original[selected % len(values)]
    late = row.model_copy(
        update={
            "revision": "late",
            "available_at": ORIGIN + timedelta(hours=delay),
            "value": row.value + 100_000,
        }
    )
    future = late.model_copy(update={"event_time": late.available_at})
    cutoff = ORIGIN.astimezone(timezone(timedelta(hours=offset)))
    first = freeze(original, ORIGIN)
    replay = freeze(tuple(reversed((*original, late, future, row))), cutoff)
    assert replay == first
    assert all(row.available_at <= cutoff for row in replay.observations)

    selection = ForecastSelection(
        provider="seasonal_naive", horizon=2, baseline_period=2
    )
    graph = build_forecast_graph("sales", first, selection, "1h", graph_id="property")
    with TemporaryDirectory() as temp:
        ledger = Ledger(Path(temp) / "state.db")
        runtime = Runtime(
            ledger, {"seasonal_naive": SeasonalNaiveProvider(1)}, {}, lambda: ORIGIN
        )
        issued = runtime.run(graph, {"sales": first}, ORIGIN, "forecast")
        assert issued.state == "completed"
        before = ledger.events_after(0, 100)
        assert runtime.run(graph, {"sales": replay}, cutoff, "forecast") == issued
        assert ledger.events_after(0, 100) == before
        assert issued.results["baseline"].point == (tuple(values[-2:]),)


@given(values=VALUES, changed_index=st.integers(0, 30), delta=st.integers(1, 100))
@settings(max_examples=35, deadline=None)
def test_ledger_preserves_published_content_and_queue_replays(
    values, changed_index, delta
):
    observations = history(values)
    snapshot = freeze(observations, ORIGIN)
    index = changed_index % len(values)
    replacement = observations[index].model_copy(
        update={"value": values[index] + delta}
    )
    revised = freeze(
        (*observations[:index], replacement, *observations[index + 1 :]), ORIGIN
    )
    graph = build_forecast_graph(
        "sales",
        snapshot,
        ForecastSelection(provider="seasonal_naive", horizon=1),
        "1h",
        graph_id="property",
    )
    with TemporaryDirectory() as temp:
        ledger = Ledger(Path(temp) / "state.db")
        runtime = Runtime(
            ledger, {"seasonal_naive": SeasonalNaiveProvider(1)}, {}, lambda: ORIGIN
        )
        issued = runtime.run(graph, {"sales": snapshot}, ORIGIN, "forecast")
        events = ledger.events_after(0, 100)
        queue = JobQueue(ledger)
        payload = {"kind": "run", "snapshot_id": snapshot.snapshot_id}
        job = queue.enqueue("same-job", payload)
        assert queue.enqueue("same-job", dict(reversed(tuple(payload.items())))) == job
        with pytest.raises(DomainError, match="idempotency_conflict"):
            queue.enqueue("same-job", {**payload, "snapshot_id": revised.snapshot_id})
        with pytest.raises(DomainError, match="idempotency_conflict"):
            runtime.run(graph, {"sales": revised}, ORIGIN, "forecast")
        with pytest.raises(DomainError, match="immutable_identity"):
            ledger.put_snapshot(
                revised.model_copy(update={"snapshot_id": snapshot.snapshot_id})
            )

        reopened = Ledger(ledger.path)
        assert reopened.get_snapshot(snapshot.snapshot_id) == snapshot
        assert reopened.get_run(issued.run_id) == issued
        assert reopened.events_after(0, 100) == events
        assert JobQueue(reopened).get(job.job_id) == job
