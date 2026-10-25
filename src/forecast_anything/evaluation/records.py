"""Point-in-time evaluations of issued results, without rewriting an emission."""

import json
from datetime import timezone
from hashlib import sha256

from ..contracts import (
    DomainError,
    EvaluationRecord,
    GraphSpec,
    RunRecord,
    Snapshot,
)
from ..graph import ForecastConfig, parse_node_config
from ..operators import register_builtin_operators
from ..temporal import freeze
from .metrics import event_metrics, forecast_metrics, relative_mae


def evaluate_run(
    run: RunRecord, actuals: Snapshot, graph: GraphSpec, *, operators=None
) -> EvaluationRecord:
    """Score complete targets using only the selected actuals vintage.

    One run is one origin. Missing partial targets never contribute a shorter
    comparison. Supply the runtime's operator registry for custom operators;
    the explicit builtin registry is the default. Scenario realizations are not
    represented by v1 contracts, so scenario runs remain insufficient evidence.
    """
    run = RunRecord.model_validate(run.model_dump())
    actuals = Snapshot.model_validate(actuals.model_dump())
    graph = GraphSpec.model_validate(graph.model_dump())
    run.as_of = run.as_of.astimezone(timezone.utc)
    actuals.as_of = actuals.as_of.astimezone(timezone.utc)
    for forecast in run.results.values():
        forecast.timestamps = tuple(
            t.astimezone(timezone.utc) for t in forecast.timestamps
        )
    if (run.graph_id, run.graph_version) != (graph.graph_id, graph.version):
        raise DomainError("graph_identity_mismatch", {})
    operators = register_builtin_operators() if operators is None else operators
    metrics, assumptions = (
        {},
        [
            "evaluation=v1; one issued run is one origin; complete target windows only",
            "actuals are selected by available_at <= actuals.as_of; no emission is modified",
        ],
    )
    available = freeze(actuals.observations, actuals.as_of)
    observations = {(o.series_id, o.event_time): o for o in available.observations}
    nodes = {n.node_id: n for n in graph.nodes}
    configs = {n.node_id: parse_node_config(n) for n in graph.nodes}
    observed, states, visiting = {}, {}, set()

    def reconstruct(node_id):
        if node_id in states:
            return observed.get(node_id)
        if node_id in visiting:
            raise DomainError("cycle", {"node_id": node_id})
        visiting.add(node_id)
        node, forecast = nodes[node_id], run.results.get(node_id)
        state, answer = "insufficient_evidence", None
        if node.kind == "forecast" and forecast is not None:
            if (
                not forecast.timestamps
                or not forecast.series_ids
                or any(t <= run.as_of for t in forecast.timestamps)
            ):
                raise DomainError("invalid_forecast_calendar", {"node_id": node_id})
            cells = [
                [observations.get((series, t)) for t in forecast.timestamps]
                for series in forecast.series_ids
            ]
            if (
                all(o is not None and o.value is not None for row in cells for o in row)
                and forecast.timestamps[-1] <= actuals.as_of
            ):
                if any(
                    o.unit != unit
                    for row, unit in zip(cells, forecast.units)
                    for o in row
                ):
                    raise DomainError("incompatible_units", {"node_id": node_id})
                matrix = tuple(tuple(o.value for o in row) for row in cells)
                answer = forecast.model_copy(
                    update={
                        "point": matrix,
                        "quantiles": None,
                        "paths": (matrix,),
                        "sample_group_id": f"actuals:{actuals.snapshot_id}",
                    }
                )
                state = "evaluated"
            elif forecast.timestamps[-1] > actuals.as_of or any(
                o.available_at > actuals.as_of
                and o.series_id in forecast.series_ids
                and o.event_time in forecast.timestamps
                for o in actuals.observations
            ):
                state = "pending"
        elif node.kind in {"transform", "event"}:
            config = configs[node_id]
            inputs = {parent: reconstruct(parent) for parent in node.inputs}
            if inputs and all(value is not None for value in inputs.values()):
                operator = operators.get(config.operator)
                if operator is None:
                    raise DomainError("unknown_operator", {"operator": config.operator})
                bindings = config.parameters.get("bindings") or {
                    parent: parent for parent in node.inputs
                }
                answer = operator.apply(
                    {role: inputs[parent] for role, parent in bindings.items()},
                    {
                        key: value
                        for key, value in config.parameters.items()
                        if key != "bindings"
                    },
                )
                state = "evaluated"
            elif any(states[parent] == "pending" for parent in node.inputs):
                state = "pending"
        visiting.remove(node_id)
        states[node_id] = state
        if answer is not None:
            observed[node_id] = answer
        return answer

    if run.scenario_id is not None:
        status = "insufficient_evidence"
        assumptions.append("hypothetical scenario has no observed realization binding")
    else:
        for node_id, forecast in run.results.items():
            if node_id not in nodes or nodes[node_id].kind == "source":
                raise DomainError("invalid_evaluation_node", {"node_id": node_id})
            outcome = reconstruct(node_id)
            if outcome is None:
                metrics[node_id] = {
                    "status": states[node_id],
                    "count": 0,
                    "brier" if nodes[node_id].kind == "event" else "mae": None,
                }
            elif nodes[node_id].kind == "event":
                if (
                    forecast.point is None
                    or outcome.point is None
                    or len(forecast.series_ids) != 1
                    or len(outcome.series_ids) != 1
                    or len(forecast.timestamps) != 1
                    or forecast.timestamps != outcome.timestamps
                    or outcome.units != ("probability",)
                    or outcome.paths is not None
                    or outcome.quantiles is not None
                ):
                    raise DomainError("invalid_event_outcome", {"node_id": node_id})
                metrics[node_id] = {
                    "status": "evaluated",
                    **event_metrics(forecast.point[0][0], outcome.point[0][0]),
                }
            else:
                if (
                    forecast.series_ids != outcome.series_ids
                    or forecast.timestamps != outcome.timestamps
                    or forecast.units != outcome.units
                ):
                    raise DomainError(
                        "incompatible_observed_result", {"node_id": node_id}
                    )
                metrics[node_id] = {
                    "status": "evaluated",
                    **forecast_metrics(forecast, outcome.point),
                }
                if forecast.point is None and not forecast.quantiles:
                    metrics[node_id].update(
                        status="insufficient_evidence",
                        reason="no_supported_score_representation",
                    )
        for node_id, score in metrics.items():
            if "mae" not in score or score["status"] != "evaluated":
                continue
            config = configs[node_id]
            baseline_id = None
            if isinstance(config, ForecastConfig):
                forecast = run.results[node_id]
                for other, candidate in sorted(configs.items()):
                    baseline = run.results.get(other)
                    if (
                        isinstance(candidate, ForecastConfig)
                        and baseline is not None
                        and baseline.provider_id == "seasonal_naive"
                        and (
                            candidate.history,
                            candidate.known_future,
                            candidate.horizon,
                            candidate.frequency,
                        )
                        == (
                            config.history,
                            config.known_future,
                            config.horizon,
                            config.frequency,
                        )
                        and (baseline.series_ids, baseline.timestamps, baseline.units)
                        == (forecast.series_ids, forecast.timestamps, forecast.units)
                        and metrics.get(other, {}).get("status") == "evaluated"
                    ):
                        baseline_id = other
                        break
            score["baseline_node_id"] = baseline_id
            score["relative_mae"], score["relative_mae_reason"] = relative_mae(
                score["mae"], metrics[baseline_id]["mae"] if baseline_id else None
            )
        status = (
            "pending"
            if any(s["status"] == "pending" for s in metrics.values())
            else "evaluated"
            if metrics and all(s["status"] == "evaluated" for s in metrics.values())
            else "insufficient_evidence"
        )
    record = dict(
        run_id=run.run_id,
        actuals_snapshot_id=actuals.snapshot_id,
        status=status,
        metrics=metrics,
        origin_count=int(any(s.get("status") == "evaluated" for s in metrics.values())),
        assumptions=tuple(assumptions) + actuals.assumptions,
    )
    identity = json.dumps(
        {
            "record": record,
            "run": run.model_dump(mode="json"),
            "actuals": actuals.model_dump(mode="json"),
            "graph": graph.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return EvaluationRecord(
        evaluation_id=sha256(identity.encode()).hexdigest(), **record
    )
