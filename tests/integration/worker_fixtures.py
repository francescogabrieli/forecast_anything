"""Fixtures for worker execution and watch lifecycle tests."""

from datetime import UTC, datetime, timedelta

from forecast_anything.contracts import GraphSpec, Node, Observation
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze

T = datetime(2026, 10, 24, tzinfo=UTC)


class CountingProvider(SeasonalNaiveProvider):
    def __init__(self):
        super().__init__(1)
        self.calls = []
        self.fail = False

    def forecast(self, request):
        self.calls.append(request.snapshot.observations[0].series_id)
        if self.fail:
            raise RuntimeError("offline")
        return super().forecast(request)


def inputs():
    nodes, snapshots = [], {}
    for source in ("a", "b"):
        snapshots[source] = freeze(
            tuple(
                Observation(
                    series_id=source,
                    event_time=T - timedelta(hours=3 - i),
                    available_at=T,
                    revision="1",
                    value=i + 1,
                    unit="count",
                )
                for i in range(3)
            ),
            T,
        )
        nodes.extend(
            (
                Node(
                    node_id=source,
                    kind="source",
                    inputs=(),
                    config={
                        "source_id": source,
                        "series_ids": [source],
                        "units": ["count"],
                        "frequency": "1h",
                    },
                ),
                Node(
                    node_id=f"f_{source}",
                    kind="forecast",
                    inputs=(source,),
                    config={
                        "provider": "seasonal_naive",
                        "history": source,
                        "horizon": 1,
                        "frequency": "1h",
                        "options": {"period": 1},
                        "relation_type": {source: "statistical"},
                    },
                ),
            )
        )
    return GraphSpec(graph_id="two-branches", version=1, nodes=tuple(nodes)), snapshots


def setup(tmp_path, clock=None):
    ledger = Ledger(tmp_path / "state.db", clock=clock or (lambda: T))
    provider = CountingProvider()
    return (
        ledger,
        provider,
        Runtime(ledger, {"seasonal_naive": provider}, {}, clock or (lambda: T)),
    )


def payload():
    graph, snapshots = inputs()
    return {
        "kind": "run",
        "graph": graph.model_dump(mode="json"),
        "snapshots": {k: v.model_dump(mode="json") for k, v in snapshots.items()},
        "as_of": T.isoformat(),
    }


def registered_watch(
    tmp_path, ledger, due=T, templates=("forecast_change",), final_origins=()
):
    from forecast_anything.contracts import DiscoveryBudget, DiscoveryEpoch, SourceSpec
    from forecast_anything.discovery.candidates import (
        CandidateProposal,
        compile_proposal,
    )
    from forecast_anything.sources.catalog import SourceCatalog
    from forecast_anything.sources.profiling import ingest_source, inspect_source
    from forecast_anything.watches import create_watch

    csv = tmp_path / "sales.csv"
    csv.write_text("time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n")
    spec = SourceSpec(
        source_id="sales",
        kind="csv",
        location=str(csv),
        refresh_seconds=120,
        mapping={
            "event_time": "time",
            "available_at": "time",
            "value": "value",
            **{
                k: {"constant": v}
                for k, v in {
                    "series_id": "sales",
                    "unit": "count",
                    "revision": "1",
                    "frequency": "D",
                    "calendar": "gregorian",
                    "timezone": "UTC",
                    "missing_values": [],
                }.items()
            },
        },
    )
    registered = SourceCatalog(ledger.path).append(spec)
    snap = ingest_source(spec, T)
    ledger.put_snapshot(snap)
    candidates = tuple(
        compile_proposal(
            CandidateProposal(
                template_id=template, source_ids=("sales",), reason="Review"
            ),
            (inspect_source(spec),),
            epoch_id="original",
        )
        for template in templates
    )
    ledger.put_discovery_epoch(
        DiscoveryEpoch(
            epoch_id="original",
            source_snapshot_ids=(snap.snapshot_id,),
            explored_candidate_ids=tuple(c.candidate_id for c in candidates),
            final_origin_ids=final_origins,
            final_candidate_id=candidates[0].candidate_id if final_origins else None,
        ),
        DiscoveryBudget(max_candidates=len(candidates), max_tool_calls=3),
    )
    for index, c in enumerate(candidates):
        ledger.register_candidate(c)
        ledger.put_watch(
            create_watch(
                c, watch_id="watch" if index == 0 else f"watch-{index}", next_due_at=due
            ),
            now=T - timedelta(days=1),
        )
    return csv, registered


def _provisional_requalification_case(tmp_path, *, appended_days, qualified=True):
    from forecast_anything.contracts import (
        QuestionCreateRequest,
        QuestionReferenceRequest,
    )
    from forecast_anything.operators import register_builtin_operators
    from forecast_anything.sources.catalog import SourceCatalog
    from forecast_anything.sources.profiling import ingest_source

    ledger, _, runtime = setup(tmp_path)
    runtime.operators = register_builtin_operators()
    if qualified:
        qualify_watch(tmp_path, ledger)
    else:
        registered_watch(tmp_path, ledger)
    question = ledger.create_question(
        QuestionCreateRequest(
            key=f"requalification-{appended_days}",
            title="Sales outlook",
            meaning="Forecast daily sales",
            source_ids=("sales",),
            selection={"provider": "seasonal_naive", "horizon": 1},
        )
    )
    ledger.link_question_reference(
        question.question_id,
        QuestionReferenceRequest(
            key="watch-link",
            revision=1,
            target_type="watch",
            target_id="watch",
        ),
    )
    registered = SourceCatalog(ledger.path).get("sales")
    csv = tmp_path / "sales.csv"
    base = T - timedelta(days=3)
    values = [1, 2, 3] + [2 if index % 2 else 5 for index in range(3, appended_days)]
    csv.write_text(
        "time,value\n"
        + "".join(
            f"{(base + timedelta(days=index)).date().isoformat()},{value}\n"
            for index, value in enumerate(values)
        )
    )
    now = T + timedelta(days=appended_days)
    snapshot = ingest_source(registered.spec, now)
    ledger.put_snapshot(snapshot)
    ledger.advance_watch(
        "watch",
        {
            "kind": "data_appended",
            "source_id": "sales",
            "snapshot_id": snapshot.snapshot_id,
            "next_due_at": now + timedelta(days=1),
            "requalification_due_at": now,
        },
        now,
        event_id=f"test-append/{snapshot.snapshot_id}",
    )
    return ledger, runtime, question, now


def qualify_watch(tmp_path, ledger):
    from forecast_anything.contracts import (
        EvaluationContext,
        ForecastResult,
        RunRecord,
        Snapshot,
    )
    from forecast_anything.discovery.policy import assess_candidate
    from forecast_anything.evaluation.records import evaluate_run

    registered_watch(
        tmp_path, ledger, final_origins=tuple(f"day-{i}" for i in range(30))
    )
    watch = ledger.get_watch("watch")
    candidate = watch.candidate
    epoch = ledger.get_discovery_epoch("original")
    records = []
    for i, origin in enumerate(epoch.final_origin_ids):
        target = T + timedelta(days=i + 1)
        result = ForecastResult(
            series_ids=("sales",),
            timestamps=(target,),
            units=("count",),
            point=((1,),),
            provider_id="scripted",
            provider_revision="v1",
            quantiles=None,
            paths=None,
            sample_group_id=None,
            assumptions=(),
        )
        run = RunRecord(
            run_id=f"qualified-{i}",
            graph_id=candidate.graph.graph_id,
            graph_version=1,
            as_of=T,
            snapshot_ids=epoch.source_snapshot_ids,
            requested_provider={},
            actual_provider={},
            state="completed",
            results={
                "forecast": result,
                "question": result,
                "reference": result.model_copy(update={"point": ((2,),)}),
            },
            evidence_ids=(),
            scenario_id=None,
            parent_run_id=None,
        )
        ledger.append_run(run, (), run.run_id)
        actuals = Snapshot(
            snapshot_id=f"actuals-{i}",
            as_of=target,
            assumptions=(),
            observations=(
                Observation(
                    series_id="sales",
                    event_time=target,
                    available_at=target,
                    revision="1",
                    value=1,
                    unit="count",
                ),
            ),
        )
        ledger.put_snapshot(actuals)
        record = evaluate_run(run, actuals, candidate.graph).model_copy(
            update={
                "discovery": EvaluationContext(
                    candidate_id=candidate.candidate_id,
                    protocol_id=candidate.protocol_id,
                    epoch_id="original",
                    origin_id=origin,
                    partition="final",
                    source_snapshot_ids=epoch.source_snapshot_ids,
                    target_start=target,
                    target_end=target,
                    temporal_valid=True,
                    semantic_valid=True,
                )
            }
        )
        ledger.append_evaluation(record)
        records.append(record)
    decision = assess_candidate(candidate, tuple(records), epoch)
    assert decision.action == "activate"
    ledger.append_eligibility_decision(candidate.candidate_id, decision)
    ledger.advance_watch(
        "watch",
        {
            "kind": "evidence_qualified",
            "decision": decision,
            "next_due_at": T + timedelta(days=1),
        },
        T,
        event_id="qualification",
    )
    return decision
