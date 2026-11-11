"""HTTP evaluation submission and result retrieval."""

from datetime import timedelta

import pytest
from api_fixtures import T, base_run, setup, source

from forecast_anything.jobs import JobQueue
from forecast_anything.worker import Worker


def test_evaluation_actuals_must_belong_to_run_sources(tmp_path):
    ledger, runtime, client, base = base_run(tmp_path)
    other = source(tmp_path)
    other["source_id"] = "other"
    response = client.post("/v1/sources", json=other)
    Worker(runtime, JobQueue(ledger)).run_due(T)
    discovery = client.get("/v1/jobs/" + response.json()["job_id"]).json()
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "evaluation",
            "key": "wrong-actuals",
            "run_id": base["run_id"],
            "actuals_snapshot_id": discovery["result"]["source_snapshot_ids"][0],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "source_snapshot_lineage_mismatch"


@pytest.mark.parametrize("legacy", [False, True])
def test_evaluation_job_reads_real_later_source_actuals(tmp_path, legacy):
    ledger, runtime, client = setup(tmp_path)
    runtime.clock = ledger.clock = lambda: T - timedelta(hours=12)
    spec = source(tmp_path)
    registered = client.post("/v1/sources", json=spec).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    discovery = client.get("/v1/jobs/" + registered["job_id"]).json()["result"]
    candidate = client.get("/v1/candidates/" + discovery["candidate_ids"][0]).json()
    snapshot = client.get("/v1/snapshots/" + discovery["source_snapshot_ids"][0]).json()
    issued = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "evaluated-run",
            "graph": candidate["graph"],
            "snapshot_ids": {"sales": snapshot["snapshot_id"]},
            "as_of": snapshot["as_of"],
        },
    ).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    run_id = client.get("/v1/jobs/" + issued["job_id"]).json()["result"]["run_id"]
    from pathlib import Path

    Path(spec["location"]).write_text(
        "time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n2026-10-24,4\n"
    )
    runtime.clock = ledger.clock = lambda: T + timedelta(days=1)
    refreshed = client.post("/v1/sources", json=spec).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    actuals_id = client.get("/v1/jobs/" + refreshed["job_id"]).json()["result"][
        "source_snapshot_ids"
    ][0]
    body = {
        "kind": "evaluation",
        "key": "evaluate-issued",
        "run_id": run_id,
        "actuals_snapshot_id": actuals_id,
    }
    if legacy:
        job = JobQueue(ledger).enqueue(
            "api/evaluate-issued", {k: v for k, v in body.items() if k != "key"}
        )
    response = client.post("/v1/jobs", json=body)
    if legacy:
        assert response.json()["job_id"] == job.job_id
    assert response.status_code == 202, response.text
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    job = client.get("/v1/jobs/" + response.json()["job_id"]).json()
    assert job["state"] == "completed", job
    evaluation = client.get("/v1/evaluations/" + job["result"]["evaluation_id"]).json()
    assert evaluation["status"] == "evaluated" and evaluation["origin_count"] == 1
    assert evaluation["assumptions"][0].startswith(
        "evaluation=v1;" if legacy else "evaluation=v2;"
    )
    assert (
        client.post("/v1/jobs", json=body).json()["job_id"] == response.json()["job_id"]
    )
    assert evaluation["discovery"] is None
    assert client.get(f"/v1/runs/{run_id}/evaluations").json() == [evaluation]
    assert client.get(f"/v1/runs/{run_id}").json()["evidence_ids"] == []


@pytest.mark.parametrize("forecast_other", [False, True])
def test_evaluation_uses_each_forecasts_history_source(tmp_path, forecast_other):
    from pathlib import Path

    ledger, runtime, client = setup(tmp_path)
    runtime.clock = ledger.clock = lambda: T - timedelta(hours=12)
    spec = source(tmp_path)
    other = {**spec, "source_id": "other"}
    registered = client.post("/v1/sources", json=spec).json()
    other_registered = client.post("/v1/sources", json=other).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    first = client.get("/v1/jobs/" + registered["job_id"]).json()["result"]
    second = client.get("/v1/jobs/" + other_registered["job_id"]).json()["result"]
    candidate = client.get("/v1/candidates/" + first["candidate_ids"][0]).json()
    graph = candidate["graph"]
    graph["graph_id"] = "colliding-series-two-sources"
    source_config = next(
        node["config"] for node in graph["nodes"] if node["kind"] == "source"
    )
    graph["nodes"].append(
        {
            "node_id": "other-source",
            "kind": "source",
            "inputs": [],
            "config": {**source_config, "source_id": "other"},
        }
    )
    if forecast_other:
        forecast = next(node for node in graph["nodes"] if node["kind"] == "forecast")
        graph["nodes"].append(
            {
                "node_id": "other-forecast",
                "kind": "forecast",
                "inputs": ["other-source"],
                "config": {
                    **forecast["config"],
                    "history": "other-source",
                    "relation_type": {"other-source": "statistical"},
                },
            }
        )
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "collision-run",
            "graph": graph,
            "snapshot_ids": {
                "sales": first["source_snapshot_ids"][0],
                "other": second["source_snapshot_ids"][0],
            },
            "as_of": runtime.clock().isoformat(),
        },
    )
    assert response.status_code == 202, response.text
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    run_id = client.get("/v1/jobs/" + response.json()["job_id"]).json()["result"][
        "run_id"
    ]
    Path(spec["location"]).write_text(
        "time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n2026-10-24,99\n"
    )
    runtime.clock = ledger.clock = lambda: T + timedelta(days=1)
    refreshed = client.post("/v1/sources", json=other).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    actuals_id = client.get("/v1/jobs/" + refreshed["job_id"]).json()["result"][
        "source_snapshot_ids"
    ][0]
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "evaluation",
            "key": "wrong-collision-actuals",
            "run_id": run_id,
            "actuals_snapshot_id": actuals_id,
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == (
        "ambiguous_actuals_bindings"
        if forecast_other
        else "source_snapshot_lineage_mismatch"
    )
    with ledger._connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE logical_key='api/wrong-collision-actuals'"
            ).fetchone()[0]
            == 0
        )
    refreshed_base = client.post("/v1/sources", json=spec).json()
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    base_actuals = client.get("/v1/jobs/" + refreshed_base["job_id"]).json()["result"][
        "source_snapshot_ids"
    ][0]
    own_response = client.post(
        "/v1/jobs",
        json={
            "kind": "evaluation",
            "key": "own-collision-actuals",
            "run_id": run_id,
            "actuals_snapshot_id": base_actuals,
        },
    )
    assert own_response.status_code == (422 if forecast_other else 202)
    if forecast_other:
        assert own_response.json()["code"] == "ambiguous_actuals_bindings"


def test_run_evaluations_are_authenticated_scoped_ordered_and_non_mutating(tmp_path):
    from forecast_anything.contracts import EvaluationRecord

    ledger, _, client, base = base_run(tmp_path)
    other = ledger.get_run(base["run_id"]).model_copy(update={"run_id": "other-run"})
    ledger.append_run(other, (), "other-run")
    for evaluation_id, run_id in (
        ("z-evaluation", base["run_id"]),
        ("other-evaluation", "other-run"),
        ("a-evaluation", base["run_id"]),
    ):
        ledger.append_evaluation(
            EvaluationRecord(
                evaluation_id=evaluation_id,
                run_id=run_id,
                actuals_snapshot_id=base["snapshot_ids"][0],
                status="pending",
                metrics={},
                origin_count=0,
                assumptions=(),
            )
        )
    empty = other.model_copy(update={"run_id": "empty-run"})
    ledger.append_run(empty, (), "empty-run")
    assert client.get("/v1/runs/empty-run/evaluations").json() == []
    path = f"/v1/runs/{base['run_id']}/evaluations"
    assert client.get(path, headers={"Authorization": ""}).status_code == 401
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert [item["evaluation_id"] for item in response.json()] == [
        "a-evaluation",
        "z-evaluation",
    ]
    assert all(item["run_id"] == base["run_id"] for item in response.json())
    assert client.get("/v1/runs/missing/evaluations").status_code == 404
    assert client.get(f"/v1/runs/{base['run_id']}").json() == base
