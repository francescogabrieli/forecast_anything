"""Durable reservations and append-only exploration for optional agent tools."""

from __future__ import annotations

import json
from hashlib import sha256

from ..contracts import Candidate, DiscoveryBudget, DiscoveryEpoch, DomainError


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class AgentStorageMixin:
    def register_agent_candidate(self, candidate: Candidate) -> str:
        """Append a core-compiled exploratory identity and candidate together.

        Final/tuning reservations or an eligibility decision seal the search.
        Unknown templates remain non-executable candidates, never a graph.
        """
        from .candidates import validate_candidate

        candidate = Candidate.model_validate(candidate.model_dump())
        if "candidate_identity_mismatch" in validate_candidate(candidate):
            raise DomainError("candidate_identity_mismatch", {})
        content = _json(candidate.model_dump(mode="json"))
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT content, budget FROM discovery_epochs WHERE epoch_id = ?",
                (candidate.epoch_id,),
            ).fetchone()
            if row is None:
                raise DomainError("unknown_discovery_epoch", {})
            epoch = DiscoveryEpoch.model_validate_json(row[0])
            previous = connection.execute(
                "SELECT content FROM discovery_candidates WHERE candidate_id = ?",
                (candidate.candidate_id,),
            ).fetchone()
            if previous is not None:
                return candidate.candidate_id
            searched = candidate.candidate_id in epoch.explored_candidate_ids
            if not searched:
                decided = connection.execute(
                    "SELECT 1 FROM eligibility_decisions AS decision "
                    "JOIN discovery_candidates AS candidate "
                    "ON candidate.candidate_id = decision.candidate_id "
                    "WHERE candidate.epoch_id = ? LIMIT 1",
                    (candidate.epoch_id,),
                ).fetchone()
                evaluated = connection.execute(
                    "SELECT 1 FROM evaluations WHERE "
                    "json_extract(content, '$.discovery.epoch_id') = ? LIMIT 1",
                    (candidate.epoch_id,),
                ).fetchone()
                if (
                    epoch.final_origin_ids
                    or epoch.tuning_origin_ids
                    or epoch.final_candidate_id is not None
                    or decided is not None
                    or evaluated is not None
                ):
                    raise DomainError("exploration_closed", {})
            budget = DiscoveryBudget.model_validate_json(row[1])
            count = connection.execute(
                "SELECT COUNT(*) FROM discovery_candidates WHERE epoch_id = ?",
                (candidate.epoch_id,),
            ).fetchone()[0]
            if count >= budget.max_candidates:
                raise DomainError(
                    "discovery_budget_exhausted", {"budget": "candidates"}
                )
            connection.execute(
                "INSERT INTO discovery_candidates VALUES (?, ?, ?)",
                (candidate.candidate_id, candidate.epoch_id, content),
            )
            if not searched:
                connection.execute(
                    "INSERT INTO discovery_explored_appends VALUES (?, ?)",
                    (candidate.epoch_id, candidate.candidate_id),
                )
        return candidate.candidate_id

    def reserve_agent_operation(
        self,
        job_id: str,
        epoch_id: str,
        session_id: str,
        call_key: str,
        tool: str,
        input_hash: str,
    ) -> tuple[str, dict | None]:
        """Bind one Eve call to a durable core-issued ID and consume its budget.

        A retry with the same call key and input gets the same result. The
        reservation is committed before tool execution, including after a crash.
        """
        if not isinstance(call_key, str) or not call_key.strip() or len(call_key) > 256:
            raise DomainError("invalid_tool_call_id", {})
        operation_id = sha256(
            _json({"job_id": job_id, "call_key": call_key}).encode()
        ).hexdigest()
        with self._transaction() as connection:
            job = connection.execute(
                "SELECT payload, state FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if job is None:
                raise DomainError("invalid_agent_job", {})
            payload = json.loads(job[0])
            if payload.get("kind") != "discovery":
                raise DomainError("invalid_agent_job", {})
            if payload.get("epoch_id") != epoch_id:
                raise DomainError("epoch_lineage_mismatch", {})
            if payload.get("session_id") != session_id:
                raise DomainError("agent_session_mismatch", {})
            previous = connection.execute(
                "SELECT operation_id, tool, input_hash, result FROM agent_tool_operations "
                "WHERE job_id = ? AND call_key = ?",
                (job_id, call_key),
            ).fetchone()
            if previous is not None:
                if previous[1:3] != (tool, input_hash):
                    raise DomainError("idempotency_conflict", {})
                if job[1] not in {"pending", "running"} and previous[3] is None:
                    raise DomainError("invalid_agent_job", {})
                return previous[0], json.loads(previous[3]) if previous[3] else None
            if job[1] not in {"pending", "running"}:
                raise DomainError("invalid_agent_job", {})
            epoch = connection.execute(
                "SELECT budget FROM discovery_epochs WHERE epoch_id = ?", (epoch_id,)
            ).fetchone()
            if epoch is None:
                raise DomainError("unknown_discovery_epoch", {})
            budget = DiscoveryBudget.model_validate_json(epoch[0])
            count = connection.execute(
                "SELECT COUNT(*) FROM discovery_tool_calls WHERE epoch_id = ?",
                (epoch_id,),
            ).fetchone()[0]
            if count >= budget.max_tool_calls:
                raise DomainError(
                    "discovery_budget_exhausted", {"budget": "tool_calls"}
                )
            connection.execute(
                "INSERT INTO discovery_tool_calls VALUES (?, ?)",
                (epoch_id, operation_id),
            )
            connection.execute(
                "INSERT INTO agent_tool_operations VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (
                    job_id,
                    call_key,
                    epoch_id,
                    session_id,
                    operation_id,
                    tool,
                    input_hash,
                ),
            )
        return operation_id, None

    def complete_agent_operation(self, operation_id: str, result: dict) -> dict:
        content = _json(result)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT result FROM agent_tool_operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is None:
                raise DomainError("invalid_agent_operation", {})
            if row[0] is None:
                connection.execute(
                    "UPDATE agent_tool_operations SET result = ? WHERE operation_id = ?",
                    (content, operation_id),
                )
            elif row[0] != content:
                raise DomainError("idempotency_conflict", {})
        return result
