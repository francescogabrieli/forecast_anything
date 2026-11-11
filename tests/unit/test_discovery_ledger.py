"""Durable discovery epochs, budgets and evaluation provenance."""

from datetime import UTC, datetime, timedelta

import pytest
from discovery_fixtures import (
    candidate,
    epoch_for,
    evidence_for,
    profile,
)

from forecast_anything.contracts import (
    DiscoveryBudget,
    DomainError,
    EvaluationContext,
)
from forecast_anything.discovery.candidates import (
    CandidateProposal,
    compile_proposal,
    propose_candidates,
)
from forecast_anything.discovery.policy import (
    assess_candidate,
)
from forecast_anything.store import Ledger


def stored_origin_evaluation(ledger, c, epoch, origin_id, partition):
    """Real stored emission/actuals so reservation tests reach persistence."""
    from forecast_anything.contracts import (
        ForecastResult,
        Observation,
        RunRecord,
        Snapshot,
    )
    from forecast_anything.evaluation.records import evaluate_run

    issued_at = datetime(2026, 1, 2, tzinfo=UTC)
    target = issued_at + timedelta(days=1)
    forecast = ForecastResult(
        provider_id="seasonal_naive",
        provider_revision="1",
        series_ids=("sales",),
        timestamps=(target,),
        units=("count",),
        point=((1.0,),),
        quantiles=None,
        paths=None,
        sample_group_id=None,
        assumptions=(),
    )
    issued = RunRecord(
        run_id=f"run:{c.candidate_id}",
        graph_id=c.graph.graph_id,
        graph_version=1,
        as_of=issued_at,
        snapshot_ids=epoch.source_snapshot_ids,
        requested_provider={
            "forecast": "seasonal_naive",
            "reference": "seasonal_naive",
        },
        actual_provider={"forecast": "seasonal_naive", "reference": "seasonal_naive"},
        state="succeeded",
        results={
            "forecast": forecast,
            "reference": forecast,
            "question": forecast.model_copy(
                update={"provider_id": "operator:sum_aligned"}
            ),
        },
        evidence_ids=(),
        scenario_id=None,
        parent_run_id=None,
    )
    ledger.append_run(issued, (), f"request:{c.candidate_id}")
    actuals = Snapshot(
        snapshot_id=f"actuals:{c.candidate_id}",
        as_of=target,
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
        assumptions=(),
    )
    ledger.put_snapshot(actuals)
    record = evaluate_run(issued, actuals, c.graph)
    return record.model_copy(
        update={
            "discovery": EvaluationContext(
                candidate_id=c.candidate_id,
                protocol_id=c.protocol_id,
                epoch_id=epoch.epoch_id,
                origin_id=origin_id,
                partition=partition,
                source_snapshot_ids=epoch.source_snapshot_ids,
                target_start=target,
                target_end=target,
                temporal_valid=True,
                semantic_valid=True,
            )
        }
    )


def start_epoch(ledger, epoch, budget):
    from forecast_anything.contracts import Snapshot

    for snapshot_id in epoch.source_snapshot_ids:
        try:
            ledger.get_snapshot(snapshot_id)
        except DomainError as error:
            if error.code != "not_found":
                raise
            ledger.put_snapshot(
                Snapshot(
                    snapshot_id=snapshot_id,
                    as_of=datetime(2026, 1, 1, tzinfo=UTC),
                    observations=(),
                    assumptions=("epoch persistence fixture",),
                )
            )
    return Ledger.put_discovery_epoch(ledger, epoch, budget)


def test_holdout_cannot_be_reused_for_tuning(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate()
    first = epoch_for(c)
    start_epoch(ledger, first, DiscoveryBudget())
    ledger = Ledger(ledger.path)
    second = epoch_for(
        c,
        epoch_id="new-config",
        final_origin_ids=(),
        final_candidate_id=None,
        tuning_origin_ids=("origin-0",),
    )
    with pytest.raises(DomainError, match="holdout_reuse"):
        start_epoch(ledger, second, DiscoveryBudget())
    with pytest.raises(DomainError, match="holdout_reuse"):
        start_epoch(
            ledger,
            first.model_copy(update={"epoch_id": "new-final"}),
            DiscoveryBudget(),
        )

    # A second epoch cannot bypass the reservation by omitting its tuning
    # declaration and attaching the reserved origin to a persisted evaluation.
    other = compile_proposal(
        CandidateProposal(
            template_id="forecast_change", source_ids=("sales",), reason="retune"
        ),
        (profile(),),
        epoch_id="other-epoch",
    )
    other_epoch = epoch_for(other, final_origin_ids=(), final_candidate_id=None)
    start_epoch(ledger, other_epoch, DiscoveryBudget())
    ledger.register_candidate(other)
    for partition in ("exploration", "selection"):
        record = stored_origin_evaluation(
            ledger, other, other_epoch, "origin-0", partition
        )
        with pytest.raises(DomainError, match="holdout_reuse"):
            ledger.append_evaluation(record)
        with pytest.raises(DomainError, match="not_found"):
            ledger.get_evaluation(record.evaluation_id)


def test_rejected_candidate_is_preserved(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate("unknown")
    epoch = epoch_for(c)
    start_epoch(ledger, epoch, DiscoveryBudget())
    ledger.register_candidate(c)
    decision = assess_candidate(c, (), epoch)
    ledger.append_eligibility_decision(c.candidate_id, decision)
    reopened = Ledger(ledger.path)
    assert reopened.get_candidate(c.candidate_id) == c
    assert reopened.eligibility_decisions(c.candidate_id) == (decision,)
    assert reopened.get_discovery_epoch(epoch.epoch_id) == epoch


def test_budget_is_enforced_outside_agent(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate()
    other = candidate("expected_deviation")
    epoch = epoch_for(c, explored_candidate_ids=(c.candidate_id, other.candidate_id))
    start_epoch(ledger, epoch, DiscoveryBudget(max_candidates=1, max_tool_calls=1))
    ledger.register_candidate(c)
    ledger.register_candidate(c)  # retries do not consume candidate budget twice
    ledger.consume_discovery_tool_call(epoch.epoch_id, "call-1")
    reopened = Ledger(ledger.path)
    reopened.consume_discovery_tool_call(epoch.epoch_id, "call-1")
    with pytest.raises(DomainError, match="discovery_budget_exhausted"):
        reopened.consume_discovery_tool_call(epoch.epoch_id, "call-2")
    with pytest.raises(DomainError, match="discovery_budget_exhausted"):
        reopened.register_candidate(other)
    assert reopened.discovery_usage(epoch.epoch_id) == (1, 1)
    assert len(propose_candidates((profile(),), DiscoveryBudget(max_candidates=1))) == 1
    assert propose_candidates((profile(),), DiscoveryBudget(max_candidates=0)) == ()


def test_store_recomputes_eligibility_instead_of_trusting_activate(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate("unknown")
    epoch = epoch_for(c)
    start_epoch(ledger, epoch, DiscoveryBudget())
    ledger.register_candidate(c)
    forged = assess_candidate(c, (), epoch).model_copy(update={"action": "activate"})
    with pytest.raises(DomainError, match="invalid_eligibility_decision"):
        ledger.append_eligibility_decision(c.candidate_id, forged)
    assert ledger.eligibility_decisions(c.candidate_id) == ()


def test_baseline_replay_qualifies_frozen_synthetic_question(tmp_path):
    from forecast_anything.contracts import Observation, Snapshot
    from forecast_anything.evaluation.records import evaluate_run
    from forecast_anything.operators import register_builtin_operators
    from forecast_anything.providers.baseline import SeasonalNaiveProvider
    from forecast_anything.runtime import Runtime
    from forecast_anything.temporal import freeze

    ledger = Ledger(tmp_path / "replay.db")
    c = candidate()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    # Frozen alternating process: period 2 is exact, last-value reference misses
    # by 2 every day. It proves question utility using only a baseline provider.
    observations = tuple(
        Observation(
            series_id="sales",
            event_time=start + timedelta(days=i),
            available_at=start + timedelta(days=i),
            revision="1",
            value=1 if i % 2 == 0 else 3,
            unit="count",
        )
        for i in range(32)
    )
    histories = tuple(
        freeze(observations[:i], start + timedelta(days=i - 1)) for i in range(2, 32)
    )
    epoch = epoch_for(c, source_snapshot_ids=tuple(s.snapshot_id for s in histories))
    for history in histories:
        ledger.put_snapshot(history)
    start_epoch(ledger, epoch, DiscoveryBudget())
    ledger.register_candidate(c)
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(2)},
        register_builtin_operators(),
        clock=lambda: start,
    )
    records = []
    for i, history in enumerate(histories):
        issued = runtime.run(c.graph, {"sales": history}, history.as_of, f"issue-{i}")
        actual = Snapshot(
            snapshot_id=f"actual-{i}",
            as_of=observations[i + 2].available_at,
            observations=(observations[i + 2],),
            assumptions=(),
        )
        ledger.put_snapshot(actual)
        record = evaluate_run(issued, actual, c.graph)
        assert record.metrics["question"]["mae"] == 0
        assert record.metrics["reference"]["mae"] == 2
        record = record.model_copy(
            update={
                "discovery": EvaluationContext(
                    candidate_id=c.candidate_id,
                    protocol_id=c.protocol_id,
                    epoch_id=epoch.epoch_id,
                    origin_id=epoch.final_origin_ids[i],
                    partition="final",
                    source_snapshot_ids=epoch.source_snapshot_ids,
                    target_start=observations[i + 2].event_time,
                    target_end=observations[i + 2].event_time,
                    temporal_valid=True,
                    semantic_valid=True,
                )
            }
        )
        ledger.append_evaluation(record)
        records.append(record)
    decision = assess_candidate(c, tuple(records), epoch)
    assert decision.action == "activate"
    ledger.append_eligibility_decision(c.candidate_id, decision)
    reopened = Ledger(ledger.path)
    assert reopened.eligibility_decisions(c.candidate_id) == (decision,)


def test_epoch_budget_is_immutable_after_restart(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate()
    epoch = epoch_for(c)
    start_epoch(ledger, epoch, DiscoveryBudget(max_candidates=1))
    with pytest.raises(DomainError, match="immutable_identity"):
        Ledger(ledger.path).put_discovery_epoch(
            epoch, DiscoveryBudget(max_candidates=100)
        )
    assert ledger.discovery_usage(epoch.epoch_id) == (0, 0)


def test_epoch_requires_existing_source_snapshot_provenance(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate()
    with pytest.raises(DomainError, match="missing_discovery_snapshot"):
        ledger.put_discovery_epoch(epoch_for(c), DiscoveryBudget())


def test_stored_discovery_evidence_is_bound_to_issued_run_and_actuals(tmp_path):
    from forecast_anything.contracts import RunRecord, Snapshot

    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate()
    epoch = epoch_for(c)
    start_epoch(ledger, epoch, DiscoveryBudget())
    ledger.register_candidate(c)
    record = evidence_for(c, epoch)[0]
    issued = RunRecord(
        run_id=record.run_id,
        graph_id=c.graph.graph_id,
        graph_version=1,
        as_of=datetime(2025, 12, 31, tzinfo=UTC),
        snapshot_ids=epoch.source_snapshot_ids,
        requested_provider={},
        actual_provider={},
        state="completed",
        results={},
        evidence_ids=(),
        scenario_id=None,
        parent_run_id=None,
    )
    ledger.append_run(issued, (), "issued")
    ledger.put_snapshot(
        Snapshot(
            snapshot_id=record.actuals_snapshot_id,
            as_of=datetime(2026, 1, 2, tzinfo=UTC),
            observations=(),
            assumptions=(),
        )
    )
    # An evaluated score cannot be attached to an empty issued result, even with
    # real run/snapshot foreign keys and plausible candidate lineage.
    with pytest.raises(DomainError, match="invalid_discovery_evidence"):
        ledger.append_evaluation(record)


@pytest.mark.parametrize("partition", ["exploration", "selection"])
def test_persisted_tuning_evaluation_requires_declared_origin(tmp_path, partition):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate()
    epoch = epoch_for(c, tuning_origin_ids=("tuning-1",))
    start_epoch(ledger, epoch, DiscoveryBudget())
    ledger.register_candidate(c)
    undeclared = stored_origin_evaluation(ledger, c, epoch, "undeclared", partition)
    with pytest.raises(DomainError, match="unreserved_discovery_origin"):
        ledger.append_evaluation(undeclared)
    declared = undeclared.model_copy(
        update={
            "discovery": undeclared.discovery.model_copy(
                update={"origin_id": "tuning-1"}
            )
        }
    )
    ledger.append_evaluation(declared)
    assert Ledger(ledger.path).get_evaluation(declared.evaluation_id) == declared


def test_persisted_final_evaluation_requires_frozen_final_origin(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate()
    epoch = epoch_for(c, tuning_origin_ids=("tuning-1",))
    start_epoch(ledger, epoch, DiscoveryBudget())
    ledger.register_candidate(c)
    unreserved = stored_origin_evaluation(ledger, c, epoch, "tuning-1", "final")
    with pytest.raises(DomainError, match="unreserved_discovery_origin"):
        ledger.append_evaluation(unreserved)
    reserved = unreserved.model_copy(
        update={
            "discovery": unreserved.discovery.model_copy(
                update={"origin_id": "origin-0"}
            )
        }
    )
    ledger.append_evaluation(reserved)
    assert Ledger(ledger.path).get_evaluation(reserved.evaluation_id) == reserved


@pytest.mark.parametrize(
    "template", ["expected_deviation", "forecast_change", "unknown", "declared_limit"]
)
def test_compiler_cost_estimates_survive_ledger_roundtrip(tmp_path, template):
    source = profile(
        proposed_mapping={
            **profile().proposed_mapping,
            "operational_limit": {"constant": 12},
        }
    )
    c = candidate(template, source)
    ledger = Ledger(tmp_path / "ledger.db")
    start_epoch(ledger, epoch_for(c), DiscoveryBudget())
    ledger.register_candidate(c)
    restored = Ledger(ledger.path).get_candidate(c.candidate_id)
    if template in {"expected_deviation", "forecast_change"}:
        assert restored.estimated_cost.status == "known"
        assert restored.estimated_cost.value == 2
        assert restored.estimated_cost.unit == "provider_calls_per_run"
    else:
        assert restored.estimated_cost.status == "unavailable"
        assert restored.estimated_cost.value is None
        assert restored.estimated_cost.basis == "unsupported_proposal"
    assert restored.estimated_cost == c.estimated_cost


def test_candidate_cannot_override_trusted_compiler_cost(tmp_path):
    ledger = Ledger(tmp_path / "ledger.db")
    c = candidate()
    start_epoch(ledger, epoch_for(c), DiscoveryBudget())
    forged = c.model_copy(
        update={"estimated_cost": c.estimated_cost.model_copy(update={"value": 0})}
    )
    with pytest.raises(DomainError, match="candidate_identity_mismatch"):
        ledger.register_candidate(forged)
