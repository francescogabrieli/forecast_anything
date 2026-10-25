from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from forecast_anything.contracts import (
    Observation, Snapshot, Node, GraphSpec, CompiledGraph, Capabilities,
    OperatorContract, ForecastRequest, ForecastResult, RunRecord, EventRecord,
    DomainError,
)

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def observation(**overrides):
    return dict(series_id="s", event_time=NOW, available_at=NOW,
                revision="1", value=1.0, unit="count") | overrides


def result(**overrides):
    return dict(provider_id="baseline", provider_revision="1", series_ids=("s",),
                timestamps=(NOW,), units=("count",), point=((1.0,),), quantiles=None,
                paths=None, sample_group_id=None, assumptions=("held constant",)) | overrides


@pytest.mark.parametrize("value", [1.0, None])
def test_roundtrip_observation(value):
    original = Observation(**observation(value=value))
    restored = Observation.model_validate_json(original.model_dump_json())
    assert restored.model_dump() == observation(value=value)


def test_timestamp_requires_timezone():
    with pytest.raises(ValidationError):
        Observation(series_id="s", event_time=datetime(2026, 10, 24),
                    available_at=NOW, revision="1", value=1.0, unit="count")


@pytest.mark.parametrize("changes", [
    {"point": ((float("inf"),),)}, {"point": ((float("nan"),),)},
    {"point": ((1., 2.),)}, {"units": ()},
    {"quantiles": {"0.5": ((1., 2.),)}},
    {"paths": (((1.,),),)},
    {"paths": (((1., 2.),),), "sample_group_id": "joint"},
    {"timestamps": (datetime(2026, 10, 24),)},
])
def test_reject_nonfinite_and_bad_shapes(changes):
    with pytest.raises(ValidationError):
        ForecastResult(**result(**changes))


def test_quantiles_and_paths_roundtrip():
    data = result(quantiles={"0.5": ((1.,),)}, paths=(((1.,),),), sample_group_id="joint")
    value = ForecastResult(**data)
    assert ForecastResult.model_validate_json(value.model_dump_json()).model_dump() == data


@pytest.mark.parametrize("changes", [{"series_id": ""}, {"revision": " "},
                                        {"value": float("inf")}, {"extra": 1}])
def test_observation_rejects_invalid_boundary_values(changes):
    with pytest.raises(ValidationError):
        Observation(**observation(**changes))


def test_horizon_positive_and_opaque_config():
    snapshot = Snapshot(snapshot_id="snap", as_of=NOW, observations=(), assumptions=("empty",))
    with pytest.raises(ValidationError):
        ForecastRequest(snapshot=snapshot, horizon=0, frequency="1h", known_future=None)
    node = Node(node_id="n", kind="source", inputs=(), config={"custom": {"anything": 1}})
    graph = GraphSpec(graph_id="g", version=1, nodes=(node,))
    assert CompiledGraph(spec=graph, order=("n",), dependencies={"n": ()}).spec == graph
    assert snapshot.assumptions == ("empty",)


def test_operational_contracts_and_schema():
    cap = Capabilities(provider_id="p", provider_revision="1", representations=("point",), supports_known_future=False)
    assert cap.representations == ("point",)
    assert OperatorContract(name="sum", required_representation="point", units_rule="same").name == "sum"
    run = RunRecord(run_id="r", graph_id="g", graph_version=1, as_of=NOW,
                    snapshot_ids=("s",), requested_provider={"n": "p"}, actual_provider={"n": "p"},
                    state="succeeded", results={"n": ForecastResult(**result())}, evidence_ids=(),
                    scenario_id=None, parent_run_id=None)
    assert RunRecord.model_validate_json(run.model_dump_json()) == run
    event = EventRecord(cursor=1, event_id="e", kind="run.completed", run_id="r", payload={"custom": 1})
    assert EventRecord.model_validate_json(event.model_dump_json()) == event
    assert ForecastResult.model_json_schema()["additionalProperties"] is False
    error = DomainError(code="bad_input", details={"node": "n"})
    assert error.model_dump() == {"code": "bad_input", "details": {"node": "n"}}
    assert isinstance(error, Exception)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("boundary", ["config", "payload", "details"])
def test_opaque_dictionaries_reject_nested_nonfinite_values(boundary, number):
    nested = {"arbitrary": [{"nested": ("preserved", number)}]}
    with pytest.raises(ValidationError):
        if boundary == "config":
            Node(node_id="n", kind="source", inputs=(), config=nested)
        elif boundary == "payload":
            EventRecord(cursor=1, event_id="e", kind="custom", run_id="r", payload=nested)
        else:
            DomainError(code="custom", details=nested)


def test_opaque_dictionary_preserves_finite_nested_structure():
    nested = {"arbitrary": [{"nested": ("preserved", 3.5, None)}]}
    node = Node(node_id="n", kind="source", inputs=(), config=nested)
    assert node.config == nested
