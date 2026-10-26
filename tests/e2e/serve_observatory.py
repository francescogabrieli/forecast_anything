"""Start an authenticated deterministic API and worker for console E2E tests."""

from __future__ import annotations

import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi.testclient import TestClient

from forecast_anything.api.app import create_app
from forecast_anything.jobs import JobQueue
from forecast_anything.operators import register_builtin_operators
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.worker import Worker

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)
TOKEN = "local-e2e-token"


def seed(ledger: Ledger, runtime: Runtime) -> None:
    csv_path = Path("/private/tmp/forecast-anything-console-e2e.csv")
    csv_path.write_text(
        "time,value\n2026-10-21,1\n2026-10-22,2\n2026-10-23,3\n", encoding="utf-8"
    )
    source = {
        "source_id": "sales",
        "kind": "csv",
        "location": str(csv_path),
        "refresh_seconds": 3600,
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
    app = create_app(ledger, runtime, TOKEN, console_origins=("http://127.0.0.1:4173",))
    worker = Worker(runtime, JobQueue(ledger))
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:
        registration = client.post("/v1/sources", json=source)
        assert registration.status_code == 201, registration.text
        worker.run_due(NOW)
        job = client.get(f"/v1/jobs/{registration.json()['job_id']}").json()
        candidate_id = job["result"]["candidate_ids"][0]
        candidate = client.get(f"/v1/candidates/{candidate_id}").json()
        epoch = ledger.get_discovery_epoch(candidate["epoch_id"])
        submitted = client.post(
            "/v1/jobs",
            json={
                "kind": "run",
                "key": "console-e2e-base",
                "graph": candidate["graph"],
                "snapshot_ids": {"sales": epoch.source_snapshot_ids[0]},
                "as_of": NOW.isoformat(),
            },
        )
        assert submitted.status_code == 202, submitted.text
        worker.run_due(NOW)
        created = client.post(
            "/v1/watches",
            json={
                "candidate_id": candidate_id,
                "next_due_at": "2026-10-25T00:00:00Z",
            },
        )
        assert created.status_code == 201, created.text


def main() -> None:
    data_dir = Path(tempfile.mkdtemp(prefix="forecast-anything-console-e2e-"))
    ledger = Ledger(data_dir / "state.db", clock=lambda: NOW)
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(1)},
        register_builtin_operators(),
        lambda: NOW,
    )
    seed(ledger, runtime)
    app = create_app(ledger, runtime, TOKEN, console_origins=("http://127.0.0.1:4173",))
    worker = Worker(runtime, JobQueue(ledger))

    def run_worker() -> None:
        while True:
            worker.run_due(NOW)
            time.sleep(0.2)

    threading.Thread(target=run_worker, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
