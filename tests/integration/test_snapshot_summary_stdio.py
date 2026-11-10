"""A 320-row synthetic CSV remains usable through bounded MCP projections."""

import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="install the optional mcp extra")

from mcp_processes import LocalWorkspace, call, poll_job, source_spec


def _contains_exact_csv_value(payload, values):
    text_values = {str(value) for value in values}
    if isinstance(payload, dict):
        return any(_contains_exact_csv_value(item, values) for item in payload.values())
    if isinstance(payload, (list, tuple)):
        return any(_contains_exact_csv_value(item, values) for item in payload)
    if isinstance(payload, bool):
        return False
    if isinstance(payload, (int, float)):
        return payload in values
    return isinstance(payload, str) and payload in text_values


def test_320_row_csv_summary_paging_and_stored_snapshot_forecast(tmp_path):
    async def journey(workspace):
        csv_path = workspace.root / "large-history.csv"
        first_day = date(2025, 12, 8)
        rows = ["time,value,published\n"]
        values = tuple(20_000 + index for index in range(320))
        for index, value in enumerate(values):
            day = first_day + timedelta(days=index)
            rows.append(f"{day.isoformat()},{value},2026-10-23T12:00:00Z\n")
        csv_path.write_text("".join(rows))
        spec = source_spec(workspace, "large")
        spec["location"] = str(csv_path)
        spec["mapping"]["series_id"] = {"constant": "large"}

        async with workspace.client(source_ids=["large"]) as client:
            registered = await call(client, "register_csv_source", spec=spec)
            discovery = await poll_job(client, registered["job_id"])
            snapshot_id = discovery["result"]["source_snapshot_ids"][0]

            summary = await call(client, "summarize_snapshot", snapshot_id=snapshot_id)
            assert summary["observation_count"] == 320
            assert summary["series_count"] == 1
            assert summary["missing_count"] == 0
            # Check exact scalar leakage rather than substrings in random IDs or dates.
            assert not _contains_exact_csv_value(summary, values)

            series_page = await call(
                client,
                "list_snapshot_series",
                snapshot_id=snapshot_id,
                offset=0,
                limit=5,
            )
            assert len(series_page["series"]) == 1
            assert series_page["series"][0]["series_id"] == "large"
            assert series_page["series"][0]["observation_count"] == 320
            assert series_page["series"][0]["revision_count"] == 1
            assert not _contains_exact_csv_value(series_page, values)

            accepted = await call(
                client,
                "submit_configured_forecast",
                key="large-snapshot-forecast",
                source_id="large",
                snapshot_id=snapshot_id,
                selection={"provider": "seasonal_naive", "horizon": 1},
            )
            completed = await poll_job(client, accepted["job_id"])
            run = await call(client, "get_run", run_id=completed["result"]["run_id"])
            forecast = next(iter(run["results"].values()))
            assert forecast["provider_id"] == "seasonal_naive"
            assert len(forecast["point"][0]) == 1
            assert forecast["point"][0][0] == values[-1]

            long_job = await call(
                client,
                "submit_configured_forecast",
                key="large-presentation",
                source_id="large",
                snapshot_id=snapshot_id,
                selection={"provider": "seasonal_naive", "horizon": 80},
            )
            completed = await poll_job(client, long_job["job_id"])
            run_id = completed["result"]["run_id"]
            presentation = await call(
                client, "get_forecast_presentation", run_id=run_id
            )
            assert presentation == workspace.get(f"/v1/runs/{run_id}/presentation")
            assert presentation["primary_node_id"] == "model"
            assert (
                presentation["truncated"] and presentation["total_point_count"] == 160
            )
            assert len(presentation["points"]) == 64
            primary = {
                (p["series_id"], p["timestamp"], p["unit"])
                for p in presentation["points"]
                if p["node_id"] == "model"
            }
            baseline = {
                (p["series_id"], p["timestamp"], p["unit"])
                for p in presentation["points"]
                if p["node_id"] == "baseline"
            }
            assert len(primary) == 32 and primary == baseline

    with LocalWorkspace(
        tmp_path, source_root=Path(__file__).resolve().parents[2]
    ) as workspace:
        asyncio.run(journey(workspace))
