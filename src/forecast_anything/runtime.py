"""Compile, validate, execute, and atomically publish immutable emissions."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING

from .contracts import (
    Capabilities,
    DomainError,
    EventRecord,
    ForecastRequest,
    GraphSpec,
    ModelSelectionEvidence,
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
from .runtime_results import _require_representations, _result, apply_operator
from .store import Ledger

if TYPE_CHECKING:
    from .jobs import LeaseGuard


def _digest(value: dict) -> str:
    wire = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(wire.encode()).hexdigest()


class Runtime:
    def __init__(
        self,
        ledger: Ledger,
        providers: dict[str, ForecastProvider],
        operators: dict[str, Operator],
        clock: Callable[[], datetime],
        *,
        required_provider: str | None = None,
    ):
        self.required_provider = required_provider
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
        primary_node_id: str | None = None,
        model_selection: ModelSelectionEvidence | None = None,
    ) -> RunRecord:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise DomainError("naive_timestamp", {"field": "as_of"})
        if not key:
            raise DomainError("invalid_key", {})
        as_of = as_of.astimezone(UTC)
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
                or scenario.primary_node_id != primary_node_id
                or scenario.snapshot_ids
                != {name: snap.snapshot_id for name, snap in snapshots.items()}
                or self.ledger.get_graph(spec.graph_id, spec.version) != spec
            ):
                raise DomainError("invalid_scenario_lineage", {})
            parent = self.ledger.get_run(previous_run_id)
            if as_of != parent.as_of or model_selection != parent.model_selection:
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
                **(
                    {"model_selection": model_selection.model_dump(mode="json")}
                    if model_selection
                    else {}
                ),
                **({"scenario_id": scenario_id} if scenario_id else {}),
                **(
                    {"primary_node_id": primary_node_id}
                    if primary_node_id is not None
                    else {}
                ),
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

        from .forecast_policy import ensure_required_model, validate_primary_provider

        selected = (
            model_selection.provider if model_selection else self.required_provider
        )
        resolved_primary = validate_primary_provider(spec, selected, primary_node_id)
        if selected == self.required_provider:
            ensure_required_model(self)

        capabilities = {
            name: Capabilities.model_validate(provider.capabilities().model_dump())
            for name, provider in self.providers.items()
        }
        if model_selection is not None and (
            selected not in capabilities
            or capabilities[selected].provider_revision
            != model_selection.provider_revision
        ):
            raise DomainError("provider_contract_changed", {"provider_id": selected})
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
                if snapshot.as_of.astimezone(UTC) != as_of:
                    raise DomainError("snapshot_origin_mismatch", {"node_id": node_id})
                groups, calendar = observation_grid(snapshot, config.frequency)
                if set(groups) != set(config.series_ids) or any(
                    groups[s][0].unit != unit
                    for s, unit in zip(config.series_ids, config.units, strict=False)
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
                    expected_units = dict(
                        zip(source.series_ids, source.units, strict=False)
                    )
                    if (
                        result.provider_id != capability.provider_id
                        or result.provider_revision != capability.provider_revision
                        or result.timestamps != calendars[node_id]
                        or set(result.series_ids) != set(source.series_ids)
                        or any(
                            unit != expected_units[s]
                            for s, unit in zip(
                                result.series_ids, result.units, strict=False
                            )
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
                    result, bindings, guaranteed[node_id] = apply_operator(
                        node,
                        config,
                        self.operators,
                        contracts[config.operator],
                        values,
                        guaranteed,
                        reusable.get(node_id),
                    )
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
            model_selection=model_selection,
            primary_node_id=resolved_primary,
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
