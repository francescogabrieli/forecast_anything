from datetime import timedelta

from test_backtest_api import request, setup, submit

from forecast_anything.jobs import JobQueue
from forecast_anything.worker import Worker


def test_product_backtest_rejects_baseline_but_replays_accepted_key(tmp_path):
    ledger, runtime, _, _, client = setup(tmp_path)
    job_id = submit(client, request())
    runtime.required_provider = "timestral"
    assert client.post("/v1/jobs", json=request()).json()["job_id"] == job_id
    rejected = client.post("/v1/jobs", json=request(key="new-baseline"))
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "required_forecast_provider"


def test_legacy_baseline_queue_fails_terminally_without_new_emissions(tmp_path):
    from test_backtest_api import T

    ledger, runtime, _, _, client = setup(tmp_path)
    job_id = submit(client, request())
    runtime.required_provider = "timestral"
    Worker(runtime, JobQueue(ledger)).run_due(T)
    view = client.get("/v1/jobs/" + job_id).json()
    assert view["state"] == "failed"
    assert view["error"]["code"] == "required_provider_migration"
    assert view["attempt"] == 1
    assert Worker(runtime, JobQueue(ledger)).run_due(T + timedelta(seconds=40)) == ()


def test_legacy_watch_is_paused_with_actionable_migration_reason(tmp_path):
    from test_worker import T, registered_watch
    from test_worker import setup as watch_setup

    ledger, _, runtime = watch_setup(tmp_path)
    registered_watch(tmp_path, ledger)
    runtime.required_provider = "timestral"
    worker = Worker(runtime, JobQueue(ledger))
    assert worker.run_due(T) == ()
    watch = ledger.get_watch("watch")
    assert watch.lifecycle == "paused"
    assert watch.migration_reason == "required_provider_migration"
    assert not watch.operational
    assert (
        ledger.watch_history("watch")[-1]["event"]["kind"]
        == "provider_migration_required"
    )


def test_model_readiness_is_separate_from_liveness(tmp_path):
    _, runtime, _, _, client = setup(tmp_path)
    runtime.required_provider = "timestral"
    assert client.get("/health").json()["status"] == "ok"
    capability = client.get("/v1/capabilities").json()
    assert capability["required_provider"] == "timestral"
    assert capability["model_status"]["status"] == "unavailable"
    assert not capability["model_status"]["ready"]


def test_model_switch_creates_fresh_product_discovery_epoch(tmp_path):
    from test_backtest_api import T

    from forecast_anything.providers.configuration import pinned_timestral_provider

    ledger, runtime, _, _, client = setup(tmp_path)
    service = client.app.state.observatory
    _, old_epoch, old_job = service.profile("sales")
    runtime.providers["timestral"] = pinned_timestral_provider()
    runtime.required_provider = "timestral"
    _, new_epoch, new_job = service.profile("sales")
    assert new_epoch != old_epoch and new_job != old_job
    Worker(runtime, JobQueue(ledger)).run_due(T)
    assert (
        client.get("/v1/jobs/" + old_job).json()["error"]["code"]
        == "required_provider_migration"
    )
    new = client.get("/v1/jobs/" + new_job).json()
    assert new["state"] == "completed", new
    candidate = ledger.get_candidate(new["result"]["candidate_ids"][0])
    assert (
        next(n for n in candidate.graph.nodes if n.node_id == "forecast").config[
            "provider"
        ]
        == "timestral"
    )


def test_explicit_primary_is_preserved_in_scenario(tmp_path):
    """Model double checks output lineage, not Timestral numerical acceptance."""
    from test_worker import T, inputs

    from forecast_anything.api.scenarios import create_scenario
    from forecast_anything.contracts import GraphSpec, Node, ScenarioRequest
    from forecast_anything.providers.baseline import SeasonalNaiveProvider
    from forecast_anything.runtime import Runtime
    from forecast_anything.store import Ledger

    class Model(SeasonalNaiveProvider):
        def capabilities(self):
            return (
                super().capabilities().model_copy(update={"provider_id": "timestral"})
            )

        def forecast(self, request):
            return (
                super()
                .forecast(request)
                .model_copy(update={"provider_id": "timestral"})
            )

    original, snapshots = inputs()
    source = next(n for n in original.nodes if n.node_id == "a")
    g = GraphSpec(
        graph_id="two-models",
        version=1,
        nodes=(
            source,
            *(
                Node(
                    node_id=name,
                    kind="forecast",
                    inputs=("a",),
                    config={
                        "provider": "timestral",
                        "history": "a",
                        "horizon": 1,
                        "frequency": "1h",
                        "relation_type": {"a": "statistical"},
                        "options": {"period": 1},
                    },
                )
                for name in ("f_a", "f_b")
            ),
        ),
    )
    ledger = Ledger(tmp_path / "primary.db", clock=lambda: T)
    runtime = Runtime(
        ledger, {"timestral": Model(1)}, {}, lambda: T, required_provider="timestral"
    )
    parent = runtime.run(
        g, {"a": snapshots["a"]}, T, "primary-parent", primary_node_id="f_a"
    )
    scenario = create_scenario(
        runtime,
        ScenarioRequest(
            base_graph_id=g.graph_id,
            base_version=1,
            label="primary preserved",
            source_overrides={"a": snapshots["a"]},
        ),
    )
    assert parent.primary_node_id == "f_a"
    assert scenario.primary_node_id == "f_a"
    Worker(runtime, JobQueue(ledger)).run_due(T)
    child = ledger.latest_run(scenario.graph_id, 1)
    assert child.primary_node_id == "f_a" and child.parent_run_id == parent.run_id


def test_product_cannot_create_new_watch_from_legacy_baseline_candidate(tmp_path):
    from fastapi.testclient import TestClient
    from test_worker import T, registered_watch
    from test_worker import setup as watch_setup

    from forecast_anything.api.app import create_app

    ledger, _, runtime = watch_setup(tmp_path)
    registered_watch(tmp_path, ledger)
    runtime.required_provider = "timestral"
    client = TestClient(
        create_app(ledger, runtime, "local-test"),
        headers={"Authorization": "Bearer local-test"},
    )
    response = client.post(
        "/v1/watches",
        json={
            "candidate_id": ledger.get_watch("watch").candidate_id,
            "next_due_at": (T + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "required_forecast_provider"
