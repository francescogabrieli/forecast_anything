"""Start the real local API/worker with deterministic two-source E2E inputs."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
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

ISSUED = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
TOKEN = "local-e2e-token"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class FixtureKnownFutureProvider(SeasonalNaiveProvider):
    """Test-only adapter: repeat history, then add the declared activity signal.

    Production seasonal naive deliberately rejects known_future. This adapter
    keeps its real seasonal calculation and adds one deterministic fixture value
    per target; it makes no claim about production support or predictive quality.
    Single-source candidate/watch requests use seasonal naive unchanged.
    """

    def capabilities(self):
        return super().capabilities().model_copy(update={"supports_known_future": True})

    def forecast(self, request):
        result = super().forecast(request.model_copy(update={"known_future": None}))
        if request.known_future is None:
            return result
        signal = {
            item.event_time: item.value for item in request.known_future.observations
        }
        return result.model_copy(
            update={
                "point": tuple(
                    tuple(
                        value + signal[target]
                        for value, target in zip(row, result.timestamps)
                    )
                    for row in result.point
                ),
                "assumptions": (
                    *result.assumptions,
                    "test fixture: additive known-future activity signal",
                ),
            }
        )


def source_spec(source_id: str, filename: str) -> dict:
    return {
        "source_id": source_id,
        "kind": "csv",
        "location": str(FIXTURES / filename),
        "refresh_seconds": 86400,
        "mapping": {
            "event_time": "time",
            "value": "value",
            "available_at": {"constant": "2026-10-23"},
            "revision": {"constant": "1"},
            "series_id": {"constant": source_id},
            "unit": {"constant": "count"},
            "frequency": {"constant": "1d"},
            "timezone": {"constant": "UTC"},
            "calendar": {"constant": "gregorian"},
            "missing_values": {"constant": [""]},
        },
    }


def write_usability_fixture(directory: Path, now: datetime) -> Path:
    """Write a deterministic daily series whose last point is current."""
    first_day = now.date() - timedelta(days=2)
    path = directory / "usability.csv"
    rows = ["time,value"]
    rows.extend(
        f"{first_day + timedelta(days=offset)},{offset + 1}" for offset in range(3)
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def seed(ledger: Ledger, runtime: Runtime, clock: list[datetime]) -> None:
    app = create_app(ledger, runtime, TOKEN, console_origins=("http://127.0.0.1:4173",))
    worker = Worker(runtime, JobQueue(ledger))
    with TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"}) as client:

        def complete(request):
            assert request.status_code in (201, 202), request.text
            worker.run_due(clock[0])
            job = client.get(f"/v1/jobs/{request.json()['job_id']}").json()
            assert job["state"] == "completed", job
            return job["result"]

        history = complete(
            client.post("/v1/sources", json=source_spec("sales", "console-e2e.csv"))
        )
        activity = complete(
            client.post(
                "/v1/sources", json=source_spec("activity", "console-e2e-activity.csv")
            )
        )
        candidate = client.get(f"/v1/candidates/{history['candidate_ids'][0]}").json()
        graph = candidate["graph"]
        graph["graph_id"] = "console-two-source-base"
        graph["nodes"].append(
            {
                "node_id": "activity",
                "kind": "source",
                "inputs": [],
                "config": {
                    "source_id": "activity",
                    "series_ids": ["activity"],
                    "units": ["count"],
                    "frequency": "1d",
                },
            }
        )
        for node in graph["nodes"]:
            if node["kind"] == "forecast":
                node["inputs"].append("activity")
                node["config"]["known_future"] = "activity"
                node["config"]["relation_type"]["activity"] = "statistical"
        base = complete(
            client.post(
                "/v1/jobs",
                json={
                    "kind": "run",
                    "key": "console-e2e-base",
                    "graph": graph,
                    "snapshot_ids": {
                        "sales": history["source_snapshot_ids"][0],
                        "activity": activity["source_snapshot_ids"][0],
                    },
                    "as_of": ISSUED.isoformat(),
                },
            )
        )
        clock[0] = NOW
        actuals_spec = source_spec("sales", "console-e2e-actuals.csv")
        actuals_spec["mapping"]["available_at"] = "available_at"
        actuals = complete(client.post("/v1/sources", json=actuals_spec))
        evaluation = complete(
            client.post(
                "/v1/jobs",
                json={
                    "kind": "evaluation",
                    "key": "console-e2e-evaluate",
                    "run_id": base["run_id"],
                    "actuals_snapshot_id": actuals["source_snapshot_ids"][0],
                },
            )
        )
        record = client.get(f"/v1/evaluations/{evaluation['evaluation_id']}").json()
        assert record["status"] == "evaluated", record
        # Candidate/watch contracts intentionally remain single-source. The
        # browser will revise sales and the real worker will create its successor.
        created = client.post(
            "/v1/watches",
            json={
                "candidate_id": actuals["candidate_ids"][0],
                "next_due_at": "2026-10-25T12:00:00Z",
            },
        )
        assert created.status_code == 201, created.text


def main() -> None:
    data_dir = Path(tempfile.mkdtemp(prefix="forecast-anything-console-e2e-"))
    clock = [ISSUED]
    ledger = Ledger(data_dir / "state.db", clock=lambda: clock[0])
    runtime = Runtime(
        ledger,
        {"seasonal_naive": FixtureKnownFutureProvider(1)},
        register_builtin_operators(),
        lambda: clock[0],
    )
    seed(ledger, runtime, clock)
    if os.environ.get("FA_USABILITY") == "1":
        clock[0] = datetime.now(timezone.utc)
    usability_csv = write_usability_fixture(data_dir, clock[0])
    port = int(os.environ.get("FA_USABILITY_PORT", "8000"))
    print(f"Usability API: http://127.0.0.1:{port}", flush=True)
    print(f"Usability CSV: {usability_csv}", flush=True)
    app = create_app(ledger, runtime, TOKEN, console_origins=("http://127.0.0.1:4173",))
    worker = Worker(runtime, JobQueue(ledger))

    def run_worker() -> None:
        while True:
            worker.run_due(clock[0])
            time.sleep(0.2)

    threading.Thread(target=run_worker, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
