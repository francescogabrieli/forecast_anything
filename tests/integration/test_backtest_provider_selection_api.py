"""Configured forecasts using held-out evidence for provider selection."""

from pathlib import Path

import pytest
from test_backtest_api import T, request, setup, submit

from forecast_anything.jobs import JobQueue
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.sources.profiling import ingest_source
from forecast_anything.worker import Worker


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("baseline", "seasonal_naive"),
        ("no_report", "timestral"),
        ("insufficient", "timestral"),
        ("holdout_disagrees", "timestral"),
        ("challenger", "trend_double"),
        ("revised_history", None),
        ("future_report", None),
        ("changed_provider", None),
    ],
)
def test_configured_forecast_can_select_a_provider_from_held_out_evidence(
    tmp_path, mode, expected
):
    from datetime import timedelta

    class ModelDouble(SeasonalNaiveProvider):
        def __init__(self, name, adjustment):
            super().__init__(1)
            self.name = name
            self.adjustment = adjustment

        def capabilities(self):
            return super().capabilities().model_copy(update={"provider_id": self.name})

        def forecast(self, request):
            result = super().forecast(request)
            adjustment = self.adjustment
            if (
                mode == "holdout_disagrees"
                and self.name == "timestral"
                and request.snapshot.as_of >= T - timedelta(days=23)
            ):
                adjustment = 2
            return result.model_copy(
                update={
                    "provider_id": self.name,
                    "point": tuple(
                        tuple(value + adjustment for value in row)
                        for row in result.point
                    ),
                }
            )

    ledger, runtime, _, revision, client = setup(tmp_path)
    runtime.required_provider = "timestral"
    runtime.providers["timestral"] = ModelDouble("timestral", 0)
    runtime.providers["trend_double"] = ModelDouble("trend_double", 1)
    start = T - timedelta(days=89)
    path = Path(revision.spec.location)
    path.write_text(
        "time,value\n"
        + "".join(f"{(start + timedelta(days=i)).date()},{i}\n" for i in range(90))
    )
    snapshot = ingest_source(revision.spec, T)
    ledger.put_snapshot(snapshot)
    worker = Worker(runtime, JobQueue(ledger))
    selection = {
        "provider": "timestral",
        "horizon": 1,
        "options": {"period": 2},
        "baseline_period": 1,
    }

    def backtest(provider, *, period, origins=10):
        job = submit(
            client,
            request(
                key=f"report-{provider}",
                selection={
                    **selection,
                    "provider": provider,
                    "options": {"period": period},
                },
                settings={"max_origins_per_partition": origins},
            ),
        )
        worker.run_due(T)
        response = client.get(f"/v1/backtests/{job}")
        assert response.status_code == 200, response.text
        return response.json()

    report = backtest(
        "timestral", period=2, origins=9 if mode == "insufficient" else 10
    )
    assert report["partitions"][1]["model_mae"] == 2
    assert report["partitions"][-1]["model_mae"] == (
        0 if mode == "holdout_disagrees" else 2
    )
    assert report["partitions"][-1]["baseline_mae"] == 1
    evidence = (
        {} if mode == "no_report" else {"selection_report_id": report["report_id"]}
    )
    if mode == "challenger":
        challenger = backtest("trend_double", period=1)
        assert challenger["partitions"][-1]["model_mae"] == 0
        evidence["challenger_report_id"] = challenger["report_id"]
    if mode == "revised_history":
        path.write_text(
            path.read_text().replace(f"{start.date()},0", f"{start.date()},99")
        )
        snapshot = ingest_source(revision.spec, T)
        ledger.put_snapshot(snapshot)
    if mode == "future_report":
        snapshot = ingest_source(revision.spec, T - timedelta(days=1))
        ledger.put_snapshot(snapshot)
    if mode == "changed_provider":

        class ChangedDouble(ModelDouble):
            def capabilities(self):
                return (
                    super()
                    .capabilities()
                    .model_copy(update={"provider_revision": "new"})
                )

        runtime.providers["timestral"] = ChangedDouble("timestral", 0)
    body = request(
        "configured_run",
        key="configured",
        snapshot_id=snapshot.snapshot_id,
        selection=selection,
        **evidence,
    )
    if expected is None:
        response = client.post("/v1/jobs", json=body)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == (
            "model_selection_report_mismatch"
            if mode in {"revised_history", "future_report"}
            else "provider_contract_changed"
        )
        return
    job_id = submit(client, body)
    worker.run_due(T)
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["state"] == "completed", job
    run = ledger.get_run(job["result"]["run_id"])
    assert run.actual_provider["model"] == expected
    if evidence:
        assert run.model_selection.report_ids == tuple(evidence.values())
        assert run.model_selection.series_id == "sales"
        assert run.model_selection.reason == (
            "default_retained"
            if mode in {"insufficient", "holdout_disagrees"}
            else "confirmed_lower_mae"
        )
        presentation = client.get(f"/v1/runs/{run.run_id}/presentation")
        assert presentation.json()["model_selection"] == run.model_selection.model_dump(
            mode="json"
        )
    else:
        assert run.model_selection is None
    assert submit(client, body) == job_id
