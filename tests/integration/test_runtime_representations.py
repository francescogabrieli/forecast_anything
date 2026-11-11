"""Runtime support for path and quantile representations."""

from datetime import timedelta

import pytest
from runtime_fixtures import T, graph, snapshot

from forecast_anything.contracts import (
    DomainError,
    Node,
    OperatorContract,
)
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger


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
                            tuple(a + b for a, b in zip(ar, br, strict=False))
                            for ar, br in zip(ap, bp, strict=False)
                        )
                        for ap, bp in zip(left.paths, right.paths, strict=False)
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
