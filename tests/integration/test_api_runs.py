"""HTTP graph and run validation and scenario lineage."""

from datetime import timedelta

from api_fixtures import T, base_run, setup, source

from forecast_anything.contracts import Observation
from forecast_anything.jobs import JobQueue
from forecast_anything.temporal import freeze
from forecast_anything.worker import Worker


def test_invalid_plan_does_not_enqueue(tmp_path):
    ledger, _, client = setup(tmp_path)
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "bad",
            "graph": {
                "graph_id": "bad",
                "version": 1,
                "nodes": [
                    {"node_id": "bad", "kind": "forecast", "inputs": [], "config": {}}
                ],
            },
            "snapshot_ids": {},
            "as_of": T.isoformat(),
        },
    )
    assert response.status_code == 422
    with ledger._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_scenario_does_not_rewrite_base(tmp_path):
    ledger, runtime, client, base = base_run(tmp_path)
    snapshot_id = base["snapshot_ids"][0]
    original = client.get("/v1/snapshots/" + snapshot_id).json()
    override = {
        **original,
        "observations": [{**o, "value": 100} for o in original["observations"]],
    }
    request = {
        "base_graph_id": base["graph_id"],
        "base_version": 1,
        "label": "Higher sales",
        "source_overrides": {"sales": override},
    }
    response = client.post("/v1/scenarios", json=request)
    assert response.status_code == 201, response.text
    scenario = response.json()
    assert scenario["parent_run_id"] == base["run_id"]
    assert scenario["graph_id"] != base["graph_id"]
    assert client.post("/v1/scenarios", json=request).json() == scenario
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get("/v1/jobs/" + scenario["job_id"]).json()
    run = client.get("/v1/runs/" + job["result"]["run_id"]).json()
    assert run["scenario_id"] == scenario["scenario_id"]
    assert run["parent_run_id"] == base["run_id"]
    assert "assumed" in str(
        client.get("/v1/snapshots/" + run["snapshot_ids"][0]).json()["assumptions"]
    )
    assert client.get("/v1/snapshots/" + snapshot_id).json() == original
    assert client.get("/v1/runs/" + base["run_id"]).json() == base
    from forecast_anything.evaluation.records import evaluate_run

    actuals = freeze(
        (
            Observation(
                series_id="sales",
                event_time=T + timedelta(days=1),
                available_at=T + timedelta(days=1),
                revision="1",
                value=100,
                unit="count",
            ),
        ),
        T + timedelta(days=1),
    )
    result = evaluate_run(
        ledger.get_run(run["run_id"]),
        actuals,
        ledger.get_graph(scenario["graph_id"], 1),
    )
    assert result.status == "insufficient_evidence" and result.origin_count == 0


def test_existing_graph_cannot_be_rebound_before_enqueue(tmp_path):
    ledger, _, client, base = base_run(tmp_path)
    graph = ledger.get_graph(base["graph_id"], 1).model_dump(mode="json")
    graph["nodes"][1]["config"]["options"]["period"] = 1
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "overwrite",
            "graph": graph,
            "snapshot_ids": {"sales": base["snapshot_ids"][0]},
            "as_of": T.isoformat(),
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "immutable_identity"
    with ledger._connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE logical_key='api/overwrite'"
            ).fetchone()[0]
            == 0
        )


def test_untrusted_candidate_cannot_supply_evidence_or_execution_graph(tmp_path):
    _, _, client = setup(tmp_path)
    spec = source(tmp_path)
    assert client.post("/v1/sources", json=spec).status_code == 201
    proposal = {
        "template_id": "forecast_change",
        "source_ids": ["sales"],
        "reason": "See changes",
    }
    candidate = client.post("/v1/candidates", json=proposal)
    assert candidate.status_code == 201
    assert (
        client.post(
            "/v1/candidates", json={**proposal, "graph": candidate.json()["graph"]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/v1/watches",
            json={
                "candidate_id": candidate.json()["candidate_id"],
                "next_due_at": T.isoformat(),
                "eligibility_decision": {"action": "activate"},
            },
        ).status_code
        == 422
    )


def test_scenario_rejects_unknown_sources_and_forged_base(tmp_path):
    _, _, client, base = base_run(tmp_path)
    original = client.get("/v1/snapshots/" + base["snapshot_ids"][0]).json()
    response = client.post(
        "/v1/scenarios",
        json={
            "base_graph_id": base["graph_id"],
            "base_version": 1,
            "label": "bad",
            "source_overrides": {"unknown": original},
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_scenario_overrides"
    response = client.post(
        "/v1/scenarios",
        json={
            "base_graph_id": "missing",
            "base_version": 1,
            "label": "bad",
            "source_overrides": {"sales": original},
        },
    )
    assert response.status_code == 404


def test_job_key_cannot_be_reused_with_different_plan(tmp_path):
    ledger, _, client, base = base_run(tmp_path)
    graph = ledger.get_graph(base["graph_id"], 1).model_dump(mode="json")
    request = {
        "kind": "run",
        "key": "repeated",
        "graph": graph,
        "snapshot_ids": {"sales": base["snapshot_ids"][0]},
        "as_of": T.isoformat(),
    }
    response = client.post("/v1/jobs", json=request)
    assert response.status_code == 202
    assert (
        client.post("/v1/jobs", json=request).json()["job_id"]
        == response.json()["job_id"]
    )
    graph["graph_id"] = "different-graph"
    assert client.post("/v1/jobs", json=request).status_code == 409


def test_run_snapshot_binding_must_belong_to_registered_source(tmp_path):
    ledger, runtime, client, base = base_run(tmp_path)
    other = source(tmp_path)
    other["source_id"] = "other"
    response = client.post("/v1/sources", json=other)
    assert response.status_code == 201
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get("/v1/jobs/" + response.json()["job_id"]).json()
    snapshot_id = job["result"]["source_snapshot_ids"][0]
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "wrong-source",
            "graph": ledger.get_graph(base["graph_id"], 1).model_dump(mode="json"),
            "snapshot_ids": {"sales": snapshot_id},
            "as_of": T.isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "source_snapshot_lineage_mismatch"
