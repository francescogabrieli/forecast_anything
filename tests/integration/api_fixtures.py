"""Shared setup for authenticated HTTP integration tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.jobs import JobQueue
from forecast_anything.operators import register_builtin_operators
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.worker import Worker

T = datetime(2026, 10, 24, tzinfo=UTC)
AUTH = {"Authorization": "Bearer test-token"}


def setup(tmp_path):
    ledger = Ledger(tmp_path / "state.db", clock=lambda: T)
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        register_builtin_operators(),
        lambda: T,
    )
    return (
        ledger,
        runtime,
        TestClient(create_app(ledger, runtime, "test-token"), headers=AUTH),
    )


def source(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n")
    return {
        "source_id": "sales",
        "kind": "csv",
        "location": str(path),
        "refresh_seconds": 60,
        "mapping": {
            "event_time": "time",
            "value": "value",
            "available_at": {"constant": "2026-10-23"},
            "revision": {"constant": "1"},
            "series_id": {"constant": "sales"},
            "unit": {"constant": "count"},
            "frequency": {"constant": "1d"},
            "timezone": {"constant": "UTC"},
            "calendar": {"constant": "gregorian"},
            "missing_values": {"constant": [""]},
        },
    }


def base_run(tmp_path):
    ledger, runtime, client = setup(tmp_path)
    registration = client.post("/v1/sources", json=source(tmp_path))
    assert registration.status_code == 201, registration.text
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get("/v1/jobs/" + registration.json()["job_id"]).json()
    candidate = client.get("/v1/candidates/" + job["result"]["candidate_ids"][0]).json()
    epoch = ledger.get_discovery_epoch(candidate["epoch_id"])
    response = client.post(
        "/v1/jobs",
        json={
            "kind": "run",
            "key": "base",
            "graph": candidate["graph"],
            "snapshot_ids": {"sales": epoch.source_snapshot_ids[0]},
            "as_of": T.isoformat(),
        },
    )
    assert response.status_code == 202, response.text
    Worker(runtime, JobQueue(ledger)).run_due(T)
    run_id = client.get("/v1/jobs/" + response.json()["job_id"]).json()["result"][
        "run_id"
    ]
    return ledger, runtime, client, client.get("/v1/runs/" + run_id).json()


def discovered_candidate(tmp_path):
    ledger, runtime, client = setup(tmp_path)
    registration = client.post("/v1/sources", json=source(tmp_path))
    assert registration.status_code == 201, registration.text
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get("/v1/jobs/" + registration.json()["job_id"]).json()
    candidate = client.get("/v1/candidates/" + job["result"]["candidate_ids"][0]).json()
    return ledger, runtime, client, registration.json(), candidate
