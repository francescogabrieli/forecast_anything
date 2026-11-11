"""HTTP event cursors and watch history."""

from datetime import timedelta

from api_fixtures import AUTH, T, base_run, discovered_candidate, setup
from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.jobs import JobQueue
from forecast_anything.store import Ledger
from forecast_anything.worker import Worker


def test_two_event_consumers_resume_independently(tmp_path):
    ledger, runtime, a, run = base_run(tmp_path)
    b = TestClient(
        create_app(Ledger(ledger.path, clock=lambda: T), runtime, "test-token"),
        headers=AUTH,
    )
    history = a.get("/v1/events").json()
    assert history and history[-1]["kind"] == "run_completed"
    cursor = history[1]["cursor"]
    assert a.get("/v1/events", params={"after": cursor}).json() == history[2:]
    assert b.get("/v1/events").json() == history
    assert (
        b.get("/v1/events", headers={"Last-Event-ID": str(cursor)}).json()
        == history[2:]
    )
    stream = a.get("/v1/events/stream", params={"after": cursor, "follow": False})
    assert f"id: {history[-1]['cursor']}\n" in stream.text
    assert history[0]["event_id"] not in stream.text
    assert a.get("/v1/runs/" + run["run_id"]).json()["evidence_ids"] == []


def test_watch_read_synchronizes_current_clock(tmp_path):
    ledger, runtime, client, _ = base_run(tmp_path)
    with ledger._connection() as connection:
        candidate_id = connection.execute(
            "SELECT candidate_id FROM discovery_candidates LIMIT 1"
        ).fetchone()[0]
    created = client.post(
        "/v1/watches",
        json={
            "candidate_id": candidate_id,
            "next_due_at": (T + timedelta(seconds=1)).isoformat(),
        },
    )
    assert created.status_code == 201
    runtime.clock = ledger.clock = lambda: T + timedelta(seconds=2)
    watches = client.get("/v1/watches").json()
    assert watches[0]["quality"] == "stale"
    assert not watches[0]["operational"]


def test_api_current_clock_blocks_expired_qualified_watch_and_resume(tmp_path):
    from test_worker import qualify_watch

    ledger, runtime, client = setup(tmp_path)
    qualify_watch(tmp_path, ledger)
    assert ledger.get_watch("watch").operational
    ledger.advance_watch("watch", {"kind": "paused"}, T, event_id="pause")
    runtime.clock = ledger.clock = lambda: T + timedelta(days=2)
    response = client.post(
        "/v1/jobs", json={"kind": "watch_resume", "key": "resume", "watch_id": "watch"}
    )
    assert response.status_code == 202
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock(), limit=1)
    current = client.get("/v1/watches").json()[0]
    assert current["lifecycle"] == "evaluating"
    assert current["quality"] == "stale" and not current["operational"]
    # Patching controls also reloads current state after synchronization.
    assert (
        client.patch("/v1/watches/watch", json={"priority": 5, "muted": False}).json()[
            "operational"
        ]
        is False
    )


def test_watch_reads_history_pages_and_current_state(tmp_path):
    _ledger, _runtime, client, _, candidate = discovered_candidate(tmp_path)
    created = client.post(
        "/v1/watches",
        json={
            "candidate_id": candidate["candidate_id"],
            "next_due_at": (T + timedelta(days=2)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    watch_id = created.json()["watch_id"]
    assert (
        client.patch(f"/v1/watches/{watch_id}", json={"muted": True}).status_code == 200
    )
    assert (
        client.patch(f"/v1/watches/{watch_id}", json={"muted": True}).status_code == 200
    )
    assert (
        client.patch(f"/v1/watches/{watch_id}", json={"priority": 5}).status_code == 200
    )

    first = client.get(f"/v1/watches/{watch_id}/history?offset=0&limit=2")
    assert first.status_code == 200, first.text
    assert [entry["sequence"] for entry in first.json()["entries"]] == [1, 2]
    assert [entry["event"]["kind"] for entry in first.json()["entries"]] == [
        "created",
        "muted",
    ]
    assert first.json()["next_offset"] == 2
    last = client.get(f"/v1/watches/{watch_id}/history?offset=2&limit=2")
    assert last.status_code == 200, last.text
    assert [entry["event"]["kind"] for entry in last.json()["entries"]] == [
        "priority_changed"
    ]
    assert last.json()["next_offset"] is None
    current = client.get(f"/v1/watches/{watch_id}")
    assert current.status_code == 200, current.text
    assert current.json()["priority"] == 5


def test_watch_change_summary_uses_recorded_runs_and_preserves_question_lineage(
    tmp_path,
):
    ledger, runtime, client, _, candidate = discovered_candidate(tmp_path)
    epoch = ledger.get_discovery_epoch(candidate["epoch_id"])
    submission = {
        "kind": "run",
        "graph": candidate["graph"],
        "snapshot_ids": {"sales": epoch.source_snapshot_ids[0]},
        "as_of": T.isoformat(),
    }
    run_ids = []
    for key in ("watch-change-before", "watch-change-after"):
        accepted = client.post("/v1/jobs", json={**submission, "key": key})
        assert accepted.status_code == 202, accepted.text
        Worker(runtime, JobQueue(ledger)).run_due(T)
        job = client.get("/v1/jobs/" + accepted.json()["job_id"]).json()
        assert job["state"] == "completed"
        run_ids.append(job["result"]["run_id"])
    created = client.post(
        "/v1/watches",
        json={
            "candidate_id": candidate["candidate_id"],
            "next_due_at": (T + timedelta(days=2)).isoformat(),
        },
    )
    watch_id = created.json()["watch_id"]

    response = client.get(
        f"/v1/watches/{watch_id}/changes",
        params={"previous_run_id": run_ids[0], "current_run_id": run_ids[1]},
    )
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["watch_id"] == watch_id
    assert summary["question"] == candidate["reason"]
    assert summary["dependencies"] == ["sales"]
    assert summary["common_target_count"] > 0
    assert "do not establish causal" in summary["explanation"]
    assert (
        client.get(
            f"/v1/watches/{watch_id}/changes",
            params={"previous_run_id": run_ids[0], "current_run_id": "missing-run"},
        ).status_code
        == 404
    )
