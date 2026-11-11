"""Durable evaluation records, revisions and ledger migration."""

import sqlite3

import pytest
from evaluation_fixtures import actuals, graph, run
from pydantic import ValidationError

from forecast_anything.contracts import (
    DomainError,
)
from forecast_anything.evaluation.records import evaluate_run
from forecast_anything.store import Ledger


def test_revised_actuals_create_new_evaluation(tmp_path):
    issued = run()
    original = actuals()
    revised = actuals((3, 5), revision="2")
    ledger = Ledger(tmp_path / "evaluations.db")
    ledger.append_run(issued, (), "request")
    for snapshot in (original, revised):
        ledger.put_snapshot(snapshot)
    first = evaluate_run(issued, original, graph())
    second = evaluate_run(issued, revised, graph())
    assert first.evaluation_id != second.evaluation_id
    assert evaluate_run(issued, original, graph()) == first
    assert ledger.append_evaluation(first) == first.evaluation_id
    ledger.append_evaluation(second)
    reopened = Ledger(ledger.path)
    assert reopened.get_evaluation(first.evaluation_id).metrics["model"]["mae"] == 0
    assert reopened.get_evaluation(second.evaluation_id).metrics["model"]["mae"] == 1
    assert reopened.get_run("issued") == issued
    assert first.run_id == second.run_id == "issued"
    assert first.actuals_snapshot_id == original.snapshot_id
    assert ledger.append_evaluation(first) == first.evaluation_id
    with pytest.raises(DomainError, match="immutable_identity"):
        ledger.append_evaluation(first.model_copy(update={"status": "pending"}))
    with pytest.raises((TypeError, ValidationError)):
        first.status = "pending"
    with pytest.raises(TypeError):
        first.metrics["model"]["mae"] = 99


def test_evaluation_ledger_requires_existing_evidence(tmp_path):
    ledger = Ledger(tmp_path / "evidence.db")
    with pytest.raises(DomainError, match="missing_evaluation_reference"):
        ledger.append_evaluation(evaluate_run(run(), actuals(), graph()))
    with pytest.raises(DomainError, match="not_found"):
        ledger.get_evaluation("missing")


def test_v1_ledger_migrates_without_changing_runs(tmp_path):
    from importlib.resources import files

    from forecast_anything.store import MIGRATIONS

    path = tmp_path / "v1.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            files("forecast_anything")
            .joinpath("migrations/001_initial.sql")
            .read_text()
        )
        connection.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?)",
            ("issued", "request", run().model_dump_json(), "[]"),
        )
    ledger = Ledger(path)
    snapshot = actuals()
    ledger.put_snapshot(snapshot)
    record = evaluate_run(ledger.get_run("issued"), snapshot, graph())
    ledger.append_evaluation(record)
    assert ledger.get_run("issued") == run()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == len(
            MIGRATIONS
        )


def test_scoring_versions_preserve_historical_identity(tmp_path):
    issued, snapshot = run(), actuals()
    ledger = Ledger(tmp_path / "scores.db")
    ledger.append_run(issued, (), "issue")
    ledger.put_snapshot(snapshot)
    old = evaluate_run(issued, snapshot, graph(), scoring_version="v1")
    new = evaluate_run(issued, snapshot, graph())
    assert old.assumptions[0].startswith("evaluation=v1;")
    assert new.assumptions[0].startswith("evaluation=v2;")
    assert (
        old.evaluation_id
        == "7e64c1f7af73b9cd229b034c9c7468a54b10f37dfb063850a6ea51465b5dc78e"
    )
    assert old.metrics == new.metrics
    assert old.evaluation_id != new.evaluation_id
    for record in (old, new, old):
        assert ledger.append_evaluation(record) == record.evaluation_id
    assert Ledger(ledger.path).get_evaluation(old.evaluation_id) == old
