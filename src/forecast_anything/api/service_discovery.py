"""Candidate compilation and scoped discovery agent tools."""

from hashlib import sha256

from pydantic import ValidationError

from ..contracts import (
    CandidateRequest,
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
)
from ..discovery.agent_gateway import AgentOperationRequest, AgentOperationResponse
from ..discovery.candidates import CandidateProposal, compile_proposal
from ..forecast_policy import provider_epoch_context
from ..graph import compile_graph
from ..runtime import _digest
from ..store import _json


class DiscoveryOperations:
    def agent_operation(self, request: AgentOperationRequest) -> AgentOperationResponse:
        """Serve a scoped Eve tool after durable core budget reservation."""
        request = AgentOperationRequest.model_validate(request.model_dump())
        operation_id, previous = self.ledger.reserve_agent_operation(
            request.job_id,
            request.epoch_id,
            request.session_id,
            request.call_key,
            request.tool,
            sha256(_json(request.input).encode()).hexdigest(),
        )
        if previous is not None:
            return AgentOperationResponse(operation_id=operation_id, result=previous)
        result = self._agent_tool_result(request)
        return AgentOperationResponse(
            operation_id=operation_id,
            result=self.ledger.complete_agent_operation(operation_id, result),
        )

    def _agent_tool_result(self, request: AgentOperationRequest) -> dict:
        job = self.queue.get(request.job_id)
        source_ids = set(job.payload["source_ids"])
        profiles = {}
        for candidate in self.ledger.candidates_for_epoch(request.epoch_id):
            for profile in candidate.source_profiles:
                prior = profiles.setdefault(profile.source_id, profile)
                if prior != profile:
                    raise DomainError("ambiguous_source_profile", {})

        if request.tool == "inspectSource":
            source_id = request.input.get("source_id")
            if (
                set(request.input) != {"source_id"}
                or not isinstance(source_id, str)
                or source_id not in source_ids
            ):
                raise DomainError("invalid_agent_input", {})
            if source_id not in profiles:
                raise DomainError("unknown_source_profile", {})
            return profiles[source_id].model_dump(mode="json")

        if request.tool == "proposeCandidates":
            proposals = request.input.get("proposals")
            if (
                set(request.input) != {"proposals"}
                or not isinstance(proposals, list)
                or len(proposals)
                > self.ledger.discovery_budget(request.epoch_id).max_candidates
            ):
                raise DomainError("invalid_agent_input", {})
            candidates = []
            for raw in proposals:
                try:
                    proposal = CandidateProposal.model_validate(raw)
                except ValidationError as error:
                    raise DomainError("invalid_agent_input", {}) from error
                if not set(proposal.source_ids).issubset(source_ids):
                    raise DomainError("invalid_agent_input", {})
                selected = tuple(
                    profiles[name] for name in proposal.source_ids if name in profiles
                )
                candidate = compile_proposal(
                    proposal,
                    selected,
                    epoch_id=request.epoch_id,
                    forecast_provider=self.runtime.required_provider
                    or "seasonal_naive",
                )
                self.ledger.register_agent_candidate(candidate)
                if candidate.executable:
                    self.ledger.put_graph(candidate.graph)
                candidates.append(self.ledger.get_candidate(candidate.candidate_id))
            unique = {candidate.candidate_id: candidate for candidate in candidates}
            return {
                "candidateIds": list(unique),
                "candidates": [
                    candidate.model_dump(mode="json") for candidate in unique.values()
                ],
            }

        if request.tool == "explainRun":
            run_id = request.input.get("run_id")
            if set(request.input) != {"run_id"} or not isinstance(run_id, str):
                raise DomainError("invalid_agent_input", {})
            run = self.ledger.get_run(run_id)
            bindings = self.ledger.run_bindings(run_id)
            if not bindings or not set(bindings).issubset(source_ids):
                raise DomainError("run_lineage_mismatch", {})
            return {
                "text": f"Run {run.run_id} recorded {len(run.evidence_ids)} evidence item(s).",
                "evidenceIds": list(run.evidence_ids),
            }
        raise DomainError("unknown_agent_tool", {})

    def candidate(self, request: CandidateRequest):
        request = CandidateRequest.model_validate(request.model_dump())
        profiles = tuple(self.profile(name)[0] for name in request.source_ids)
        epoch_id = _digest(
            {
                "profiles": [p.model_dump(mode="json") for p in profiles],
                "proposal": request.model_dump(mode="json"),
                **provider_epoch_context(self.runtime),
            }
        )
        candidate = compile_proposal(
            CandidateProposal(**request.model_dump()),
            profiles,
            epoch_id=epoch_id,
            forecast_provider=self.runtime.required_provider or "seasonal_naive",
        )
        if candidate.executable:
            compile_graph(
                candidate.graph,
                {k: p.capabilities() for k, p in self.runtime.providers.items()},
                {k: o.contract() for k, o in self.runtime.operators.items()},
            )
        self.ledger.put_discovery_epoch(
            DiscoveryEpoch(
                epoch_id=epoch_id,
                source_snapshot_ids=(),
                explored_candidate_ids=(candidate.candidate_id,),
                final_origin_ids=(),
            ),
            DiscoveryBudget(),
        )
        self.ledger.register_candidate(candidate)
        if candidate.executable:
            self.ledger.put_graph(candidate.graph)
        return candidate
