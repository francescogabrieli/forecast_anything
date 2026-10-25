"""Create isolated assumed inputs and immutable scenario lineage."""

from ..contracts import (
    DomainError,
    GraphSpec,
    ScenarioRecord,
    ScenarioRequest,
    ScenarioView,
    Snapshot,
)
from ..jobs import JobQueue
from ..runtime import Runtime, _digest


def create_scenario(runtime: Runtime, request: ScenarioRequest) -> ScenarioView:
    request = ScenarioRequest.model_validate(request.model_dump())
    ledger = runtime.ledger
    base = ledger.get_graph(request.base_graph_id, request.base_version)
    parent = ledger.latest_run(base.graph_id, base.version)
    if parent.scenario_id is not None:
        raise DomainError("invalid_scenario_lineage", {})
    bindings = ledger.run_bindings(parent.run_id)
    if not request.source_overrides or not set(request.source_overrides) <= set(
        bindings
    ):
        raise DomainError("invalid_scenario_overrides", {})
    scenario_id = _digest(
        {"request": request.model_dump(mode="json"), "parent_run_id": parent.run_id}
    )
    snapshots = {name: ledger.get_snapshot(sid) for name, sid in bindings.items()}
    for name, override in request.source_overrides.items():
        if override.as_of != parent.as_of:
            raise DomainError("snapshot_origin_mismatch", {})
        original = snapshots[name]
        if {(o.series_id, o.unit) for o in override.observations} != {
            (o.series_id, o.unit) for o in original.observations
        }:
            raise DomainError("source_metadata_mismatch", {})
        content = override.model_dump()
        content["snapshot_id"] = _digest({"scenario": scenario_id, "source": name})
        content["assumptions"] = (
            *override.assumptions,
            f"assumed:{scenario_id}",
            "hypothetical inputs; not observed outcomes",
        )
        content["observations"] = tuple(
            o.model_copy(update={"revision": f"assumed:{scenario_id}"})
            for o in override.observations
        )
        snapshots[name] = Snapshot.model_validate(content)
    graph = GraphSpec(
        graph_id=_digest({"scenario_id": scenario_id}), version=1, nodes=base.nodes
    )
    # Validate before persistence/enqueue; no inference runs inside this boundary.
    from .service import validate_run

    validate_run(runtime, graph, snapshots, parent.as_of)
    ledger.put_graph(graph)
    for snap in snapshots.values():
        ledger.put_snapshot(snap)
    record = ScenarioRecord(
        scenario_id=scenario_id,
        graph_id=graph.graph_id,
        version=1,
        parent_run_id=parent.run_id,
        label=request.label,
        snapshot_ids={name: snap.snapshot_id for name, snap in snapshots.items()},
    )
    ledger.put_scenario(record)
    job = JobQueue(ledger).enqueue(
        f"scenario/{scenario_id}",
        {
            "kind": "run",
            "graph": graph.model_dump(mode="json"),
            "snapshots": {
                name: snap.model_dump(mode="json") for name, snap in snapshots.items()
            },
            "as_of": parent.as_of.isoformat(),
            "previous_run_id": parent.run_id,
            "scenario_id": scenario_id,
        },
    )
    return ScenarioView(**record.model_dump(), job_id=job.job_id)
