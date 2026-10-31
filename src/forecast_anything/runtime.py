"""Compile, validate, execute, and atomically publish immutable emissions."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import TYPE_CHECKING, Callable

from .contracts import (
    REPRESENTATION_FIELDS,
    Capabilities,
    DomainError,
    EventRecord,
    ForecastRequest,
    ForecastResult,
    GraphSpec,
    OperatorContract,
    RunRecord,
    Snapshot,
)
from .graph import (
    ForecastConfig,
    SourceConfig,
    compile_graph,
    parse_node_config,
)
from .operators.base import Operator
from .providers.base import ForecastProvider, frequency_step, observation_grid
from .store import Ledger

if TYPE_CHECKING:
    from .jobs import LeaseGuard


def _digest(value: dict) -> str:
    wire = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(wire.encode()).hexdigest()


def _result(value) -> ForecastResult:
    # Revalidation catches mutable models and malicious adapters using model_copy.
    result = ForecastResult.model_validate(value.model_dump())
    # Compare absolute instants: same-ZoneInfo datetime comparisons ignore fold.
    result.timestamps = tuple(
        timestamp.astimezone(timezone.utc) for timestamp in result.timestamps
    )
    if not result.series_ids or len(set(result.series_ids)) != len(result.series_ids):
        raise DomainError(
            "invalid_result", {"reason": "series IDs must be nonempty and unique"}
        )
    if not result.timestamps or any(
        b <= a for a, b in zip(result.timestamps, result.timestamps[1:])
    ):
        raise DomainError(
            "invalid_result", {"reason": "timestamps must be nonempty and ordered"}
        )
    if result.paths is not None and not result.paths:
        raise DomainError("invalid_result", {"reason": "paths must contain samples"})
    if all(getattr(result, rep) is None for rep in ("point", "quantiles", "paths")):
        raise DomainError(
            "invalid_result", {"reason": "missing numerical representation"}
        )
    return result


def _require_representations(result, representations):
    if any(
        rep not in REPRESENTATION_FIELDS
        or not getattr(result, REPRESENTATION_FIELDS[rep])
        for rep in representations
    ):
        raise DomainError(
            "unsupported_representation", {"required": list(representations)}
        )


class Runtime:
    def __init__(
        self,
        ledger: Ledger,
        providers: dict[str, ForecastProvider],
        operators: dict[str, Operator],
        clock: Callable[[], datetime],
    ):
        self.ledger, self.providers, self.operators, self.clock = (
            ledger,
            providers,
            operators,
            clock,
        )

    def run(
        self,
        spec: GraphSpec,
        snapshots: dict[str, Snapshot],
        as_of: datetime,
        key: str,
        lease_guard: LeaseGuard | None = None,
        previous_run_id: str | None = None,
        scenario_id: str | None = None,
    ) -> RunRecord:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise DomainError("naive_timestamp", {"field": "as_of"})
        if not key:
            raise DomainError("invalid_key", {})
        as_of = as_of.astimezone(timezone.utc)
        spec = GraphSpec.model_validate(spec.model_dump())
        snapshots = {
            name: Snapshot.model_validate(value.model_dump())
            for name, value in snapshots.items()
        }
        scenario = self.ledger.scenario_for_graph(spec.graph_id, spec.version)
        if scenario_id is not None:
            if (
                scenario is None
                or scenario.scenario_id != scenario_id
                or scenario.parent_run_id != previous_run_id
                or scenario.snapshot_ids
                != {name: snap.snapshot_id for name, snap in snapshots.items()}
                or self.ledger.get_graph(spec.graph_id, spec.version) != spec
            ):
                raise DomainError("invalid_scenario_lineage", {})
            parent = self.ledger.get_run(previous_run_id)
            if as_of != parent.as_of:
                raise DomainError("invalid_scenario_lineage", {})
        elif scenario is not None or any(
            any(a.startswith("assumed:") for a in snapshot.assumptions)
            for snapshot in snapshots.values()
        ):
            raise DomainError("scenario_required", {})
        fingerprint = _digest(
            {
                "graph": spec.model_dump(mode="json"),
                "snapshots": {
                    name: value.model_dump(mode="json")
                    for name, value in snapshots.items()
                },
                "as_of": as_of.isoformat(),
                **({"scenario_id": scenario_id} if scenario_id else {}),
                **(
                    {"previous_run_id": previous_run_id}
                    if previous_run_id is not None
                    else {}
                ),
            }
        )
        run_id = _digest({"key": key, "request": fingerprint})
        previous = self.ledger.get_run_by_key(key)
        if previous is not None:
            if previous.run_id != run_id:
                raise DomainError("idempotency_conflict", {"key": key})
            return previous

        capabilities = {
            name: Capabilities.model_validate(provider.capabilities().model_dump())
            for name, provider in self.providers.items()
        }
        contracts = {
            name: OperatorContract.model_validate(operator.contract().model_dump())
            for name, operator in self.operators.items()
        }
        compiled = compile_graph(spec, capabilities, contracts)
        nodes = {node.node_id: node for node in spec.nodes}
        configs = {key: parse_node_config(node) for key, node in nodes.items()}
        source_keys = {
            c.source_id for c in configs.values() if isinstance(c, SourceConfig)
        }
        if source_keys != set(snapshots):
            raise DomainError(
                "invalid_snapshot_bindings",
                {"expected": sorted(source_keys), "actual": sorted(snapshots)},
            )
        reusable = {}
        if previous_run_id is not None:
            prior = self.ledger.get_run(previous_run_id)
            if (prior.graph_id, prior.graph_version, prior.as_of, prior.state) == (
                spec.graph_id,
                spec.version,
                as_of,
                "completed",
            ) and self.ledger.get_graph(prior.graph_id, prior.graph_version) == spec:
                old_bindings = self.ledger.run_bindings(previous_run_id)
                affected = set()
                for node_id in compiled.order:
                    config = configs[node_id]
                    node = nodes[node_id]
                    if isinstance(config, SourceConfig):
                        if (
                            old_bindings.get(config.source_id)
                            != snapshots[config.source_id].snapshot_id
                        ):
                            affected.add(node_id)
                    elif isinstance(config, ForecastConfig):
                        result = prior.results.get(node_id)
                        capability = capabilities[config.provider]
                        if result is None or (
                            result.provider_id,
                            result.provider_revision,
                        ) != (capability.provider_id, capability.provider_revision):
                            affected.add(node_id)
                    if any(parent in affected for parent in node.inputs):
                        affected.add(node_id)
                    if node_id not in affected and node_id in prior.results:
                        reusable[node_id] = prior.results[node_id]
        values, calendars, requests = {}, {}, {}
        # All actual source metadata and request calendars are checked before inference.
        for node_id in compiled.order:
            config = configs[node_id]
            if isinstance(config, SourceConfig):
                snapshot = snapshots[config.source_id]
                if snapshot.as_of.astimezone(timezone.utc) != as_of:
                    raise DomainError("snapshot_origin_mismatch", {"node_id": node_id})
                groups, calendar = observation_grid(snapshot, config.frequency)
                if set(groups) != set(config.series_ids) or any(
                    groups[s][0].unit != unit
                    for s, unit in zip(config.series_ids, config.units)
                ):
                    raise DomainError("source_metadata_mismatch", {"node_id": node_id})
                values[node_id], calendars[node_id] = snapshot, calendar
            elif isinstance(config, ForecastConfig):
                history = values[config.history]
                if calendars[config.history][-1] > as_of:
                    raise DomainError("future_history", {"node_id": node_id})
                step = frequency_step(config.frequency)
                expected = tuple(
                    calendars[config.history][-1] + step * (i + 1)
                    for i in range(config.horizon)
                )
                known_future = (
                    values[config.known_future] if config.known_future else None
                )
                if (
                    known_future is not None
                    and calendars[config.known_future] != expected
                ):
                    raise DomainError(
                        "known_future_calendar_mismatch", {"node_id": node_id}
                    )
                requests[node_id] = ForecastRequest(
                    snapshot=history,
                    horizon=config.horizon,
                    frequency=config.frequency,
                    known_future=known_future,
                    options=deepcopy(config.options),
                )
                calendars[node_id] = expected

        self.ledger.put_graph(spec, lease_guard=lease_guard)
        for snapshot in snapshots.values():
            self.ledger.put_snapshot(snapshot, lease_guard=lease_guard)
        emitted_at = self.clock()
        if emitted_at.tzinfo is None or emitted_at.utcoffset() is None:
            raise DomainError("naive_timestamp", {"field": "clock"})
        events = []

        def emit(kind, payload):
            events.append(
                EventRecord(
                    cursor=0,
                    event_id=f"{run_id}:{len(events)}",
                    kind=kind,
                    run_id=run_id,
                    payload={"emitted_at": emitted_at.isoformat(), **payload},
                )
            )

        emit(
            "run_started",
            {
                "request_fingerprint": fingerprint,
                "order": list(compiled.order),
                "source_bindings": {
                    name: snap.snapshot_id for name, snap in snapshots.items()
                },
            },
        )
        requested = {
            node_id: config.provider
            for node_id, config in configs.items()
            if isinstance(config, ForecastConfig)
        }
        actual, results, guaranteed = {}, {}, {}
        state = "completed"
        for node_id in compiled.order:
            config = configs[node_id]
            node = nodes[node_id]
            try:
                if isinstance(config, SourceConfig):
                    emit(
                        "node_completed",
                        {
                            "node_id": node_id,
                            "dependencies": [],
                            "snapshot_id": values[node_id].snapshot_id,
                        },
                    )
                    continue
                if isinstance(config, ForecastConfig):
                    capability = capabilities[config.provider]
                    actual[node_id] = capability.provider_id
                    result = _result(
                        reusable[node_id]
                        if node_id in reusable
                        else self.providers[config.provider].forecast(
                            requests[node_id].model_copy(deep=True)
                        )
                    )
                    source = configs[config.history]
                    expected_units = dict(zip(source.series_ids, source.units))
                    if (
                        result.provider_id != capability.provider_id
                        or result.provider_revision != capability.provider_revision
                        or result.timestamps != calendars[node_id]
                        or set(result.series_ids) != set(source.series_ids)
                        or any(
                            unit != expected_units[s]
                            for s, unit in zip(result.series_ids, result.units)
                        )
                    ):
                        raise DomainError(
                            "invalid_provider_output", {"node_id": node_id}
                        )
                    _require_representations(result, capability.representations)
                    guaranteed[node_id] = set(capability.representations)
                    bindings = {"history": config.history}
                    if config.known_future:
                        bindings["known_future"] = config.known_future
                else:
                    contract = contracts[config.operator]
                    bindings = config.parameters.get("bindings") or {
                        name: name for name in node.inputs
                    }
                    inputs = {role: values[parent] for role, parent in bindings.items()}
                    forecasts = [
                        value
                        for value in inputs.values()
                        if isinstance(value, ForecastResult)
                    ]
                    common = contract.accepted_inputs().intersection(
                        *(guaranteed[parent] for parent in node.inputs)
                    )
                    if not common or len(forecasts) != len(inputs):
                        raise DomainError(
                            "unsupported_representation", {"node_id": node_id}
                        )
                    for value in forecasts:
                        _require_representations(value, common)
                    if forecasts and any(
                        value.timestamps != forecasts[0].timestamps
                        for value in forecasts
                    ):
                        raise DomainError("incompatible_calendar", {"node_id": node_id})
                    if (
                        "joint_paths" in common
                        and forecasts
                        and any(
                            value.sample_group_id != forecasts[0].sample_group_id
                            or len(value.paths) != len(forecasts[0].paths)
                            for value in forecasts
                        )
                    ):
                        raise DomainError("incompatible_samples", {"node_id": node_id})
                    parameters = {
                        k: v for k, v in config.parameters.items() if k != "bindings"
                    }
                    result = _result(
                        reusable[node_id]
                        if node_id in reusable
                        else self.operators[config.operator].apply(
                            deepcopy(inputs), deepcopy(parameters)
                        )
                    )
                    output_reps = contract.output_representations(common, node.kind)
                    _require_representations(result, output_reps)
                    guaranteed[node_id] = output_reps
                    if (
                        "joint_paths" in output_reps
                        and "joint_paths" in common
                        and (
                            result.sample_group_id != forecasts[0].sample_group_id
                            or len(result.paths) != len(forecasts[0].paths)
                        )
                    ):
                        raise DomainError("incompatible_samples", {"node_id": node_id})
                    if contract.output_representation == "preserve" and any(
                        result.series_ids != value.series_ids for value in forecasts
                    ):
                        raise DomainError("incompatible_series", {"node_id": node_id})
                    if (
                        node.kind == "event"
                        and contract.output_representation == "point"
                        and contract.units_rule == "probability"
                    ):
                        if (
                            len(result.series_ids) != 1
                            or result.timestamps != (forecasts[0].timestamps[-1],)
                            or result.paths is not None
                            or result.quantiles is not None
                            or result.sample_group_id is not None
                            or not 0 <= result.point[0][0] <= 1
                        ):
                            raise DomainError(
                                "invalid_event_output", {"node_id": node_id}
                            )
                    input_units = {
                        unit
                        for value in inputs.values()
                        for unit in (
                            value.units
                            if isinstance(value, ForecastResult)
                            else tuple(o.unit for o in value.observations)
                        )
                    }
                    expected_units = (
                        {"1"}
                        if contract.units_rule == "dimensionless"
                        else {"probability"}
                        if contract.units_rule == "probability"
                        else input_units
                    )
                    if set(result.units) != expected_units:
                        raise DomainError("incompatible_units", {"node_id": node_id})
                    if (
                        node.kind == "transform"
                        and forecasts
                        and result.timestamps != forecasts[0].timestamps
                    ):
                        raise DomainError("incompatible_calendar", {"node_id": node_id})
                values[node_id] = result
                results[node_id] = result
                emit(
                    "node_completed",
                    {
                        "node_id": node_id,
                        "dependencies": list(node.inputs),
                        "bindings": bindings,
                        "config": deepcopy(node.config),
                        "provider_id": result.provider_id,
                        "provider_revision": result.provider_revision,
                    },
                )
            except Exception as error:
                state = "failed"
                failure = (
                    error.model_dump()
                    if isinstance(error, DomainError)
                    else {
                        "code": "execution_error",
                        "details": {
                            "type": type(error).__name__,
                            "message": str(error),
                        },
                    }
                )
                payload = {"node_id": node_id, "error": failure}
                if isinstance(config, ForecastConfig):
                    payload.update(
                        provider_id=capabilities[config.provider].provider_id,
                        provider_revision=capabilities[
                            config.provider
                        ].provider_revision,
                    )
                emit("run_failed", payload)
                break
        if state == "completed":
            emit("run_completed", {"node_ids": list(results)})
        run = RunRecord(
            run_id=run_id,
            graph_id=spec.graph_id,
            graph_version=spec.version,
            as_of=as_of,
            snapshot_ids=tuple(
                sorted({snap.snapshot_id for snap in snapshots.values()})
            ),
            requested_provider=requested,
            actual_provider=actual,
            state=state,
            results=results,
            evidence_ids=(),
            scenario_id=scenario_id,
            parent_run_id=previous_run_id,
        )
        return self.ledger.append_run(run, tuple(events), key, lease_guard=lease_guard)
