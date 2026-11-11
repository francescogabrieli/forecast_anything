"""Source profiling, refresh, and preview through HTTP."""

from datetime import timedelta

from api_fixtures import T, setup, source
from fastapi.testclient import TestClient

from forecast_anything.jobs import JobQueue
from forecast_anything.worker import Worker


def test_sources_are_write_only_and_discovery_is_provisional(tmp_path):
    ledger, runtime, client = setup(tmp_path)
    spec = source(tmp_path)
    spec["secret_ref"] = "private-secret-reference"
    # Registering credentials must not disclose them, even when inspection fails.
    response = client.post("/v1/sources", json=spec)
    assert "private-secret-reference" not in response.text
    assert "private-secret-reference" not in client.get("/v1/sources").text
    config = client.get(f"/v1/sources/{spec['source_id']}/configuration")
    assert config.status_code == 200
    assert config.json()["location"] == spec["location"]
    assert config.json()["mapping"] == spec["mapping"]
    assert config.json()["has_secret_ref"] is True
    assert "private-secret-reference" not in config.text
    assert (
        client.get(
            f"/v1/sources/{spec['source_id']}/configuration",
            headers={"Authorization": ""},
        ).status_code
        == 401
    )
    spec["secret_ref"] = None
    response = client.post("/v1/sources", json=spec)
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get("/v1/jobs/" + response.json()["job_id"]).json()
    candidate_id = job["result"]["candidate_ids"][0]
    watch = client.post(
        "/v1/watches",
        json={
            "candidate_id": candidate_id,
            "next_due_at": (T + timedelta(hours=1)).isoformat(),
        },
    )
    assert watch.status_code == 201, watch.text
    assert watch.json()["quality"] == "provisional"
    assert not watch.json()["operational"]
    assert (
        client.patch(
            "/v1/watches/" + watch.json()["watch_id"], json={"kind": "resumed"}
        ).status_code
        == 422
    )


def test_source_profile_retry_is_idempotent_across_clock_changes(tmp_path):
    ledger, runtime, client = setup(tmp_path)
    created = client.post("/v1/sources", json=source(tmp_path))
    assert created.status_code == 201
    runtime.clock = ledger.clock = lambda: T + timedelta(minutes=1)
    assert client.get("/v1/sources/sales/profile").status_code == 200
    assert (
        client.post("/v1/sources", json=source(tmp_path)).json()["job_id"]
        == created.json()["job_id"]
    )


def test_explicit_source_refresh_captures_new_data_beyond_profile_sample(tmp_path):
    from pathlib import Path

    ledger, runtime, client = setup(tmp_path)
    spec = source(tmp_path)
    spec["mapping"]["available_at"] = "time"
    path = Path(spec["location"])
    start = T - timedelta(days=120)
    rows = [f"{(start + timedelta(days=i)).date()},{i}" for i in range(120)]
    path.write_text("time,value\n" + "\n".join(rows) + "\n")
    registered = client.post("/v1/sources", json=spec).json()
    Worker(runtime, JobQueue(ledger)).run_due(T)
    original_job = client.get(f"/v1/jobs/{registered['job_id']}").json()
    original_id = original_job["result"]["source_snapshot_ids"][0]

    with path.open("a") as stream:
        stream.write("2026-10-24,999\n")
    runtime.clock = ledger.clock = lambda: T + timedelta(days=1)
    assert (
        client.post("/v1/sources", json=spec).json()["job_id"] == registered["job_id"]
    )
    request = {"key": "refresh-1"}
    refreshed = client.post("/v1/sources/sales/refresh", json=request)
    assert refreshed.status_code == 202, refreshed.text
    assert refreshed.json()["job_id"] != registered["job_id"]
    assert (
        client.post("/v1/sources/sales/refresh", json=request).json()["job_id"]
        == refreshed.json()["job_id"]
    )
    Worker(runtime, JobQueue(ledger)).run_due(runtime.clock())
    result = client.get(f"/v1/jobs/{refreshed.json()['job_id']}").json()["result"]
    new_id = result["source_snapshot_ids"][0]
    assert new_id != original_id
    assert len(client.get(f"/v1/snapshots/{original_id}").json()["observations"]) == 120
    assert (
        client.get(f"/v1/snapshots/{new_id}").json()["observations"][-1]["value"] == 999
    )
    assert (
        TestClient(client.app)
        .post("/v1/sources/sales/refresh", json=request)
        .status_code
        == 401
    )
    spec["mapping"]["unit"] = {"constant": "items"}
    assert client.post("/v1/sources", json=spec).status_code == 201
    conflict = client.post("/v1/sources/sales/refresh", json=request)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"


def test_source_refresh_retry_reuses_original_profile_after_data_changes(tmp_path):
    from pathlib import Path

    _, _, client = setup(tmp_path)
    spec = source(tmp_path)
    assert client.post("/v1/sources", json=spec).status_code == 201
    first = client.post("/v1/sources/sales/refresh", json={"key": "retry"})
    assert first.status_code == 202
    path = Path(spec["location"])
    path.write_text(path.read_text() + "2026-10-24,4\n")
    retry = client.post("/v1/sources/sales/refresh", json={"key": "retry"})
    assert retry.status_code == 202, retry.text
    assert retry.json() == first.json()
    path.unlink()
    assert (
        client.post("/v1/sources/sales/refresh", json={"key": "retry"}).json()
        == first.json()
    )


def test_unavailable_source_is_sanitized_domain_error(tmp_path):
    _, _, client = setup(tmp_path)
    spec = source(tmp_path)
    spec["location"] = str(tmp_path / "private-nonexistent-file.csv")
    response = client.post("/v1/sources", json=spec)
    assert response.status_code == 422
    assert response.json()["code"] == "source_unavailable"
    assert "private-nonexistent" not in response.text


def test_source_preview_does_not_register_or_enqueue(tmp_path):
    ledger, _, client = setup(tmp_path)
    spec = source(tmp_path)
    spec["mapping"].pop("unit")

    response = client.post("/v1/sources/preview", json=spec)

    assert response.status_code == 200, response.text
    profile = response.json()
    assert "unit" in profile["unresolved"]
    assert profile["source_id"] == "sales"
    assert client.get("/v1/sources").json() == []
    with ledger._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_source_preview_mapping_is_saved_and_read_back(tmp_path):
    _, _, client = setup(tmp_path)
    spec = source(tmp_path)

    preview = client.post("/v1/sources/preview", json=spec)
    assert preview.status_code == 200, preview.text
    saved = client.post("/v1/sources", json=spec)
    assert saved.status_code == 201, saved.text
    reread = client.get("/v1/sources/sales/profile")

    assert reread.status_code == 200
    assert reread.json() == preview.json()
    assert saved.json()["profile"] == reread.json()
