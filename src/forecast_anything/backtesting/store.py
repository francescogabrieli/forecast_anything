"""Immutable backtest records composed with the ledger's transaction/lease boundary."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, TypeVar

from pydantic import ValidationError

from ..contracts import Contract, DomainError, EvaluationRecord
from ..store import Ledger
from .contracts import (
    BacktestPlan,
    BacktestReport,
    OriginOutcome,
    OriginPage,
    PlannedOrigin,
    canonical_json,
)

if TYPE_CHECKING:
    from ..jobs import LeaseGuard

Record = TypeVar("Record", bound=Contract)


def _validated(model: type[Record], value: Record | str) -> Record:
    try:
        return (
            model.model_validate_json(value)
            if isinstance(value, str)
            else model.model_validate(value.model_dump())
        )
    except (ValidationError, ValueError, TypeError):
        raise DomainError(
            "invalid_backtest_record", {"record_type": model.__name__}
        ) from None


class BacktestStore:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    @staticmethod
    def _decode(connection, table, identity, model):
        where = " AND ".join(f"{key} = ?" for key in identity)
        row = connection.execute(
            f"SELECT content FROM {table} WHERE {where}", tuple(identity.values())
        ).fetchone()
        if row is None:
            raise DomainError("not_found", {"table": table, **identity})
        value = _validated(model, row[0])
        if any(getattr(value, key) != item for key, item in identity.items()):
            raise DomainError(
                "invalid_backtest_record", {"record_type": model.__name__}
            )
        return value

    @staticmethod
    def _insert(connection, table, identity, references, value):
        content = canonical_json(value.model_dump(mode="json"))
        where = " AND ".join(f"{key} = ?" for key in identity)
        previous = connection.execute(
            f"SELECT content FROM {table} WHERE {where}", tuple(identity.values())
        ).fetchone()
        if previous is not None:
            if previous[0] != content:
                raise DomainError("immutable_identity", {"table": table, **identity})
            return
        columns = (*identity, *references, "content")
        placeholders = ", ".join("?" for _ in columns)
        try:
            connection.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                (*identity.values(), *references.values(), content),
            )
        except sqlite3.IntegrityError:
            raise DomainError(
                "invalid_backtest_reference", {"table": table, **identity}
            ) from None

    def put_plan(
        self, plan: BacktestPlan, *, lease_guard: LeaseGuard | None = None
    ) -> str:
        plan = _validated(BacktestPlan, plan)
        with self.ledger._transaction(lease_guard) as connection:
            self._insert(
                connection,
                "backtest_plans",
                {"backtest_id": plan.backtest_id},
                {
                    "plan_id": plan.plan_id,
                    "archive_id": plan.archive.archive_id,
                    "actuals_snapshot_id": plan.actuals_snapshot_id,
                },
                plan,
            )
        return plan.plan_id

    def get_plan(self, backtest_id: str) -> BacktestPlan:
        with self.ledger._connection() as connection:
            return self._decode(
                connection, "backtest_plans", {"backtest_id": backtest_id}, BacktestPlan
            )

    def _check_origin(
        self, connection, outcome: OriginOutcome, plan: BacktestPlan | None = None
    ) -> None:
        plan = (
            plan
            if plan is not None
            else self._decode(
                connection,
                "backtest_plans",
                {"backtest_id": outcome.backtest_id},
                BacktestPlan,
            )
        )
        planned = PlannedOrigin.model_validate(
            outcome.model_dump(include=set(PlannedOrigin.model_fields))
        )
        if (
            outcome.plan_id != plan.plan_id
            or outcome.ordinal >= len(plan.origins)
            or planned != plan.origins[outcome.ordinal]
        ):
            raise DomainError(
                "invalid_backtest_reference",
                {"backtest_id": outcome.backtest_id, "ordinal": outcome.ordinal},
            )
        if (
            outcome.run_id is not None
            and connection.execute(
                "SELECT 1 FROM runs WHERE run_id = ?", (outcome.run_id,)
            ).fetchone()
            is None
        ):
            raise DomainError("invalid_backtest_reference", {"run_id": outcome.run_id})
        if outcome.evaluation_id is not None:
            row = connection.execute(
                "SELECT run_id, actuals_snapshot_id, content FROM evaluations WHERE evaluation_id = ?",
                (outcome.evaluation_id,),
            ).fetchone()
            if row is None or row[:2] != (outcome.run_id, plan.actuals_snapshot_id):
                raise DomainError(
                    "invalid_backtest_reference",
                    {"evaluation_id": outcome.evaluation_id},
                )
            evaluation = _validated(EvaluationRecord, row[2])
            if (
                evaluation.evaluation_id,
                evaluation.run_id,
                evaluation.actuals_snapshot_id,
            ) != (outcome.evaluation_id, outcome.run_id, plan.actuals_snapshot_id):
                raise DomainError(
                    "invalid_backtest_reference",
                    {"evaluation_id": outcome.evaluation_id},
                )
            if outcome.status == "evaluated":
                for node_id, mae in (
                    ("model", outcome.model_mae),
                    ("baseline", outcome.baseline_mae),
                ):
                    score = evaluation.metrics.get(node_id, {})
                    if (
                        evaluation.status != "evaluated"
                        or not isinstance(score, dict)
                        or score.get("status") != "evaluated"
                        or score.get("count") != outcome.matched_count
                        or score.get("mae") != mae
                    ):
                        raise DomainError(
                            "invalid_backtest_reference",
                            {"evaluation_id": outcome.evaluation_id},
                        )

    def put_origin(
        self, outcome: OriginOutcome, *, lease_guard: LeaseGuard | None = None
    ) -> int:
        outcome = _validated(OriginOutcome, outcome)
        with self.ledger._transaction(lease_guard) as connection:
            self._check_origin(connection, outcome)
            self._insert(
                connection,
                "backtest_origins",
                {"backtest_id": outcome.backtest_id, "ordinal": outcome.ordinal},
                {
                    "plan_id": outcome.plan_id,
                    "run_id": outcome.run_id,
                    "evaluation_id": outcome.evaluation_id,
                },
                outcome,
            )
        return outcome.ordinal

    def get_origin(self, backtest_id: str, ordinal: int) -> OriginOutcome:
        with self.ledger._connection() as connection:
            outcome = self._decode(
                connection,
                "backtest_origins",
                {"backtest_id": backtest_id, "ordinal": ordinal},
                OriginOutcome,
            )
            self._check_origin(connection, outcome)
            return outcome

    def list_origins(
        self, backtest_id: str, *, offset: int = 0, limit: int = 25
    ) -> OriginPage:
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 50
        ):
            raise DomainError("invalid_page", {})
        with self.ledger._connection() as connection:
            plan = self._decode(
                connection, "backtest_plans", {"backtest_id": backtest_id}, BacktestPlan
            )
            rows = connection.execute(
                "SELECT ordinal, content FROM backtest_origins WHERE backtest_id = ? ORDER BY ordinal LIMIT ? OFFSET ?",
                # SQLite accepts only signed 64-bit integers. An offset beyond
                # that range cannot address a row in a SQLite table.
                (backtest_id, limit + 1, min(offset, 2**63 - 1)),
            ).fetchall()
            outcomes = []
            for ordinal, content in rows[:limit]:
                outcome = _validated(OriginOutcome, content)
                if (outcome.backtest_id, outcome.ordinal) != (backtest_id, ordinal):
                    raise DomainError(
                        "invalid_backtest_record", {"record_type": "OriginOutcome"}
                    )
                self._check_origin(connection, outcome, plan)
                outcomes.append(outcome)
        return OriginPage(
            backtest_id=backtest_id,
            origins=tuple(outcomes),
            offset=offset,
            limit=limit,
            next_offset=offset + limit if len(rows) > limit else None,
        )

    def _check_report(self, connection, report: BacktestReport) -> None:
        plan = self._decode(
            connection,
            "backtest_plans",
            {"backtest_id": report.backtest_id},
            BacktestPlan,
        )
        shared = (
            "backtest_id",
            "plan_id",
            "actuals_snapshot_id",
            "selection",
            "settings",
            "provider_contracts",
            "frequency",
            "assumptions",
            "protocol_version",
        )
        archive = plan.archive
        if any(
            getattr(report, field) != getattr(plan, field) for field in shared
        ) or any(
            getattr(report, field) != getattr(archive, field)
            for field in ("archive_id", "source_id", "source_revision", "captured_at")
        ):
            raise DomainError(
                "invalid_backtest_reference", {"backtest_id": report.backtest_id}
            )
        rows = connection.execute(
            "SELECT content FROM backtest_origins WHERE backtest_id = ? ORDER BY ordinal",
            (report.backtest_id,),
        ).fetchall()
        outcomes = tuple(_validated(OriginOutcome, row[0]) for row in rows)
        if tuple(outcome.ordinal for outcome in outcomes) != tuple(
            range(len(plan.origins))
        ):
            raise DomainError(
                "invalid_backtest_reference", {"backtest_id": report.backtest_id}
            )
        for outcome in outcomes:
            self._check_origin(connection, outcome, plan)
        for score in report.partitions:
            selected = tuple(
                outcome for outcome in outcomes if outcome.partition == score.partition
            )
            counts = {
                "evaluated": score.evaluated,
                "excluded": score.excluded,
                "failed": score.failed,
                "insufficient_evidence": score.insufficient,
            }
            if (
                score.planned != len(selected)
                or any(
                    sum(outcome.status == status for outcome in selected) != count
                    for status, count in counts.items()
                )
                or score.matched_count
                != sum(outcome.matched_count for outcome in selected)
            ):
                raise DomainError(
                    "invalid_backtest_reference", {"backtest_id": report.backtest_id}
                )

    def put_report(
        self, report: BacktestReport, *, lease_guard: LeaseGuard | None = None
    ) -> str:
        report = _validated(BacktestReport, report)
        with self.ledger._transaction(lease_guard) as connection:
            self._check_report(connection, report)
            self._insert(
                connection,
                "backtest_reports",
                {"backtest_id": report.backtest_id},
                {"report_id": report.report_id, "plan_id": report.plan_id},
                report,
            )
        return report.report_id

    def get_report(self, backtest_id: str) -> BacktestReport:
        with self.ledger._connection() as connection:
            report = self._decode(
                connection,
                "backtest_reports",
                {"backtest_id": backtest_id},
                BacktestReport,
            )
            self._check_report(connection, report)
            return report
