"""Persistence for discovery budgets, candidates, and eligibility decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts import (
    Candidate,
    DiscoveryBudget,
    DiscoveryEpoch,
    DomainError,
    EligibilityDecision,
)
from .encoding import _json

if TYPE_CHECKING:
    from ..jobs import LeaseGuard


class DiscoveryStorageMixin:
    def put_discovery_epoch(
        self,
        epoch: DiscoveryEpoch,
        budget: DiscoveryBudget,
        *,
        lease_guard: LeaseGuard | None = None,
    ) -> str:
        """Freeze search configuration, budget and target reservations atomically.

        Origin IDs denote dataset/window identities, never configuration-specific
        labels. Different configurations must reserve fresh final windows.
        """
        epoch = DiscoveryEpoch.model_validate(epoch.model_dump())
        budget = DiscoveryBudget.model_validate(budget.model_dump())
        content, limits = (
            _json(epoch.model_dump(mode="json")),
            _json(budget.model_dump()),
        )
        with self._transaction(lease_guard) as connection:
            previous = connection.execute(
                "SELECT content, budget FROM discovery_epochs WHERE epoch_id = ?",
                (epoch.epoch_id,),
            ).fetchone()
            if previous is not None:
                if previous != (content, limits):
                    raise DomainError(
                        "immutable_identity", {"epoch_id": epoch.epoch_id}
                    )
                return epoch.epoch_id
            for snapshot_id in epoch.source_snapshot_ids:
                if (
                    connection.execute(
                        "SELECT 1 FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
                    ).fetchone()
                    is None
                ):
                    raise DomainError(
                        "missing_discovery_snapshot", {"snapshot_id": snapshot_id}
                    )
            for role, origins in (
                ("final", epoch.final_origin_ids),
                ("tuning", epoch.tuning_origin_ids),
            ):
                for origin in origins:
                    reservations = connection.execute(
                        "SELECT role FROM discovery_origins WHERE origin_id = ?",
                        (origin,),
                    ).fetchall()
                    if reservations and (
                        role == "final" or any(r[0] == "final" for r in reservations)
                    ):
                        raise DomainError("holdout_reuse", {"origin_id": origin})
            connection.execute(
                "INSERT INTO discovery_epochs VALUES (?, ?, ?)",
                (epoch.epoch_id, content, limits),
            )
            for role, origins in (
                ("final", epoch.final_origin_ids),
                ("tuning", epoch.tuning_origin_ids),
            ):
                for origin in origins:
                    connection.execute(
                        "INSERT INTO discovery_origins VALUES (?, ?, ?)",
                        (origin, epoch.epoch_id, role),
                    )
        return epoch.epoch_id

    def discovery_budget(self, epoch_id: str) -> DiscoveryBudget:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT budget FROM discovery_epochs WHERE epoch_id = ?", (epoch_id,)
            ).fetchone()
        if row is None:
            raise DomainError("unknown_discovery_epoch", {})
        return DiscoveryBudget.model_validate_json(row[0])

    def get_discovery_epoch(self, epoch_id: str) -> DiscoveryEpoch:
        frozen = DiscoveryEpoch.model_validate_json(
            self._get("discovery_epochs", {"epoch_id": epoch_id})
        )
        with self._connection() as connection:
            additions = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT candidate_id FROM discovery_explored_appends "
                    "WHERE epoch_id = ? ORDER BY rowid",
                    (epoch_id,),
                ).fetchall()
            )
        return frozen.model_copy(
            update={"explored_candidate_ids": frozen.explored_candidate_ids + additions}
        )

    def register_candidate(
        self, candidate: Candidate, *, lease_guard: LeaseGuard | None = None
    ) -> str:
        from ..discovery.candidates import validate_candidate

        candidate = Candidate.model_validate(candidate.model_dump())
        if "candidate_identity_mismatch" in validate_candidate(candidate):
            raise DomainError("candidate_identity_mismatch", {})
        content = _json(candidate.model_dump(mode="json"))
        with self._transaction(lease_guard) as connection:
            previous = connection.execute(
                "SELECT content FROM discovery_candidates WHERE candidate_id = ?",
                (candidate.candidate_id,),
            ).fetchone()
            if previous is not None:
                # Agent prose is not part of question identity: first proposal wins.
                return candidate.candidate_id
            row = connection.execute(
                "SELECT content, budget FROM discovery_epochs WHERE epoch_id = ?",
                (candidate.epoch_id,),
            ).fetchone()
            if row is None:
                raise DomainError("unknown_discovery_epoch", {})
            epoch, budget = (
                DiscoveryEpoch.model_validate_json(row[0]),
                DiscoveryBudget.model_validate_json(row[1]),
            )
            if candidate.candidate_id not in epoch.explored_candidate_ids:
                raise DomainError("epoch_lineage_mismatch", {})
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
        return candidate.candidate_id

    def get_candidate(self, candidate_id: str) -> Candidate:
        return Candidate.model_validate_json(
            self._get("discovery_candidates", {"candidate_id": candidate_id})
        )

    def candidates_for_epoch(self, epoch_id: str) -> tuple[Candidate, ...]:
        self.get_discovery_epoch(epoch_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT content FROM discovery_candidates WHERE epoch_id = ? ORDER BY candidate_id",
                (epoch_id,),
            ).fetchall()
        return tuple(Candidate.model_validate_json(row[0]) for row in rows)

    def discovery_usage(self, epoch_id: str) -> tuple[int, int]:
        self.get_discovery_epoch(epoch_id)
        with self._connection() as connection:
            return tuple(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE epoch_id = ?", (epoch_id,)
                ).fetchone()[0]
                for table in ("discovery_candidates", "discovery_tool_calls")
            )

    def consume_discovery_tool_call(
        self, epoch_id: str, call_id: str, *, lease_guard: LeaseGuard | None = None
    ) -> None:
        """Reserve a call before dispatch; retry the same operation ID after restart."""
        if not isinstance(call_id, str) or not call_id.strip():
            raise DomainError("invalid_tool_call_id", {})
        with self._transaction(lease_guard) as connection:
            row = connection.execute(
                "SELECT budget FROM discovery_epochs WHERE epoch_id = ?", (epoch_id,)
            ).fetchone()
            if row is None:
                raise DomainError("unknown_discovery_epoch", {})
            if connection.execute(
                "SELECT 1 FROM discovery_tool_calls WHERE epoch_id = ? AND call_id = ?",
                (epoch_id, call_id),
            ).fetchone():
                return
            budget = DiscoveryBudget.model_validate_json(row[0])
            count = connection.execute(
                "SELECT COUNT(*) FROM discovery_tool_calls WHERE epoch_id = ?",
                (epoch_id,),
            ).fetchone()[0]
            if count >= budget.max_tool_calls:
                raise DomainError(
                    "discovery_budget_exhausted", {"budget": "tool_calls"}
                )
            connection.execute(
                "INSERT INTO discovery_tool_calls VALUES (?, ?)", (epoch_id, call_id)
            )

    def append_eligibility_decision(
        self, candidate_id: str, decision: EligibilityDecision
    ) -> None:
        candidate = self.get_candidate(candidate_id)
        decision = EligibilityDecision.model_validate(decision.model_dump())
        if (decision.candidate_id, decision.protocol_id, decision.epoch_id) != (
            candidate_id,
            candidate.protocol_id,
            candidate.epoch_id,
        ):
            raise DomainError("decision_lineage_mismatch", {})
        if decision.backtest_id is not None:
            from ..backtesting.store import BacktestStore
            from ..discovery.policy import assess_candidate_backtest

            backtests = BacktestStore(self)
            report = backtests.get_report(decision.backtest_id)
            plan = backtests.get_plan(decision.backtest_id)
            if plan.watch_id is None or plan.candidate_id != candidate_id:
                raise DomainError("watch_backtest_lineage_mismatch", {})
            outcomes = []
            offset = 0
            while True:
                page = backtests.list_origins(
                    decision.backtest_id, offset=offset, limit=50
                )
                outcomes.extend(page.origins)
                if page.next_offset is None:
                    break
                offset = page.next_offset
            expected = assess_candidate_backtest(
                candidate, report, plan, tuple(outcomes)
            )
        else:
            from ..discovery.policy import assess_candidate

            expected = assess_candidate(
                candidate,
                tuple(
                    self.get_evaluation(identity)
                    for identity in decision.evaluation_ids
                ),
                self.get_discovery_epoch(candidate.epoch_id),
            )
        if decision != expected:
            raise DomainError("invalid_eligibility_decision", {})
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO eligibility_decisions (candidate_id, content) VALUES (?, ?)",
                (candidate_id, _json(decision.model_dump(mode="json"))),
            )

    def eligibility_decisions(
        self, candidate_id: str
    ) -> tuple[EligibilityDecision, ...]:
        self.get_candidate(candidate_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT content FROM eligibility_decisions WHERE candidate_id = ? ORDER BY sequence",
                (candidate_id,),
            ).fetchall()
        return tuple(EligibilityDecision.model_validate_json(row[0]) for row in rows)
