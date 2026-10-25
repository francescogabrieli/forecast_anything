import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from forecast_anything.contracts import (
    DomainError,
    ForecastResult,
    GraphSpec,
    Node,
    Observation,
    RunRecord,
    Snapshot,
)
from forecast_anything.evaluation.records import evaluate_run
from forecast_anything.evaluation.splits import build_splits
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze

T = datetime(2026, 1, 1, tzinfo=timezone.utc)
GRID = (T + timedelta(days=1), T + timedelta(days=2))


def result(values=(2, 4), provider="model", **changes):
    return ForecastResult.model_validate(
        dict(
            provider_id=provider,
            provider_revision="1",
            series_ids=("s",),
            timestamps=GRID,
            units=("count",),
            point=(values,),
            quantiles=None,
            paths=None,
            sample_group_id=None,
            assumptions=(),
        )
        | changes
    )


def graph(event=False):
    nodes = [
        Node(
            node_id="source",
            kind="source",
            inputs=(),
            config={
                "source_id": "source",
                "series_ids": ["s"],
                "units": ["count"],
                "frequency": "1d",
            },
        )
    ]
    for name, provider in (("model", "model"), ("baseline", "seasonal_naive")):
        nodes.append(
            Node(
                node_id=name,
                kind="forecast",
                inputs=("source",),
                config={
                    "provider": provider,
                    "history": "source",
                    "horizon": 2,
                    "frequency": "1d",
                    "relation_type": {"source": "statistical"},
                },
            )
        )
    if event:
        nodes.extend(
            (
                Node(
                    node_id="total",
                    kind="transform",
                    inputs=("model", "baseline"),
                    config={
                        "operator": "sum_aligned",
                        "relation_type": {
                            "model": "accounting",
                            "baseline": "accounting",
                        },
                    },
                ),
                Node(
                    node_id="event",
                    kind="event",
                    inputs=("total",),
                    config={
                        "operator": "any_exceed",
                        "relation_type": {"total": "statistical"},
                        "parameters": {
                            "bindings": {"value": "total"},
                            "threshold": 5,
                            "comparator": "gt",
                        },
                    },
                ),
            )
        )
    return GraphSpec(graph_id="g", version=1, nodes=tuple(nodes))


def run(values=(2, 4), baseline=(1, 3), **changes):
    return RunRecord.model_validate(
        dict(
            run_id="issued",
            graph_id="g",
            graph_version=1,
            as_of=T,
            snapshot_ids=("history",),
            requested_provider={"model": "model", "baseline": "seasonal_naive"},
            actual_provider={"model": "model", "baseline": "seasonal_naive"},
            state="completed",
            results={
                "model": result(values),
                "baseline": result(baseline, "seasonal_naive"),
            },
            evidence_ids=(),
            scenario_id=None,
            parent_run_id=None,
        )
        | changes
    )


def actuals(values=(2, 4), as_of=None, revision="1", available_at=None):
    return freeze(
        tuple(
            Observation(
                series_id="s",
                event_time=t,
                available_at=available_at or t,
                revision=revision,
                value=value,
                unit="count",
            )
            for t, value in zip(GRID, values)
        ),
        as_of or GRID[-1],
    )


def test_final_split_is_separate():
    split = build_splits(tuple(T + timedelta(days=i) for i in range(100)), horizon=5)
    assert split.exploration_end < split.selection_end < split.final_start
    assert split.stride == split.horizon == 5
    assert split.exploration_end == T + timedelta(days=49)
    assert split.selection_end == T + timedelta(days=74)
    assert split.final_start == T + timedelta(days=75)


def test_no_overlap_final_split():
    timestamps = tuple(T + timedelta(days=i) for i in range(103))
    split = build_splits(timestamps, horizon=5)
    windows = {}
    for partition in ("exploration", "selection", "final"):
        origins = split.origins_for(partition, timestamps)
        windows[partition] = [
            set(timestamps[timestamps.index(origin) + 1 : timestamps.index(origin) + 6])
            for origin in origins
        ]
        assert all(len(w) == 5 for w in windows[partition])
        assert all(
            not a & b for a, b in zip(windows[partition], windows[partition][1:])
        )
    assert max(set.union(*windows["exploration"])) <= split.exploration_end
    assert min(set.union(*windows["selection"])) > split.exploration_end
    assert max(set.union(*windows["selection"])) <= split.selection_end
    assert min(set.union(*windows["final"])) >= split.final_start
    with pytest.raises((ValidationError, AttributeError)):
        split.final_start = T


@pytest.mark.parametrize(
    "timestamps,horizon",
    [
        ((), 1),
        ((T, T), 1),
        ((T + timedelta(days=1), T), 1),
        ((T.replace(tzinfo=None),), 1),
        ((T,), 0),
        ((T,), True),
    ],
)
def test_invalid_splits(timestamps, horizon):
    with pytest.raises(DomainError):
        build_splits(timestamps, horizon)


def test_short_split_has_no_final_origins():
    timestamps = tuple(T + timedelta(days=i) for i in range(8))
    split = build_splits(timestamps, 5)
    assert split.origins_for("final", timestamps) == ()
    assert split.status == "insufficient_evidence"


def test_unmatured_is_not_failure():
    evaluation = evaluate_run(run(), actuals(as_of=GRID[0]), graph())
    assert evaluation.status == "pending"
    assert evaluation.origin_count == 0
    assert evaluation.metrics["model"]["mae"] is None


def test_unreleased_actuals_remain_pending():
    snapshot = Snapshot(
        snapshot_id="late",
        as_of=GRID[-1],
        observations=tuple(
            Observation(
                series_id="s",
                event_time=t,
                available_at=GRID[-1] + timedelta(days=1),
                revision="1",
                value=1,
                unit="count",
            )
            for t in GRID
        ),
        assumptions=(),
    )
    assert evaluate_run(run(), snapshot, graph()).status == "pending"


def test_missing_mature_history_is_insufficient_evidence():
    assert (
        evaluate_run(run(), actuals((None, 4)), graph()).status
        == "insufficient_evidence"
    )


@pytest.mark.parametrize(
    "prediction,want_mae,want_relative", [((2, 4), 0, 0), ((5, 7), 3, 3)]
)
def test_matched_model_and_baseline(prediction, want_mae, want_relative):
    issued = run(prediction)
    before = issued.model_dump_json()
    evaluation = evaluate_run(issued, actuals(), graph())
    assert evaluation.status == "evaluated"
    assert evaluation.origin_count == 1
    assert evaluation.metrics["model"]["mae"] == want_mae
    assert evaluation.metrics["model"]["relative_mae"] == want_relative
    assert evaluation.metrics["model"]["baseline_node_id"] == "baseline"
    assert evaluation.metrics["model"]["count"] == 2
    assert issued.model_dump_json() == before
    assert evaluation.run_id == "issued"


def test_zero_denominator_metric_is_explicit():
    evaluation = evaluate_run(run((3, 3), (2, 2)), actuals((2, 2)), graph())
    assert evaluation.metrics["model"]["relative_mae"] is None
    assert evaluation.metrics["model"]["relative_mae_reason"] == "zero_baseline_mae"


def test_unmatched_baseline_is_not_a_comparison():
    spec = graph()
    spec.nodes[2].config["history"] = "other_source"
    evaluation = evaluate_run(run(), actuals(), spec)
    assert evaluation.metrics["model"]["relative_mae"] is None
    assert evaluation.metrics["model"]["relative_mae_reason"] == "unmatched_baseline"


def test_quantiles_pinball_coverage_and_width():
    issued = run()
    issued.results["model"] = result(
        quantiles={"0.1": ((1, 3),), "0.5": ((2, 4),), "0.9": ((3, 5),)}
    )
    scores = evaluate_run(issued, actuals(), graph()).metrics["model"]
    assert scores["pinball"]["0.1"] == pytest.approx(0.1)
    assert scores["pinball"]["0.5"] == 0
    assert scores["intervals"]["0.1:0.9"] == {"coverage": 1, "width": 2, "level": 0.8}


@pytest.mark.parametrize(
    "quantiles",
    [{"nope": ((1, 1),)}, {"1.2": ((1, 1),)}, {"0.1": ((3, 5),), "0.9": ((1, 3),)}],
)
def test_invalid_quantile_levels_or_crossings(quantiles):
    issued = run()
    issued.results["model"] = result(quantiles=quantiles)
    with pytest.raises(DomainError, match="invalid_quantiles"):
        evaluate_run(issued, actuals(), graph())


def test_events_replay_complete_observed_paths_through_transform():
    issued = run()
    issued.results["total"] = result(
        (3, 7), paths=(((3, 7),),), sample_group_id="draws"
    )
    issued.results["event"] = result(
        (0.25,),
        series_ids=("event:any_exceed",),
        timestamps=(GRID[-1],),
        units=("probability",),
    )
    evaluation = evaluate_run(issued, actuals((2, 3)), graph(event=True))
    # Each observed parent is [2, 3]; their sum is [4, 6], with one strict hit > 5.
    assert evaluation.metrics["event"]["brier"] == 0.5625
    assert evaluation.metrics["event"]["count"] == 1
    assert evaluation.metrics["event"]["observed_outcome"] == 1
    assert (
        evaluate_run(issued, actuals((2, None)), graph(event=True)).metrics["event"][
            "brier"
        ]
        is None
    )


def test_hypothetical_scenario_is_not_scored():
    evaluation = evaluate_run(run(scenario_id="hypothetical"), actuals(), graph())
    assert evaluation.status == "insufficient_evidence"
    assert evaluation.origin_count == 0
    assert evaluation.metrics == {}


def test_graph_identity_must_match_emission():
    spec = graph().model_copy(update={"version": 2})
    with pytest.raises(DomainError, match="graph_identity_mismatch"):
        evaluate_run(run(), actuals(), spec)


def test_revised_actuals_create_new_evaluation(tmp_path):
    issued = run()
    original = actuals()
    revised = actuals((3, 5), revision="2")
    ledger = Ledger(tmp_path / "evaluations.db")
    ledger.append_run(issued, (), "request")
    for snapshot in (original, revised):
        ledger.put_snapshot(snapshot)
    first = evaluate_run(issued, original, graph())
    second = evaluate_run(issued, revised, graph())
    assert first.evaluation_id != second.evaluation_id
    assert evaluate_run(issued, original, graph()) == first
    assert ledger.append_evaluation(first) == first.evaluation_id
    ledger.append_evaluation(second)
    reopened = Ledger(ledger.path)
    assert reopened.get_evaluation(first.evaluation_id).metrics["model"]["mae"] == 0
    assert reopened.get_evaluation(second.evaluation_id).metrics["model"]["mae"] == 1
    assert reopened.get_run("issued") == issued
    assert first.run_id == second.run_id == "issued"
    assert first.actuals_snapshot_id == original.snapshot_id
    assert ledger.append_evaluation(first) == first.evaluation_id
    with pytest.raises(DomainError, match="immutable_identity"):
        ledger.append_evaluation(first.model_copy(update={"status": "pending"}))
    with pytest.raises((TypeError, ValidationError)):
        first.status = "pending"
    with pytest.raises(TypeError):
        first.metrics["model"]["mae"] = 99


def test_evaluation_ledger_requires_existing_evidence(tmp_path):
    ledger = Ledger(tmp_path / "evidence.db")
    with pytest.raises(DomainError, match="missing_evaluation_reference"):
        ledger.append_evaluation(evaluate_run(run(), actuals(), graph()))
    with pytest.raises(DomainError, match="not_found"):
        ledger.get_evaluation("missing")


def test_v1_ledger_migrates_without_changing_runs(tmp_path):
    from importlib.resources import files

    path = tmp_path / "v1.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            files("forecast_anything")
            .joinpath("migrations/001_initial.sql")
            .read_text()
        )
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?)",
            ("issued", "request", run().model_dump_json(), "[]"),
        )
    ledger = Ledger(path)
    snapshot = actuals()
    ledger.put_snapshot(snapshot)
    record = evaluate_run(ledger.get_run("issued"), snapshot, graph())
    ledger.append_evaluation(record)
    assert ledger.get_run("issued") == run()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3


def test_frozen_split_rejects_extended_or_revised_calendar():
    timestamps = tuple(T + timedelta(days=i) for i in range(100))
    split = build_splits(timestamps, 5)
    with pytest.raises(DomainError, match="changed_split_calendar"):
        split.origins_for("final", timestamps + (T + timedelta(days=100),))


def test_latest_visible_revision_is_selected_without_future_vintage_leakage():
    original = actuals()
    revisions = tuple(
        o.model_copy(
            update={
                "revision": "2",
                "available_at": GRID[-1] + timedelta(days=1),
                "value": o.value + 10,
            }
        )
        for o in original.observations
    )
    hidden = Snapshot(
        snapshot_id="hidden",
        as_of=GRID[-1],
        observations=original.observations + revisions,
        assumptions=(),
    )
    visible = hidden.model_copy(
        update={"snapshot_id": "visible", "as_of": GRID[-1] + timedelta(days=1)}
    )
    assert evaluate_run(run(), hidden, graph()).metrics["model"]["mae"] == 0
    assert evaluate_run(run(), visible, graph()).metrics["model"]["mae"] == 10


def test_custom_registered_operator_determines_event_outcome():
    from forecast_anything.operators import register_builtin_operators
    from forecast_anything.operators.events import AnyExceed

    class ComplementEvent(AnyExceed):
        def apply(self, inputs, config):
            answer = super().apply(inputs, config)
            return answer.model_copy(update={"point": ((1 - answer.point[0][0],),)})

    issued = run()
    issued.results["total"] = result(
        (3, 7), paths=(((3, 7),),), sample_group_id="draws"
    )
    issued.results["event"] = result(
        (0.25,),
        series_ids=("event:any_exceed",),
        timestamps=(GRID[-1],),
        units=("probability",),
    )
    operators = register_builtin_operators() | {"any_exceed": ComplementEvent()}
    score = evaluate_run(
        issued, actuals((2, 3)), graph(event=True), operators=operators
    ).metrics["event"]
    assert score["observed_outcome"] == 0
    assert score["brier"] == 0.0625


def test_invalid_registered_event_output_is_rejected():
    from forecast_anything.operators import register_builtin_operators
    from forecast_anything.operators.events import AnyExceed

    class InvalidEvent(AnyExceed):
        def apply(self, inputs, config):
            answer = super().apply(inputs, config)
            return answer.model_copy(
                update={
                    "series_ids": ("a", "b"),
                    "units": ("probability", "probability"),
                    "point": ((0,), (1,)),
                }
            )

    issued = run()
    issued.results["total"] = result(
        (3, 7), paths=(((3, 7),),), sample_group_id="draws"
    )
    issued.results["event"] = result(
        (0.25,),
        series_ids=("event:any_exceed",),
        timestamps=(GRID[-1],),
        units=("probability",),
    )
    with pytest.raises(DomainError, match="invalid_event_outcome"):
        evaluate_run(
            issued,
            actuals((2, 3)),
            graph(event=True),
            operators=register_builtin_operators() | {"any_exceed": InvalidEvent()},
        )


def test_paths_without_point_or_quantile_scores_do_not_claim_evaluated_evidence():
    issued = run(
        results={
            "model": result(point=None, paths=(((1, 2),),), sample_group_id="paths")
        }
    )
    evaluation = evaluate_run(issued, actuals(), graph())
    assert evaluation.status == "insufficient_evidence"
    assert evaluation.origin_count == 0
    assert evaluation.metrics["model"]["reason"] == "no_supported_score_representation"


def test_maturity_uses_absolute_instants_across_dst_fold():
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Rome")
    origin = datetime(2026, 10, 25, 2, tzinfo=zone, fold=0)
    timestamps = (origin.replace(fold=1), datetime(2026, 10, 25, 3, tzinfo=zone))
    issued = run(as_of=origin, results={"model": result(timestamps=timestamps)})
    snapshot = freeze(
        tuple(
            Observation(
                series_id="s",
                event_time=t,
                available_at=t,
                revision="1",
                value=value,
                unit="count",
            )
            for t, value in zip(timestamps, (2, 4))
        ),
        timestamps[-1],
    )
    assert evaluate_run(issued, snapshot, graph()).metrics["model"]["mae"] == 0


def test_unpublished_folded_target_with_utc_forecast_is_pending():
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Rome")
    origin = datetime(2026, 10, 25, 2, tzinfo=zone, fold=0)
    folded_target = origin.replace(fold=1)
    last_target = datetime(2026, 10, 25, 3, tzinfo=zone)
    timestamps = tuple(t.astimezone(timezone.utc) for t in (folded_target, last_target))
    issued = run(as_of=origin, results={"model": result(timestamps=timestamps)})
    snapshot = Snapshot(
        snapshot_id="unpublished-folded-target",
        as_of=last_target,
        observations=(
            Observation(
                series_id="s",
                event_time=folded_target,
                available_at=last_target + timedelta(days=1),
                revision="1",
                value=2,
                unit="count",
            ),
            Observation(
                series_id="s",
                event_time=last_target,
                available_at=last_target,
                revision="1",
                value=4,
                unit="count",
            ),
        ),
        assumptions=(),
    )
    evaluation = evaluate_run(issued, snapshot, graph())
    assert evaluation.status == "pending"
    assert evaluation.metrics["model"]["status"] == "pending"
    assert evaluation.origin_count == 0
