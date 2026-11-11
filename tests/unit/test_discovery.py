"""Discovery proposal compilation, semantics and provider selection."""

import pytest
from discovery_fixtures import candidate, epoch_for, profile

from forecast_anything.contracts import (
    DiscoveryBudget,
    DomainError,
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


def test_expected_deviation_keeps_comparable_level_targets():
    c = candidate("expected_deviation")
    # Subtracting two forecasts of one series would cancel both reconstructed
    # actuals to zero. Keep level forecasts and their explicit reference instead.
    assert c.graph.nodes[-1].inputs == ("forecast",)
    assert c.protocol.reference_node_id == "reference"


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
