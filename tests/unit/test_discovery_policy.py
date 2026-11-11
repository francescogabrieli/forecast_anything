"""Discovery evidence requirements and qualification policy."""

import pytest
from discovery_fixtures import candidate, epoch_for, evidence_for, profile

from forecast_anything.discovery.candidates import (
    CandidateProposal,
    compile_proposal,
)
from forecast_anything.discovery.policy import (
    assess_candidate,
)


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
    assert assess_candidate(c, (*records, revised), epoch).action != "activate"


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


def test_empty_source_provenance_cannot_qualify():
    c = candidate()
    epoch = epoch_for(c, source_snapshot_ids=())
    assert assess_candidate(c, evidence_for(c, epoch), epoch).action == "reject"


def test_evaluation_context_cannot_be_mutated_after_validation():
    from pydantic import ValidationError

    c = candidate()
    record = evidence_for(c, epoch_for(c))[0]
    with pytest.raises(ValidationError):
        record.discovery.temporal_valid = False
