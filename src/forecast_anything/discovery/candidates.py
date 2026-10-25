"""Deterministic registered questions; agents supply proposals, never executable DAGs.

The default provider is deliberately the point seasonal baseline. A declared
limit is retained as a proposal but cannot run an event operator until a provider
with joint paths is explicitly supported. No Timestral acceptance is implied.
"""

from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..contracts import (
    Candidate,
    CandidateCostEstimate,
    Contract,
    DiscoveryBudget,
    DomainError,
    GraphSpec,
    Identifier,
    Node,
    SourceProfile,
    VerificationProtocol,
)
from ..graph import compile_graph
from ..operators import register_builtin_operators
from ..providers.baseline import SeasonalNaiveProvider

# Questions use existing numerical operators, with no inferred causal relation.
TEMPLATES = {
    "expected_deviation": "sum_aligned",
    "forecast_change": "sum_aligned",
    "declared_limit": "any_exceed",
}


class CandidateProposal(Contract):
    template_id: Identifier
    source_ids: tuple[Identifier, ...]
    reason: Identifier
    selection_method: Literal["prespecified_holdout", "exploratory", "corrected"] = (
        "prespecified_holdout"
    )


def _digest(value) -> str:
    content = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(content.encode()).hexdigest()


def _constant(profile, name):
    declaration = profile.proposed_mapping.get(name)
    if not isinstance(declaration, dict) or set(declaration) != {"constant"}:
        raise ValueError(name)
    return declaration["constant"]


def _resolved(profile):
    """Read explicit declarations only, including their provenance revision."""
    if profile.unresolved or not profile.source_revision:
        raise ValueError("unresolved_source_mapping")
    for name in (
        "event_time",
        "available_at",
        "revision",
        "value",
        "series_id",
        "unit",
    ):
        mapping = profile.proposed_mapping.get(name)
        if isinstance(mapping, str):
            if mapping not in profile.fields:
                raise ValueError("unresolved_source_mapping")
        elif not isinstance(mapping, dict) or set(mapping) != {"constant"}:
            raise ValueError("unresolved_source_mapping")
    series, unit = (_constant(profile, name) for name in ("series_id", "unit"))
    if not all(isinstance(x, str) and x.strip() for x in (series, unit)):
        raise ValueError("unresolved_source_mapping")
    frequency = _constant(profile, "frequency")
    frequency = (
        {"D": "1d", "H": "1h"}.get(frequency, frequency)
        if isinstance(frequency, str)
        else None
    )
    if not isinstance(frequency, str) or not re.fullmatch(
        r"[1-9][0-9]*[hd]", frequency
    ):
        raise ValueError("unsupported_frequency")
    ZoneInfo(_constant(profile, "timezone"))
    if _constant(profile, "calendar") != "gregorian":
        raise ValueError("unsupported_calendar")
    missing = _constant(profile, "missing_values")
    if not isinstance(missing, list) or any(
        isinstance(x, (list, dict)) for x in missing
    ):
        raise ValueError("unresolved_source_mapping")
    return series, unit, frequency


def graph_support(graph: GraphSpec) -> tuple[str, ...]:
    """Compile against trusted builtins; unregistered providers cannot self-certify."""
    try:
        compile_graph(
            graph,
            {"seasonal_naive": SeasonalNaiveProvider(1).capabilities()},
            {name: op.contract() for name, op in register_builtin_operators().items()},
        )
    except DomainError as error:
        return (error.code,)
    return ()


def _graph(template, profile):
    series, unit, frequency = _resolved(profile)
    nodes = [
        Node(
            node_id="source",
            kind="source",
            inputs=(),
            config={
                "source_id": profile.source_id,
                "series_ids": [series],
                "units": [unit],
                "frequency": frequency,
            },
        )
    ]
    # Period 1 is the frozen reference. Period 2 is a declared baseline candidate,
    # not a claim that seasonal repetition outperforms another model.
    for name, period in (("forecast", 2), ("reference", 1)):
        nodes.append(
            Node(
                node_id=name,
                kind="forecast",
                inputs=("source",),
                config={
                    "provider": "seasonal_naive",
                    "history": "source",
                    "horizon": 1,
                    "frequency": frequency,
                    "options": {"period": period},
                    "relation_type": {"source": "statistical"},
                },
            )
        )
    if template == "declared_limit":
        threshold = _constant(profile, "operational_limit")
        if type(threshold) not in (int, float) or not math.isfinite(threshold):
            raise ValueError("undeclared_operational_limit")
        inputs, parameters = (
            ("forecast",),
            {
                "threshold": threshold,
                "comparator": "gt",
                "bindings": {"value": "forecast"},
            },
        )
    else:
        # A forecast view whose common timestamps can be compared across issues
        # by the watch layer. This graph does not invent a previous run.
        inputs, parameters = ("forecast",), {}
    nodes.append(
        Node(
            node_id="question",
            kind="event" if template == "declared_limit" else "transform",
            inputs=inputs,
            config={
                "operator": TEMPLATES[template],
                "parameters": parameters,
                "relation_type": {name: "accounting" for name in inputs},
            },
        )
    )
    return GraphSpec(
        graph_id=_digest([n.model_dump(mode="json") for n in nodes]),
        version=1,
        nodes=tuple(nodes),
    )


def compile_proposal(
    proposal: CandidateProposal, profiles: tuple[SourceProfile, ...], *, epoch_id: str
) -> Candidate:
    """Trusted compilation boundary. ``profiles`` must come from the source catalog.

    Unknown/free-form templates and unresolved mappings are retained with an empty
    non-executable graph. Agents cannot supply their own graph or evidence here.
    """
    proposal = CandidateProposal.model_validate(proposal.model_dump())
    profiles = tuple(SourceProfile.model_validate(p.model_dump()) for p in profiles)
    by_id = {p.source_id: p for p in profiles}
    if len(by_id) != len(profiles):
        raise DomainError("duplicate_source_profile", {})
    sources = tuple(sorted(set(proposal.source_ids)))
    selected = tuple(by_id[s] for s in sources if s in by_id)
    unresolved = []
    graph = GraphSpec(graph_id="non-executable", version=1, nodes=())
    if proposal.template_id not in TEMPLATES:
        unresolved.append("unregistered_template")
    elif len(sources) != 1 or len(selected) != 1:
        unresolved.append("unknown_source")
    else:
        try:
            graph = _graph(proposal.template_id, selected[0])
        except (ValueError, TypeError, ZoneInfoNotFoundError) as error:
            code = (
                str(error)
                if str(error) in {"unsupported_frequency", "unsupported_calendar"}
                else "unresolved_source_mapping"
            )
            unresolved.append(code)
        else:
            unresolved.extend(graph_support(graph))
    protocol = VerificationProtocol(
        criterion="brier" if proposal.template_id == "declared_limit" else "mae",
        selection_method=proposal.selection_method,
    )
    # Identity excludes sample rows and prose; every execution-relevant declaration
    # and the frozen protocol participate. Epoch identity separates repeated search.
    identity = {
        "template_id": proposal.template_id,
        "source_ids": sources,
        "sources": [
            {
                "source_id": p.source_id,
                "source_revision": p.source_revision,
                "mapping": p.proposed_mapping,
                "unresolved": p.unresolved,
            }
            for p in selected
        ],
        "graph": graph.model_dump(mode="json"),
        "protocol": protocol.model_dump(mode="json"),
        "epoch_id": epoch_id,
    }
    return Candidate(
        candidate_id=_digest(identity),
        template_id=proposal.template_id,
        source_ids=sources,
        graph=graph,
        reason=proposal.reason,
        protocol_id=_digest({"protocol": identity, "version": 1}),
        epoch_id=epoch_id,
        protocol=protocol,
        estimated_cost=(
            CandidateCostEstimate(
                status="known",
                value=sum(node.kind == "forecast" for node in graph.nodes),
                basis="static_graph_forecast_count; excludes source I/O, latency, money and verification replay",
            )
            if not unresolved
            else CandidateCostEstimate(basis="unsupported_proposal")
        ),
        source_profiles=selected,
        executable=not unresolved,
        unresolved=tuple(unresolved),
    )


def validate_candidate(candidate: Candidate) -> tuple[str, ...]:
    candidate = Candidate.model_validate(candidate.model_dump())
    expected = compile_proposal(
        CandidateProposal(
            template_id=candidate.template_id,
            source_ids=candidate.source_ids,
            reason=candidate.reason,
            selection_method=candidate.protocol.selection_method,
        ),
        candidate.source_profiles,
        epoch_id=candidate.epoch_id,
    )
    if (
        candidate.candidate_id,
        candidate.protocol_id,
        candidate.graph,
        candidate.protocol,
        candidate.estimated_cost,
        candidate.executable,
        candidate.unresolved,
    ) != (
        expected.candidate_id,
        expected.protocol_id,
        expected.graph,
        expected.protocol,
        expected.estimated_cost,
        expected.executable,
        expected.unresolved,
    ):
        return ("candidate_identity_mismatch",)
    return expected.unresolved


def propose_candidates(
    profiles: tuple[SourceProfile, ...], budget: DiscoveryBudget
) -> tuple[Candidate, ...]:
    budget = DiscoveryBudget.model_validate(budget.model_dump())
    profiles = tuple(
        sorted(
            (SourceProfile.model_validate(p.model_dump()) for p in profiles),
            key=lambda p: p.source_id,
        )
    )
    if len({p.source_id for p in profiles}) != len(profiles):
        raise DomainError("duplicate_source_profile", {})
    epoch_id = _digest(
        [
            {
                "source_id": p.source_id,
                "revision": p.source_revision,
                "mapping": p.proposed_mapping,
                "unresolved": p.unresolved,
            }
            for p in profiles
        ]
    )
    result = []
    for p in profiles:
        for template in TEMPLATES:
            if len(result) >= budget.max_candidates:
                return tuple(result)
            if (
                template == "declared_limit"
                and "operational_limit" not in p.proposed_mapping
            ):
                continue
            result.append(
                compile_proposal(
                    CandidateProposal(
                        template_id=template,
                        source_ids=(p.source_id,),
                        reason=f"Registered {template} question for {p.source_id}.",
                    ),
                    profiles,
                    epoch_id=epoch_id,
                )
            )
    return tuple(result)
