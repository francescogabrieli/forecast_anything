"""Discovery boundaries: no invented semantics, selection leakage or agent trust."""

from datetime import datetime, timedelta, timezone

import pytest

from forecast_anything.contracts import (
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EvaluationContext,
    EvaluationRecord,
    SourceField,
    SourceProfile,
    SourceSpec,
)
from forecast_anything.discovery.candidates import (
    CandidateProposal,
    compile_proposal,
    graph_support,
    propose_candidates,
    validate_candidate,
)
from forecast_anything.discovery.policy import (
    assess_candidate,
    candidate_backtest_selection,
)
from forecast_anything.sources.profiling import inspect_source
from forecast_anything.store import Ledger


def profile(**changes):
    return SourceProfile.model_validate(
        dict(
            source_id="sales",
            source_revision="mapping-v1",
            fields={"date": SourceField(data_type="datetime", nullable=False)},
            proposed_mapping={
                "series_id": {"constant": "sales"},
                "unit": {"constant": "count"},
                "event_time": "date",
                "available_at": "date",
                "revision": {"constant": "1"},
                "value": {"constant": 1},
                "frequency": {"constant": "D"},
                "timezone": {"constant": "UTC"},
                "calendar": {"constant": "gregorian"},
                "missing_values": {"constant": []},
            },
            unresolved=(),
            assumptions=(),
            sample_rows=({"date": "2026-01-01"},),
        )
        | changes
    )


def candidate(template="forecast_change", source=None):
    return compile_proposal(
        CandidateProposal(template_id=template, source_ids=("sales",), reason="Review"),
        (source or profile(),),
        epoch_id="epoch-1",
    )


def epoch_for(c, count=30, **changes):
    return DiscoveryEpoch.model_validate(
        dict(
            epoch_id=c.epoch_id,
            source_snapshot_ids=("snapshot-1",),
            explored_candidate_ids=(c.candidate_id,),
            final_origin_ids=tuple(f"origin-{i}" for i in range(count)),
            final_candidate_id=c.candidate_id,
        )
        | changes
    )


def evidence_for(c, epoch, loss=1.0, reference=2.0, **context_changes):
    # Frozen scripted final suite: one complete, disjoint daily target per origin.
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        EvaluationRecord(
            evaluation_id=f"evaluation-{i}",
            run_id=f"run-{i}",
            actuals_snapshot_id=f"actuals-{i}",
            status="evaluated",
            origin_count=1,
            metrics={
                "question": {"status": "evaluated", "mae": loss, "count": 1},
                "reference": {"status": "evaluated", "mae": reference, "count": 1},
            },
            assumptions=("frozen synthetic fixture; scripted baseline evidence",),
            discovery=EvaluationContext.model_validate(
                dict(
                    candidate_id=c.candidate_id,
                    protocol_id=c.protocol_id,
                    epoch_id=epoch.epoch_id,
                    origin_id=origin,
                    partition="final",
                    source_snapshot_ids=epoch.source_snapshot_ids,
                    target_start=start + timedelta(days=i),
                    target_end=start + timedelta(days=i),
                    temporal_valid=True,
                    semantic_valid=True,
                )
                | context_changes
            ),
        )
        for i, origin in enumerate(epoch.final_origin_ids)
    )


def stored_origin_evaluation(ledger, c, epoch, origin_id, partition):
    """Real stored emission/actuals so reservation tests reach persistence."""
    from forecast_anything.contracts import (
        ForecastResult,
        Observation,
        RunRecord,
        Snapshot,
    )
    from forecast_anything.evaluation.records import evaluate_run

    issued_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
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
                    as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    observations=(),
                    assumptions=("epoch persistence fixture",),
                )
            )
    return Ledger.put_discovery_epoch(ledger, epoch, budget)


def test_discovery_without_sources_proposes_nothing():
    assert propose_candidates((), DiscoveryBudget()) == ()


def test_timestral_candidate_preserves_baseline_comparator_and_exact_replay():
    c = compile_proposal(
        CandidateProposal(
            template_id="forecast_change", source_ids=("sales",), reason="Review"
        ),
        (profile(),),
        epoch_id="epoch-1",
        forecast_provider="timestral",
    )
    nodes = {node.node_id: node for node in c.graph.nodes}
    assert c.executable
    assert nodes["forecast"].config["provider"] == "timestral"
    assert nodes["forecast"].config["options"] == {}
    assert nodes["forecast"].config["horizon"] == 1
    assert nodes["reference"].config["provider"] == "seasonal_naive"
    assert nodes["reference"].config["options"] == {"period": 1}
    assert validate_candidate(c) == ()
    selection = candidate_backtest_selection(c)
    assert selection.provider == "timestral"
    assert selection.options == {}
    assert selection.baseline_period == 1
    assert c.candidate_id != candidate().candidate_id
    assert c.graph.graph_id != candidate().graph.graph_id


def test_deterministic_proposals_use_explicit_forecast_provider():
    proposed = propose_candidates(
        (profile(),), DiscoveryBudget(), forecast_provider="timestral"
    )
    assert len(proposed) == 2
    assert all(c.executable and validate_candidate(c) == () for c in proposed)
    assert all(
        next(n for n in c.graph.nodes if n.node_id == "forecast").config["provider"]
        == "timestral"
        for c in proposed
    )


def test_deterministic_epoch_changes_with_provider_preserving_legacy_epoch():
    profiles = (profile(),)
    legacy = propose_candidates(profiles, DiscoveryBudget())
    model = propose_candidates(
        profiles, DiscoveryBudget(), forecast_provider="timestral"
    )
    assert {c.epoch_id for c in legacy} == {
        "0658b1ff32516117403a7f41b5ac36fda235df2fa1065e11ef41e727ea4e3689"
    }
    assert len({c.epoch_id for c in model}) == 1
    assert model[0].epoch_id != legacy[0].epoch_id


def test_proposals_reject_unregistered_primary_provider():
    with pytest.raises(DomainError, match="unknown_provider"):
        compile_proposal(
            CandidateProposal(
                template_id="forecast_change", source_ids=("sales",), reason="Review"
            ),
            (profile(),),
            epoch_id="epoch-1",
            forecast_provider="untrusted",
        )


def test_trusted_timestral_graph_support_never_loads_weights(monkeypatch):
    from forecast_anything.providers.timestral import TimestralProvider

    def forbidden_load(self):
        pytest.fail("discovery compilation must not load model weights")

    monkeypatch.setattr(TimestralProvider, "_load", forbidden_load)
    c = candidate()
    graph = c.graph.model_copy(
        update={
            "nodes": tuple(
                node.model_copy(
                    update={
                        "config": {
                            **node.config,
                            "provider": "timestral",
                            "options": {},
                        }
                    }
                )
                if node.node_id == "forecast"
                else node
                for node in c.graph.nodes
            )
        }
    )
    assert graph_support(graph) == ()


def test_legacy_baseline_candidate_keeps_original_identity_and_replay():
    c = candidate()
    assert (
        c.candidate_id
        == "5740f86f63864d4312ce7ff49b3246715b87a6569df42359fdffbf11d38f8fc5"
    )
    assert (
        c.protocol_id
        == "ae470041d266b45386da404ca609388f420997c688919066e1f1556923593686"
    )
    assert (
        c.graph.graph_id
        == "ca3a5e9f1def036197b779037816b811f5d6ea0281811b3faf6323180daa7d12"
    )
    assert validate_candidate(c) == ()
    selection = candidate_backtest_selection(c)
    assert selection.provider == "seasonal_naive"
    assert selection.options == {"period": 2}
    assert selection.baseline_period == 1


@pytest.mark.parametrize("provider", ["untrusted", None, [], {}])
def test_candidate_rejects_unknown_primary_provider_spoof(provider):
    c = candidate()
    forged = c.model_copy(
        update={
            "graph": c.graph.model_copy(
                update={
                    "nodes": tuple(
                        node.model_copy(
                            update={"config": {**node.config, "provider": provider}}
                        )
                        if node.node_id == "forecast"
                        else node
                        for node in c.graph.nodes
                    )
                }
            )
        }
    )
    assert validate_candidate(forged) == ("candidate_identity_mismatch",)
    with pytest.raises(ValueError, match="unsupported_watch_backtest_candidate"):
        candidate_backtest_selection(forged)


def test_no_undeclared_operational_limit():
    proposed = propose_candidates((profile(),), DiscoveryBudget())
    assert {c.template_id for c in proposed} == {
        "expected_deviation",
        "forecast_change",
    }
    limited = profile(
        proposed_mapping={
            **profile().proposed_mapping,
            "operational_limit": {"constant": 12},
        }
    )
    proposed = propose_candidates((limited,), DiscoveryBudget())
    limit = next(c for c in proposed if c.template_id == "declared_limit")
    assert limit.graph.nodes[-1].config["parameters"]["threshold"] == 12
    assert (
        "unsupported_representation"
        in assess_candidate(limit, (), epoch_for(limit)).reason_codes
    )


def test_profile_preserves_explicit_semantics_without_inferring(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text("date,value\n2026-01-01,1\n")
    mapping = profile().proposed_mapping
    spec = SourceSpec(
        source_id="sales",
        kind="csv",
        location=str(path),
        mapping=mapping,
        refresh_seconds=60,
    )
    utc = inspect_source(spec)
    local = inspect_source(
        spec.model_copy(
            update={
                "mapping": {
                    **mapping,
                    "timezone": {"constant": "Europe/Rome"},
                    "frequency": {"constant": "H"},
                }
            }
        )
    )
    assert utc.proposed_mapping["frequency"] == {"constant": "D"}
    assert local.proposed_mapping["frequency"] == {"constant": "H"}
    assert utc.proposed_mapping["timezone"] != local.proposed_mapping["timezone"]
    assert utc.source_revision != local.source_revision
    unresolved = inspect_source(
        spec.model_copy(
            update={"mapping": {k: v for k, v in mapping.items() if k != "timezone"}}
        )
    )
    assert "timezone" in unresolved.unresolved
    assert "timezone" not in unresolved.proposed_mapping
    assert all(
        not c.executable for c in propose_candidates((unresolved,), DiscoveryBudget())
    )


def test_canonical_identity_ignores_agent_reason_and_samples():
    first = candidate()
    changed = compile_proposal(
        CandidateProposal(
            template_id="forecast_change",
            source_ids=("sales",),
            reason="different wording",
        ),
        (profile(sample_rows=()),),
        epoch_id="epoch-1",
    )
    assert first.candidate_id == changed.candidate_id
    assert first.protocol_id == changed.protocol_id
    revised = candidate(source=profile(source_revision="mapping-v2"))
    assert first.candidate_id != revised.candidate_id


def test_agent_free_form_and_forged_graph_are_non_executable():
    c = candidate("invented question")
    assert not c.executable
    assert assess_candidate(c, (), epoch_for(c)).action == "reject"
    valid = candidate()
    graph = valid.graph.model_copy(update={"nodes": valid.graph.nodes[:-1]})
    forged = valid.model_copy(update={"graph": graph})
    decision = assess_candidate(forged, (), epoch_for(valid))
    assert decision.action == "reject"
    assert "candidate_identity_mismatch" in decision.reason_codes


def test_noise_candidate_is_not_promoted():
    c = candidate()
    epoch = epoch_for(c)
    decision = assess_candidate(c, evidence_for(c, epoch, loss=2.0), epoch)
    assert decision.action == "reject"
    assert "nonpositive_final_skill" in decision.reason_codes


def test_baseline_evidence_can_qualify_question():
    c = candidate()
    epoch = epoch_for(c)
    decision = assess_candidate(c, evidence_for(c, epoch), epoch)
    assert decision.action == "activate"
    assert (decision.candidate_id, decision.protocol_id, decision.epoch_id) == (
        c.candidate_id,
        c.protocol_id,
        c.epoch_id,
    )


@pytest.mark.parametrize("count", [0, 1, 29])
def test_requires_thirty_distinct_final_origins(count):
    c = candidate()
    epoch = epoch_for(c, count)
    assert assess_candidate(c, evidence_for(c, epoch), epoch).action == "provisional"


def test_duplicate_revised_origin_does_not_inflate_evidence():
    c = candidate()
    epoch = epoch_for(c, 29)
    records = evidence_for(c, epoch)
    revised = records[-1].model_copy(
        update={"evaluation_id": "revision", "actuals_snapshot_id": "revised"}
    )
    assert assess_candidate(c, records + (revised,), epoch).action != "activate"


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"temporal_valid": False}, "temporal_violation"),
        ({"semantic_valid": False}, "semantic_violation"),
        ({"protocol_id": "other"}, "evidence_lineage_mismatch"),
        ({"source_snapshot_ids": ("other",)}, "evidence_lineage_mismatch"),
        ({"partition": "exploration"}, "nonfinal_evidence"),
    ],
)
def test_invalid_evidence_cannot_activate(change, reason):
    c = candidate()
    epoch = epoch_for(c)
    decision = assess_candidate(c, evidence_for(c, epoch, **change), epoch)
    assert decision.action != "activate"
    assert reason in decision.reason_codes


def test_overlapping_final_windows_do_not_qualify():
    c = candidate()
    epoch = epoch_for(c)
    records = evidence_for(c, epoch)
    context = records[1].discovery.model_copy(
        update={"target_start": records[0].discovery.target_start}
    )
    records = (
        records[0],
        records[1].model_copy(update={"discovery": context}),
        *records[2:],
    )
    assert (
        "overlapping_final_windows" in assess_candidate(c, records, epoch).reason_codes
    )


def test_exploration_without_valid_selection_treatment_stays_provisional():
    c = candidate()
    protocol = c.protocol.model_copy(update={"selection_method": "exploratory"})
    c = compile_proposal(
        CandidateProposal(
            template_id=c.template_id,
            source_ids=c.source_ids,
            reason=c.reason,
            selection_method=protocol.selection_method,
        ),
        (profile(),),
        epoch_id=c.epoch_id,
    )
    epoch = epoch_for(c)
    decision = assess_candidate(c, evidence_for(c, epoch), epoch)
    assert decision.action == "provisional"
    assert "selection_not_validated" in decision.reason_codes


def test_zero_reference_is_undefined():
    c = candidate()
    epoch = epoch_for(c)
    assert (
        "undefined_reference_skill"
        in assess_candidate(
            c, evidence_for(c, epoch, loss=0, reference=0), epoch
        ).reason_codes
    )


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


@pytest.mark.parametrize("value", ["mae", 4, None, []])
def test_malformed_node_metrics_fail_closed(value):
    c = candidate()
    epoch = epoch_for(c)
    records = evidence_for(c, epoch)
    invalid = records[0].model_copy(update={"metrics": {"question": value}})
    assert assess_candidate(c, (invalid, *records[1:]), epoch).action != "activate"


def test_event_gate_is_explicit_even_for_well_scored_evidence():
    source = profile(
        proposed_mapping={
            **profile().proposed_mapping,
            "operational_limit": {"constant": 12},
        }
    )
    c = candidate("declared_limit", source)
    epoch = epoch_for(c)
    decision = assess_candidate(c, evidence_for(c, epoch), epoch)
    assert decision.action != "activate"
    assert "event_method_provisional" in decision.reason_codes


def test_expected_deviation_keeps_comparable_level_targets():
    c = candidate("expected_deviation")
    # Subtracting two forecasts of one series would cancel both reconstructed
    # actuals to zero. Keep level forecasts and their explicit reference instead.
    assert c.graph.nodes[-1].inputs == ("forecast",)
    assert c.protocol.reference_node_id == "reference"


def test_frozen_final_block_cannot_be_cherry_picked():
    c = candidate()
    epoch = epoch_for(c, 31)
    assert (
        assess_candidate(c, evidence_for(c, epoch)[:30], epoch).action == "provisional"
    )


def test_huge_finite_losses_do_not_overflow_skill_comparison():
    c = candidate()
    epoch = epoch_for(c)
    decision = assess_candidate(
        c, evidence_for(c, epoch, loss=1e307, reference=1e308), epoch
    )
    assert decision.action == "activate"


def test_baseline_replay_qualifies_frozen_synthetic_question(tmp_path):
    from forecast_anything.contracts import Observation, Snapshot
    from forecast_anything.evaluation.records import evaluate_run
    from forecast_anything.operators import register_builtin_operators
    from forecast_anything.providers.baseline import SeasonalNaiveProvider
    from forecast_anything.runtime import Runtime
    from forecast_anything.temporal import freeze

    ledger = Ledger(tmp_path / "replay.db")
    c = candidate()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
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


@pytest.mark.parametrize(
    "semantic,declaration",
    [
        ("frequency", {"constant": "invented-cadence"}),
        ("timezone", {"constant": "Not/AZone"}),
        ("calendar", {"constant": "invented-calendar"}),
        ("missing_values", {"constant": [{"secret": "nested"}]}),
    ],
)
def test_invalid_semantic_declarations_remain_unresolved(
    tmp_path, semantic, declaration
):
    path = tmp_path / "source.csv"
    path.write_text("date,value\n2026-01-01,1\n")
    source = SourceSpec(
        source_id="sales",
        kind="csv",
        location=str(path),
        mapping={**profile().proposed_mapping, semantic: declaration},
        refresh_seconds=60,
    )
    inspected = inspect_source(source)
    assert semantic in inspected.unresolved
    assert semantic not in inspected.proposed_mapping
    assert all(
        not c.executable for c in propose_candidates((inspected,), DiscoveryBudget())
    )


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


def test_empty_source_provenance_cannot_qualify():
    c = candidate()
    epoch = epoch_for(c, source_snapshot_ids=())
    assert assess_candidate(c, evidence_for(c, epoch), epoch).action == "reject"


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
        as_of=datetime(2025, 12, 31, tzinfo=timezone.utc),
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
            as_of=datetime(2026, 1, 2, tzinfo=timezone.utc),
            observations=(),
            assumptions=(),
        )
    )
    # An evaluated score cannot be attached to an empty issued result, even with
    # real run/snapshot foreign keys and plausible candidate lineage.
    with pytest.raises(DomainError, match="invalid_discovery_evidence"):
        ledger.append_evaluation(record)


def test_evaluation_context_cannot_be_mutated_after_validation():
    from pydantic import ValidationError

    c = candidate()
    record = evidence_for(c, epoch_for(c))[0]
    with pytest.raises(ValidationError):
        record.discovery.temporal_valid = False


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
