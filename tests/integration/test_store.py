from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from forecast_anything.contracts import DomainError, EventRecord, GraphSpec, Node, RunRecord, Snapshot
from forecast_anything.store import Ledger


def run_record(run_id="r"):
    return RunRecord(run_id=run_id, graph_id="g", graph_version=1,
        as_of="2026-10-24T12:00:00Z", snapshot_ids=(), requested_provider={},
        actual_provider={}, state="succeeded", results={}, evidence_ids=(),
        scenario_id=None, parent_run_id=None)


def event(run_id="r", event_id="e"):
    return EventRecord(cursor=999, event_id=event_id, kind="issued", run_id=run_id, payload={"ok": True})


def test_graph_revision_is_immutable(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    graph = GraphSpec(graph_id="g", version=1, nodes=())
    assert ledger.put_graph(graph) == ("g", 1)
    assert ledger.get_graph("g", 1) == graph
    changed = GraphSpec(graph_id="g", version=1, nodes=(
        Node(node_id="source", kind="source", inputs=(), config={"source_id": "s"}),))
    with pytest.raises(DomainError):
        ledger.put_graph(changed)
    assert ledger.put_graph(graph) == ("g", 1)


def test_snapshot_is_immutable(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    snapshot = Snapshot(snapshot_id="s", as_of="2026-10-24T12:00:00Z", observations=(), assumptions=())
    assert ledger.put_snapshot(snapshot) == "s"
    assert ledger.put_snapshot(snapshot) == "s"
    with pytest.raises(DomainError):
        ledger.put_snapshot(snapshot.model_copy(update={"assumptions": ("changed",)}))
    assert ledger.get_snapshot("s") == snapshot


def test_no_partial_commit(tmp_path):
    path = tmp_path / "state.db"
    ledger = Ledger(path)
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER fail_outbox BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'injected'); END")
    with pytest.raises((sqlite3.DatabaseError, DomainError)):
        ledger.append_run(run_record(), (event(),), "key")
    assert ledger.get_run_by_key("key") is None
    assert ledger.events_after(0) == ()
    with pytest.raises(DomainError):
        ledger.get_run("r")
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER fail_outbox")
    assert ledger.append_run(run_record(), (event(),), "key") == run_record()


def test_retry_returns_original(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    original = run_record()
    assert ledger.get_run_by_key("key") is None
    assert ledger.append_run(original, (event(),), "key") == original
    assert ledger.append_run(original, (event().model_copy(update={"cursor": -1}),), "key") == original
    assert ledger.get_run_by_key("key") == original
    with pytest.raises(DomainError):
        ledger.append_run(original.model_copy(update={"state": "failed"}), (event(),), "key")
    with pytest.raises(DomainError):
        ledger.append_run(original, (event().model_copy(update={"payload": {}}),), "key")
    with pytest.raises(DomainError):
        ledger.append_run(original.model_copy(update={"state": "failed"}), (), "other")
    assert len(ledger.events_after(0)) == 1


def test_restart_and_cursor(tmp_path):
    path = tmp_path / "state.db"
    Ledger(path).append_run(run_record(), (event(), event(event_id="e2")), "key")
    ledger = Ledger(path)
    assert ledger.get_run("r") == run_record()
    assert ledger.get_run_by_key("key") == run_record()
    first = ledger.events_after(0, limit=1)
    assert first[0].cursor == 1
    assert first[0].event_id == "e"
    assert ledger.events_after(first[0].cursor)[0].event_id == "e2"
    assert Ledger(path).events_after(0) == ledger.events_after(0)
    assert ledger.events_after(2) == ()
    with pytest.raises(DomainError):
        ledger.events_after(0, limit=-1)


def test_concurrent_writers_and_retries(tmp_path):
    path = tmp_path / "state.db"
    Ledger(path)
    def append(index):
        return Ledger(path).append_run(run_record(str(index)), (event(str(index), str(index)),), str(index))
    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(append, list(range(12)) * 2))
    assert len(records) == 24
    events = Ledger(path).events_after(0)
    assert len(events) == 12
    assert [e.cursor for e in events] == list(range(1, 13))


def test_event_conflict_rolls_back_run(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    ledger.append_run(run_record(), (event(),), "key")
    with pytest.raises(DomainError):
        ledger.append_run(run_record("r2"), (event("r2"),), "key2")
    assert ledger.get_run_by_key("key2") is None
    with pytest.raises(DomainError):
        ledger.append_run(run_record("r3"), (event(),), "key3")
    assert ledger.get_run_by_key("key3") is None
