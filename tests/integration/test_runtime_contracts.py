"""Runtime provider, operator, and calendar contracts."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from runtime_fixtures import T, graph, snapshot

from forecast_anything.contracts import (
    DomainError,
    Node,
    Observation,
    OperatorContract,
)
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze


class Scale:
    def contract(self):
        return OperatorContract(
            name="scale", required_representation="point", units_rule="same"
        )

    def apply(self, inputs, config):
        assert set(inputs) == {"inflow"}
        assert config == {"factor": 2}
        value = inputs["inflow"]
        return value.model_copy(
            update={
                "provider_id": "scale",
                "point": tuple(
                    tuple(v * config["factor"] for v in row) for row in value.point
                ),
            }
        )


def test_operator_roles_direct_parameters_and_original_provenance(tmp_path):
    node = Node(
        node_id="scaled",
        kind="transform",
        inputs=("prediction",),
        config={
            "operator": "scale",
            "relation_type": {"prediction": "physical"},
            "parameters": {"bindings": {"inflow": "prediction"}, "factor": 2},
        },
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    spec = graph(extra=(node,))
    original = spec.model_dump_json()
    run = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        {"scale": Scale()},
        lambda: T,
    ).run(spec, {"data": snapshot()}, T, "key")
    assert run.state == "completed"
    assert run.results["scaled"].point == ((20, 40, 20),)
    assert json.loads(ledger.get_graph("g", 1).model_dump_json()) == json.loads(
        original
    )
    event = next(
        e for e in ledger.events_after(0) if e.payload.get("node_id") == "scaled"
    )
    assert event.payload["dependencies"] == ["prediction"]
    assert event.payload["bindings"] == {"inflow": "prediction"}


@pytest.mark.parametrize(
    "bindings", [{}, {"left": "prediction", "right": "prediction"}]
)
def test_explicit_bindings_must_cover_inputs_exactly_once(tmp_path, bindings):
    node = Node(
        node_id="scaled",
        kind="transform",
        inputs=("prediction",),
        config={
            "operator": "scale",
            "relation_type": {"prediction": "physical"},
            "parameters": {"bindings": bindings},
        },
    )
    runtime = Runtime(
        Ledger(tmp_path / "ledger.sqlite"),
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        {"scale": Scale()},
        lambda: T,
    )
    with pytest.raises(DomainError, match="invalid_binding"):
        runtime.run(graph(extra=(node,)), {"data": snapshot()}, T, "key")


class KnownFutureProvider(SeasonalNaiveProvider):
    def capabilities(self):
        return super().capabilities().model_copy(update={"supports_known_future": True})

    def forecast(self, request):
        assert request.known_future is not None
        return super().forecast(request.model_copy(update={"known_future": None}))


@pytest.mark.parametrize("shift", [0, 1])
def test_known_future_requires_exact_forecast_calendar(tmp_path, shift):
    spec = graph()
    future = Node(
        node_id="calendar",
        kind="source",
        inputs=(),
        config={
            "source_id": "calendar_data",
            "series_ids": ["weekday"],
            "units": ["1"],
            "frequency": "1h",
        },
    )
    spec.nodes = (spec.nodes[0], future, spec.nodes[1])
    spec.nodes[2].inputs = ("history", "calendar")
    spec.nodes[2].config.update(
        known_future="calendar",
        relation_type={"history": "statistical", "calendar": "statistical"},
    )
    known = freeze(
        tuple(
            Observation(
                series_id="weekday",
                event_time=T + timedelta(hours=i + shift),
                available_at=T,
                revision="1",
                value=1,
                unit="1",
            )
            for i in range(3)
        ),
        T,
    )
    runtime = Runtime(
        Ledger(tmp_path / "ledger.sqlite"),
        {"seasonal_naive": KnownFutureProvider(2)},
        {},
        lambda: T,
    )
    if shift:
        with pytest.raises(DomainError, match="known_future_calendar_mismatch"):
            runtime.run(spec, {"data": snapshot(), "calendar_data": known}, T, "key")
    else:
        assert (
            runtime.run(
                spec, {"data": snapshot(), "calendar_data": known}, T, "key"
            ).state
            == "completed"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_id", "imposter"),
        ("provider_revision", "wrong"),
        ("units", ("wrong",)),
        ("series_ids", ("other",)),
        ("point", None),
    ],
)
def test_provider_cannot_falsify_compiled_contract(tmp_path, field, value):
    class Invalid(SeasonalNaiveProvider):
        def forecast(self, request):
            return super().forecast(request).model_copy(update={field: value})

    ledger = Ledger(tmp_path / "ledger.sqlite")
    run = Runtime(ledger, {"seasonal_naive": Invalid(2)}, {}, lambda: T).run(
        graph(), {"data": snapshot()}, T, "key"
    )
    assert run.state == "failed"
    assert run.actual_provider == {"prediction": "seasonal_naive"}
    assert run.results == {}
    assert ledger.events_after(0)[-1].kind == "run_failed"


def test_provider_local_dst_fold_outputs_are_normalized_for_operator_calendar(tmp_path):
    from zoneinfo import ZoneInfo

    origin = datetime(2026, 10, 25, tzinfo=UTC)
    data = freeze(
        tuple(
            Observation(
                series_id="s",
                event_time=origin - timedelta(hours=4 - i),
                available_at=origin,
                revision="1",
                value=v,
                unit="count",
            )
            for i, v in enumerate((10, 20, 10, 20))
        ),
        origin,
    )

    class LocalOutput(SeasonalNaiveProvider):
        def forecast(self, request):
            result = super().forecast(request)
            return result.model_copy(
                update={
                    "timestamps": tuple(
                        t.astimezone(ZoneInfo("Europe/Rome")) for t in result.timestamps
                    )
                }
            )

    class LocalScale(Scale):
        def apply(self, inputs, config):
            result = super().apply(inputs, config)
            return result.model_copy(
                update={
                    "timestamps": tuple(
                        t.astimezone(ZoneInfo("Europe/Rome")) for t in result.timestamps
                    )
                }
            )

    node = Node(
        node_id="scaled",
        kind="transform",
        inputs=("prediction",),
        config={
            "operator": "scale",
            "relation_type": {"prediction": "physical"},
            "parameters": {"bindings": {"inflow": "prediction"}, "factor": 2},
        },
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    run = Runtime(
        ledger,
        {"seasonal_naive": LocalOutput(2)},
        {"scale": LocalScale()},
        lambda: origin,
    ).run(graph(extra=(node,)), {"data": data}, origin, "fold")
    assert run.state == "completed"
    expected = (origin, origin + timedelta(hours=1), origin + timedelta(hours=2))
    assert run.results["prediction"].timestamps == expected
    assert run.results["scaled"].timestamps == expected
    assert run.results["scaled"].point == ((20, 40, 20),)
    assert ledger.get_run(run.run_id).results["scaled"].timestamps == expected
