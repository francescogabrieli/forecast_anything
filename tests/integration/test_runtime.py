import json
from datetime import datetime, timedelta, timezone

import pytest

from forecast_anything.contracts import (
    Capabilities,
    DomainError,
    GraphSpec,
    Node,
    Observation,
    OperatorContract,
)
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze

T = datetime(2026, 10, 24, tzinfo=timezone.utc)


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


@pytest.mark.parametrize("representation", ["joint_paths", "paths"])
@pytest.mark.parametrize("requirement", ["joint_paths", "paths"])
@pytest.mark.parametrize("mismatch", ["group", "samples", "none"])
def test_joint_paths_require_same_group_and_sample_count(
    tmp_path, mismatch, representation, requirement
):
    class Paths(SeasonalNaiveProvider):
        def capabilities(self):
            return (
                super()
                .capabilities()
                .model_copy(update={"representations": ("point", representation)})
            )

        def forecast(self, request):
            result = super().forecast(
                request.model_copy(update={"options": {"period": 2}})
            )
            second = request.options.get("second")
            count = 3 if second and mismatch == "samples" else 2
            group = "other" if second and mismatch == "group" else "joint"
            return result.model_copy(
                update={"paths": (result.point,) * count, "sample_group_id": group}
            )

    class Combine:
        def contract(self):
            return OperatorContract(
                name="combine", required_representation=requirement, units_rule="same"
            )

        def apply(self, inputs, config):
            left, right = inputs["left"], inputs["right"]
            return left.model_copy(
                update={
                    "paths": tuple(
                        tuple(
                            tuple(a + b for a, b in zip(ar, br))
                            for ar, br in zip(ap, bp)
                        )
                        for ap, bp in zip(left.paths, right.paths)
                    )
                }
            )

    spec = graph()
    second = spec.nodes[1].model_copy(deep=True)
    second.node_id = "second"
    second.config["options"] = {"second": True}
    combined = Node(
        node_id="combined",
        kind="transform",
        inputs=("prediction", "second"),
        config={
            "operator": "combine",
            "relation_type": {"prediction": "accounting", "second": "accounting"},
            "parameters": {"bindings": {"left": "prediction", "right": "second"}},
        },
    )
    spec.nodes = (*spec.nodes, second, combined)
    ledger = Ledger(tmp_path / "ledger.sqlite")
    run = Runtime(
        ledger, {"seasonal_naive": Paths(2)}, {"combine": Combine()}, lambda: T
    ).run(spec, {"data": snapshot()}, T, "key")
    if mismatch == "none":
        assert run.state == "completed"
        assert run.results["combined"].paths == (((20, 40, 20),), ((20, 40, 20),))
    else:
        assert run.state == "failed"
        assert set(run.results) == {"prediction", "second"}
        assert (
            ledger.events_after(0)[-1].payload["error"]["code"]
            == "incompatible_samples"
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


def test_provider_local_dst_fold_outputs_are_normalized_for_operator_calendar(tmp_path):
    from zoneinfo import ZoneInfo

    origin = datetime(2026, 10, 25, tzinfo=timezone.utc)
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


@pytest.mark.parametrize("representation", ["marginal_quantiles", "quantiles"])
def test_marginal_quantiles_run_without_claiming_joint_paths(tmp_path, representation):
    class Quantiles(SeasonalNaiveProvider):
        def capabilities(self):
            return (
                super()
                .capabilities()
                .model_copy(update={"representations": (representation,)})
            )

        def forecast(self, request):
            result = super().forecast(request)
            return result.model_copy(
                update={"point": None, "quantiles": {"0.5": result.point}}
            )

    ledger = Ledger(tmp_path / "ledger.sqlite")
    runtime = Runtime(ledger, {"seasonal_naive": Quantiles(2)}, {}, lambda: T)
    run = runtime.run(graph(), {"data": snapshot()}, T, "quantiles")
    assert run.state == "completed"
    assert run.results["prediction"].quantiles == {"0.5": ((10, 20, 10),)}
    assert run.results["prediction"].paths is None

    class NeedsPaths:
        def contract(self):
            return OperatorContract(
                name="paths", required_representation="joint_paths", units_rule="same"
            )

        def apply(self, inputs, config):
            raise AssertionError("quantiles must not satisfy joint paths")

    runtime.operators["paths"] = NeedsPaths()
    node = Node(
        node_id="joint",
        kind="transform",
        inputs=("prediction",),
        config={"operator": "paths", "relation_type": {"prediction": "statistical"}},
    )
    with pytest.raises(DomainError, match="unsupported_representation"):
        runtime.run(graph(extra=(node,)), {"data": snapshot()}, T, "joint")
    assert ledger.get_run_by_key("joint") is None


@pytest.mark.parametrize(
    "representations", [("point", "joint_paths"), ("joint_paths",)]
)
@pytest.mark.parametrize(
    "fault",
    [None, "group", "count", "calendar", "shape", "dropped_paths", "event_window"],
)
def test_builtin_transform_event_runtime_contract(tmp_path, representations, fault):
    from forecast_anything.operators import register_builtin_operators

    class Fixture(SeasonalNaiveProvider):
        def capabilities(self):
            return (
                super()
                .capabilities()
                .model_copy(update={"representations": representations})
            )

        def forecast(self, request):
            answer = super().forecast(request)
            return answer.model_copy(
                update={
                    "point": answer.point if "point" in representations else None,
                    "paths": (((2, 0, 0),), ((0, 2, 0),)),
                    "sample_group_id": "world",
                }
            )

    operators = register_builtin_operators()
    delegate = operators["any_exceed" if fault == "event_window" else "sum_aligned"]

    class Corrupt:
        def contract(self):
            return delegate.contract()

        def apply(self, inputs, config):
            answer = delegate.apply(inputs, config)
            changes = (
                {
                    "group": {"sample_group_id": "other"},
                    "count": {"paths": answer.paths[:1]},
                    "calendar": {
                        "timestamps": tuple(
                            t + timedelta(hours=1) for t in answer.timestamps
                        )
                    },
                    "shape": {"paths": (((1,),),)},
                    "dropped_paths": {"paths": None, "sample_group_id": None},
                    "event_window": {"timestamps": (T + timedelta(hours=5),)},
                }
                if fault != "event_window"
                else {"event_window": {"timestamps": (T + timedelta(hours=5),)}}
            )
            return answer.model_copy(update=changes[fault]) if fault else answer

    operators[delegate.contract().name] = Corrupt()
    extra = (
        Node(
            node_id="sum",
            kind="transform",
            inputs=("prediction",),
            config={
                "operator": "sum_aligned",
                "relation_type": {"prediction": "accounting"},
            },
        ),
        Node(
            node_id="event",
            kind="event",
            inputs=("sum",),
            config={
                "operator": "any_exceed",
                "relation_type": {"sum": "statistical"},
                "parameters": {
                    "bindings": {"value": "sum"},
                    "threshold": 1,
                    "comparator": "gt",
                },
            },
        ),
    )
    ledger = Ledger(tmp_path / "ledger.sqlite")
    run = Runtime(ledger, {"seasonal_naive": Fixture(2)}, operators, lambda: T).run(
        graph(extra=extra), {"data": snapshot()}, T, "builtins"
    )
    if fault:
        assert run.state == "failed"
        assert (
            ("sum" not in run.results)
            if fault != "event_window"
            else ("event" not in run.results)
        )
    else:
        assert run.state == "completed"
        assert run.results["sum"].paths == (((2, 0, 0),), ((0, 2, 0),))
        assert run.results["event"].point == ((1,),)
        assert run.results["event"].timestamps == (T + timedelta(hours=2),)
