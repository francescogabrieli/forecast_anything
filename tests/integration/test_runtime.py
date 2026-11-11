"""Runtime execution, retry, and durable errors."""

import json
from datetime import timedelta

import pytest
from runtime_fixtures import T, graph, snapshot

from forecast_anything.contracts import (
    Capabilities,
    DomainError,
    Observation,
)
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze


class ExplodingProvider:
    def capabilities(self):
        return Capabilities(
            provider_id="broken",
            provider_revision="rev7",
            representations=("point",),
            supports_known_future=False,
        )

    def forecast(self, request):
        raise RuntimeError("upstream service unavailable")


def test_retry_and_failed_provider(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(1), "broken": ExplodingProvider()},
        {},
        lambda: T,
    )
    first = runtime.run(graph(), {"data": snapshot()}, T, "key")
    original = first.model_dump_json()
    assert first.state == "completed"
    assert first.results["prediction"].point == ((10, 20, 10),)
    # Returning the durable record must not re-enter inference.
    runtime.providers["seasonal_naive"] = ExplodingProvider()
    assert runtime.run(graph(), {"data": snapshot()}, T, "key") == first
    assert len([e for e in ledger.events_after(0) if e.kind == "run_completed"]) == 1
    broken_graph = graph("broken").model_copy(update={"version": 2})
    failed = runtime.run(broken_graph, {"data": snapshot()}, T, "failure")
    assert failed.state == "failed"
    assert failed.requested_provider == {"prediction": "broken"}
    assert failed.actual_provider == {"prediction": "broken"}
    event = ledger.events_after(0)[-1]
    assert event.kind == "run_failed"
    assert "upstream service unavailable" in json.dumps(event.payload)
    assert "rev7" in json.dumps(event.payload)
    assert ledger.get_run(first.run_id).model_dump_json() == original
    assert runtime.run(broken_graph, {"data": snapshot()}, T, "failure") == failed


def test_retry_rejects_changed_content_even_under_same_snapshot_id(tmp_path):
    runtime = Runtime(
        Ledger(tmp_path / "ledger.sqlite"),
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        {},
        lambda: T,
    )
    runtime.run(graph(), {"data": snapshot()}, T, "key")
    altered = snapshot()
    altered.observations[0].value = 999
    with pytest.raises(DomainError, match="idempotency_conflict"):
        runtime.run(graph(), {"data": altered}, T, "key")


@pytest.mark.parametrize(
    "mutation", ["unit", "series", "available", "grid", "future", "as_of"]
)
def test_actual_source_metadata_rejected_before_inference(tmp_path, mutation):
    data = snapshot()
    if mutation == "unit":
        data.observations[0].unit = "wrong"
    if mutation == "series":
        data.observations[0].series_id = "other"
    if mutation == "available":
        data.observations[0].available_at = T + timedelta(hours=1)
    if mutation == "grid":
        data.observations[0].event_time += timedelta(minutes=1)
    if mutation == "future":
        data.observations[-1].event_time = T + timedelta(hours=1)
    if mutation == "as_of":
        data.as_of = T - timedelta(hours=1)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    runtime = Runtime(ledger, {"broken": ExplodingProvider()}, {}, lambda: T)
    with pytest.raises(DomainError):
        runtime.run(graph("broken"), {"data": data}, T, "key")
    assert ledger.get_run_by_key("key") is None


def test_invalid_graph_compiles_before_provider_call(tmp_path):
    spec = graph("broken")
    spec.nodes[1].config["relation_type"]["history"] = "candidate"
    runtime = Runtime(
        Ledger(tmp_path / "ledger.sqlite"),
        {"broken": ExplodingProvider()},
        {},
        lambda: T,
    )
    with pytest.raises(DomainError, match="candidate_relation"):
        runtime.run(spec, {"data": snapshot()}, T, "key")


class WrongOutput(SeasonalNaiveProvider):
    def forecast(self, request):
        result = super().forecast(request)
        result.timestamps = tuple(t + timedelta(hours=1) for t in result.timestamps)
        return result


def test_provider_output_checked_and_failed_durably(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    run = Runtime(ledger, {"seasonal_naive": WrongOutput(2)}, {}, lambda: T).run(
        graph(), {"data": snapshot()}, T, "key"
    )
    assert run.state == "failed"
    assert run.results == {}
    assert (
        ledger.events_after(0)[-1].payload["error"]["code"] == "invalid_provider_output"
    )


def test_second_emission_preserves_first_canonical_bytes(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    runtime = Runtime(
        ledger, {"seasonal_naive": SeasonalNaiveProvider(2)}, {}, lambda: T
    )
    first = runtime.run(graph(), {"data": snapshot()}, T, "first")
    original = ledger.get_run(first.run_id).model_dump_json()
    new_data = snapshot()
    observations = (
        *new_data.observations,
        Observation(
            series_id="s",
            event_time=T,
            available_at=T + timedelta(hours=1),
            revision="1",
            value=30,
            unit="count",
        ),
    )
    second = runtime.run(
        graph(),
        {"data": freeze(observations, T + timedelta(hours=1))},
        T + timedelta(hours=1),
        "second",
    )
    assert first.run_id != second.run_id
    assert second.results["prediction"].point == ((20, 30, 20),)
    assert ledger.get_run(first.run_id).model_dump_json() == original
