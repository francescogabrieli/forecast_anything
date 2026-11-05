"""Real authenticated API, SQLite and leased-worker evidence boundaries."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.contracts import SourceSpec
from forecast_anything.jobs import JobQueue
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.sources.catalog import SourceCatalog
from forecast_anything.sources.profiling import ingest_source
from forecast_anything.store import Ledger
from forecast_anything.worker import Worker

T = datetime(2026, 1, 20, tzinfo=timezone.utc)
AUTH = {"Authorization": "Bearer test-token"}


def setup(tmp_path, *, assumptions=(), kind="csv"):
    path = tmp_path / "private.csv"
    path.write_text(
        "time,value\n" + "".join(f"2026-01-{i:02}, {i}\n" for i in range(1, 17))
    )
    spec = SourceSpec(
        source_id="sales",
        kind=kind,
        location=str(path),
        refresh_seconds=60,
        mapping={
            "event_time": "time",
            "available_at": "time",
            "value": "value",
            "revision": {"constant": "a"},
            "series_id": {"constant": "sales"},
            "unit": {"constant": "count"},
            "frequency": {"constant": "D"},
            "timezone": {"constant": "UTC"},
            "calendar": {"constant": "gregorian"},
            "missing_values": {"constant": [""]},
        },
    )
    ledger = Ledger(tmp_path / "state.db", clock=lambda: T)
    runtime = Runtime(
        ledger, {"seasonal_naive": SeasonalNaiveProvider(99)}, {}, lambda: T
    )
    catalog = SourceCatalog(ledger.path)
    revision = catalog.append(spec, assumptions)
    client = TestClient(create_app(ledger, runtime, "test-token"), headers=AUTH)
    return ledger, runtime, catalog, revision, client


def request(kind="backtest", **changes):
    return {
        "kind": kind,
        "key": "evidence",
        "source_id": "sales",
        "selection": {
            "provider": "seasonal_naive",
            "horizon": 2,
            "options": {"period": 2},
        },
        **changes,
    }


def submit(client, body):
    response = client.post("/v1/jobs", json=body)
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


def test_backtest_job_publishes_manual_scores_and_bounded_immutable_reads(tmp_path):
    ledger, runtime, _, revision, client = setup(tmp_path)
    job_id = submit(client, request())
    for path in (f"/v1/backtests/{job_id}", f"/v1/backtests/{job_id}/origins"):
        assert client.get(path).status_code == 404
        assert client.get(path, headers={"Authorization": ""}).status_code == 401
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["state"] == "completed", job
    assert job["result"]["backtest_id"] == job_id
    report = client.get(f"/v1/backtests/{job_id}")
    assert report.status_code == 200, report.text
    value = report.json()
    assert value["source_revision"] == revision.revision
    assert value["status"] == "completed"
    final = value["partitions"][2]
    assert (final["planned"], final["evaluated"], final["matched_count"]) == (2, 2, 4)
    assert (final["model_mae"], final["baseline_mae"]) == (2, 1.5)
    assert "observations" not in report.text and "private.csv" not in report.text
    first = client.get(f"/v1/backtests/{job_id}/origins?limit=2").json()
    assert [o["ordinal"] for o in first["origins"]] == [0, 1]
    assert first["next_offset"] == 2
    last = client.get(f"/v1/backtests/{job_id}/origins?offset=6&limit=2").json()
    assert [o["ordinal"] for o in last["origins"]] == [6]
    assert last["next_offset"] is None
    huge_offset = 2**63
    huge = client.get(f"/v1/backtests/{job_id}/origins?offset={huge_offset}&limit=2")
    assert huge.status_code == 200
    assert huge.json() == {
        "backtest_id": job_id,
        "origins": [],
        "offset": huge_offset,
        "limit": 2,
        "next_offset": None,
    }
    for query in ("offset=-1", "limit=0", "limit=51"):
        assert client.get(f"/v1/backtests/{job_id}/origins?{query}").status_code == 422
    before = ledger.events_after(0, 1000)
    assert client.get(f"/v1/backtests/{job_id}").json() == value
    assert client.get(f"/v1/backtests/{job_id}/origins?limit=2").json() == first
    assert ledger.events_after(0, 1000) == before


def test_configured_run_uses_historical_snapshot_vintage_without_source_io(tmp_path):
    ledger, runtime, catalog, revision, client = setup(tmp_path)
    snapshot = ingest_source(revision.spec, T)
    ledger.put_snapshot(snapshot)
    catalog.append(
        revision.spec.model_copy(
            update={
                "mapping": {**revision.spec.mapping, "frequency": {"constant": "H"}}
            }
        )
    )
    Path(revision.spec.location).unlink()
    body = request("configured_run", snapshot_id=snapshot.snapshot_id)
    job_id = submit(client, body)
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["state"] == "completed", job
    run = ledger.get_run(job["result"]["run_id"])
    assert run.results["model"].point == ((15.0, 16.0),)
    assert run.results["baseline"].point == ((16.0, 16.0),)
    assert len(run.results["model"].timestamps) == 2
    assert run.results["model"].timestamps[0] == datetime(
        2026, 1, 17, tzinfo=timezone.utc
    )
    runtime.providers.clear()
    assert submit(client, body) == job_id


@pytest.mark.parametrize("kind", ["configured_run", "backtest"])
def test_replay_compares_original_typed_request_before_catalog_and_provider(
    tmp_path, kind
):
    ledger, runtime, catalog, revision, client = setup(tmp_path)
    snapshot = ingest_source(revision.spec, T)
    ledger.put_snapshot(snapshot)
    body = request(
        kind,
        **({"snapshot_id": snapshot.snapshot_id} if kind == "configured_run" else {}),
    )
    body["selection"]["options"]["flag"] = True
    job_id = submit(client, body)
    queue = JobQueue(ledger)
    leased = queue.claim("checkpoint", T, 60)
    queue.checkpoint(leased, {"kind": "unrelated-checkpoint"}, T)
    catalog.append(revision.spec.model_copy(update={"kind": "http_json"}))
    Path(revision.spec.location).unlink()
    runtime.providers.clear()
    assert submit(client, body) == job_id
    body["selection"]["options"]["flag"] = 1
    assert client.post("/v1/jobs", json=body).status_code == 409
    body["selection"]["options"]["flag"] = 1.0
    assert client.post("/v1/jobs", json=body).status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"selection": {"provider": "missing", "horizon": 2}},
        {"selection": {"provider": "seasonal_naive", "horizon": 0}},
        {"selection": {"provider": "seasonal_naive", "horizon": True}},
        {"settings": {"max_origins_per_partition": 51}},
        {"settings": {"origin_offset_seconds": 86400}},
    ],
)
def test_invalid_submission_does_not_enqueue(tmp_path, change):
    ledger, _, _, _, client = setup(tmp_path)
    assert client.post("/v1/jobs", json=request(**change)).status_code == 422
    with ledger._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_http_source_is_rejected_before_io(tmp_path):
    _, _, _, revision, client = setup(tmp_path, kind="http_json")
    Path(revision.spec.location).unlink()
    response = client.post("/v1/jobs", json=request())
    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_backtest_source"


@pytest.mark.parametrize("kind", ["backtest", "configured_run"])
def test_assumed_input_is_rejected(tmp_path, kind):
    ledger, _, _, revision, client = setup(tmp_path, assumptions=("assumed:scenario",))
    snapshot = ingest_source(revision.spec, T)
    snapshot = snapshot.model_copy(
        update={"assumptions": (*snapshot.assumptions, "assumed:scenario")}
    )
    ledger.put_snapshot(snapshot)
    body = request(
        kind,
        **({"snapshot_id": snapshot.snapshot_id} if kind == "configured_run" else {}),
    )
    response = client.post("/v1/jobs", json=body)
    assert response.status_code == 422
    assert response.json()["code"] in {"assumed_backtest_input", "scenario_required"}


@pytest.mark.parametrize("lineage", ["missing", "ambiguous"])
def test_configured_run_rejects_untrusted_snapshot_lineage(tmp_path, lineage):
    ledger, _, catalog, revision, client = setup(tmp_path)
    snapshot = ingest_source(revision.spec, T)
    assumptions = ()
    if lineage == "ambiguous":
        other = catalog.append(
            revision.spec.model_copy(update={"refresh_seconds": 120})
        )
        assumptions = (*snapshot.assumptions, f"source_revision={other.revision}")
    snapshot = snapshot.model_copy(
        update={"snapshot_id": lineage, "assumptions": assumptions}
    )
    ledger.put_snapshot(snapshot)
    response = client.post(
        "/v1/jobs", json=request("configured_run", snapshot_id=snapshot.snapshot_id)
    )
    assert response.status_code == 422
    assert response.json()["code"] == "source_snapshot_lineage_mismatch"


def test_revision_changed_between_submission_and_worker_fails_without_io(tmp_path):
    ledger, runtime, catalog, revision, client = setup(tmp_path)
    job_id = submit(client, request())
    catalog.append(revision.spec.model_copy(update={"refresh_seconds": 120}))
    Path(revision.spec.location).unlink()
    Worker(runtime, JobQueue(ledger)).run_due(T, limit=1)
    error = JobQueue(ledger).history(job_id)[0]["error"]
    assert error["code"] == "source_revision_changed"
    assert "private" not in str(error)


@pytest.mark.parametrize("kind", ["backtest", "configured_run"])
def test_existing_other_job_kind_conflicts_before_dependencies(tmp_path, kind):
    ledger, runtime, _, _, client = setup(tmp_path)
    JobQueue(ledger).enqueue(
        "api/evidence", {"kind": "watch_resume", "watch_id": "absent"}
    )
    runtime.providers.clear()
    response = client.post(
        "/v1/jobs",
        json=request(
            kind, **({"snapshot_id": "absent"} if kind == "configured_run" else {})
        ),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_conflict"


@pytest.mark.parametrize("kind", ["backtest", "configured_run"])
def test_missing_provider_is_rejected_without_source_io(tmp_path, kind):
    ledger, runtime, _, revision, client = setup(tmp_path)
    snapshot = ingest_source(revision.spec, T)
    ledger.put_snapshot(snapshot)
    runtime.providers.clear()
    Path(revision.spec.location).unlink()
    response = client.post(
        "/v1/jobs",
        json=request(
            kind,
            **(
                {"snapshot_id": snapshot.snapshot_id}
                if kind == "configured_run"
                else {}
            ),
        ),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "unknown_provider"


def test_wrong_source_snapshot_is_rejected(tmp_path):
    ledger, _, catalog, revision, client = setup(tmp_path)
    other = catalog.append(revision.spec.model_copy(update={"source_id": "other"}))
    snapshot = ingest_source(other.spec, T)
    ledger.put_snapshot(snapshot)
    response = client.post(
        "/v1/jobs", json=request("configured_run", snapshot_id=snapshot.snapshot_id)
    )
    assert response.status_code == 422
    assert response.json()["code"] == "source_snapshot_lineage_mismatch"


def test_configured_http_snapshot_executes_without_raw_reads_or_network(
    tmp_path, monkeypatch
):
    from forecast_anything.temporal import freeze

    ledger, runtime, catalog, revision, client = setup(tmp_path)
    csv_snapshot = ingest_source(revision.spec, T)
    http_vintage = catalog.append(
        revision.spec.model_copy(
            update={
                "kind": "http_json",
                "location": "https://example.invalid/private-endpoint",
            }
        )
    )
    snapshot = freeze(
        csv_snapshot.observations, T, (f"source_revision={http_vintage.revision}",)
    )
    ledger.put_snapshot(snapshot)
    Path(revision.spec.location).unlink()

    def forbidden(*args, **kwargs):
        pytest.fail("configured forecast attempted raw source or network I/O")

    monkeypatch.setattr(
        "forecast_anything.backtesting.service.read_observations", forbidden
    )
    monkeypatch.setattr(
        "forecast_anything.sources.profiling.read_observations", forbidden
    )
    monkeypatch.setattr("forecast_anything.sources.profiling.load_http_json", forbidden)
    monkeypatch.setattr(
        "forecast_anything.connectors.http_json.build_opener", forbidden
    )
    body = request("configured_run", snapshot_id=snapshot.snapshot_id)
    job_id = submit(client, body)
    Worker(runtime, JobQueue(ledger)).run_due(T)
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["state"] == "completed", job
    run = ledger.get_run(job["result"]["run_id"])
    assert run.results["model"].point == ((15.0, 16.0),)
    assert ledger.run_bindings(run.run_id) == {"sales": snapshot.snapshot_id}
    assert ledger.get_snapshot(snapshot.snapshot_id).assumptions == (
        f"source_revision={http_vintage.revision}",
    )
    assert (
        client.post("/v1/jobs", json=request(key="http-backtest")).json()["code"]
        == "unsupported_backtest_source"
    )


@pytest.mark.parametrize("changed_body", [False, True])
def test_competing_submission_uses_first_revision_only_for_same_original_body(
    tmp_path, monkeypatch, changed_body
):
    from forecast_anything.backtesting import service

    ledger, _, catalog, revision, client = setup(tmp_path)
    real_payload = service.backtest_payload
    winners = []

    def interleaved(*args):
        # Both callers passed replay preflight with no original job. The inner
        # caller inserts R1 before the outer caller resolves the updated R2.
        monkeypatch.setattr(service, "backtest_payload", real_payload)
        winners.append(submit(client, request()))
        catalog.append(revision.spec.model_copy(update={"refresh_seconds": 120}))
        return real_payload(*args)

    monkeypatch.setattr(service, "backtest_payload", interleaved)
    body = (
        request(selection={"provider": "seasonal_naive", "horizon": 3})
        if changed_body
        else request()
    )
    response = client.post("/v1/jobs", json=body)
    assert response.status_code == (409 if changed_body else 202), response.text
    if not changed_body:
        assert response.json()["job_id"] == winners[0]
    queue = JobQueue(ledger)
    assert queue.original_payload(winners[0])["source_revision"] == revision.revision
    with ledger._connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
