"""Real SDK/stdin/stdout -> authenticated loopback API -> independent worker."""

import asyncio
import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("mcp", reason="install the optional mcp extra")

from mcp_processes import LocalWorkspace, baseline_journey, call, poll_job, source_spec


def test_stdio_profile_of_changed_allowed_source_queues_durable_discovery(tmp_path):
    async def journey(workspace):
        registered = workspace.post("/v1/sources", source_spec(workspace))
        async with workspace.client(source_ids=["sales"]) as client:
            original = await poll_job(client, registered["job_id"])
            workspace.stop_worker()
            workspace.write_history(actuals=True)
            workspace.set_clock("2026-10-25T00:00:00+00:00")
            profile = await call(client, "get_source_profile", source_id="sales")
            assert profile != registered["profile"]
            # Observe the real API's queue; the profile response does not expose its job ID.
            with sqlite3.connect(workspace.root / "state.db") as connection:
                pending = connection.execute(
                    "SELECT job_id, payload FROM jobs WHERE state = 'pending'"
                ).fetchall()
            assert len(pending) == 1
            job_id, payload = pending[0]
            payload = json.loads(payload)
            assert payload["kind"] == "discovery_templates"
            assert payload["source_id"] == "sales"
            assert payload["profile"] == profile
            assert job_id != registered["job_id"]
            catalog = {tool.name: tool for tool in (await client.list_tools()).tools}
        # The profile's durable work outlives the MCP process that caused it.
        assert workspace.get("/v1/jobs/" + job_id)["state"] == "pending"
        workspace.start_worker()
        async with workspace.client(source_ids=["sales"]) as client:
            discovered = await poll_job(client, job_id)
            snapshot_id = discovered["result"]["source_snapshot_ids"][0]
            assert snapshot_id != original["result"]["source_snapshot_ids"][0]
            snapshot = await call(client, "get_snapshot", snapshot_id=snapshot_id)
            assert len(snapshot["observations"]) == 4
            candidate = await call(
                client,
                "get_candidate",
                candidate_id=discovered["result"]["candidate_ids"][0],
            )
            assert candidate["epoch_id"] == payload["epoch_id"]
            assert (
                await call(
                    client,
                    "get_graph",
                    graph_id=candidate["graph"]["graph_id"],
                    version=candidate["graph"]["version"],
                )
                == candidate["graph"]
            )
        # Clients must see the side-effect risk before choosing to invoke this tool.
        assert catalog["get_source_profile"].annotations.read_only_hint is False
        assert catalog["get_source_profile"].annotations.idempotent_hint is False

    with LocalWorkspace(tmp_path) as workspace:
        asyncio.run(asyncio.wait_for(journey(workspace), timeout=30))


def test_stdio_forecast_survives_disconnect_and_evaluates_same_source(tmp_path):
    async def journey(workspace):
        issued = await baseline_journey(workspace)
        # baseline_journey disconnected before starting the worker again.
        async with workspace.client(source_ids=["sales"]) as client:
            run = issued["run"]
            assert await call(client, "get_source_profile", source_id="sales")
            assert (
                await call(client, "get_graph", graph_id=run["graph_id"], version=1)
                == issued["candidate"]["graph"]
            )
            assert (
                await call(
                    client,
                    "get_snapshot",
                    snapshot_id=issued["snapshot"]["snapshot_id"],
                )
                == issued["snapshot"]
            )
            assert (
                await call(client, "list_run_evaluations", run_id=run["run_id"]) == []
            )
            # New observations are published only after this forecast was issued.
            workspace.write_history(actuals=True)
            workspace.set_clock("2026-10-25T00:00:00+00:00")
            refreshed = await call(
                client, "refresh_source", source_id="sales", key="actuals-vintage-1"
            )
            refreshed_job = await poll_job(client, refreshed["job_id"])
            actuals_id = refreshed_job["result"]["source_snapshot_ids"][0]
            actuals = await call(client, "get_snapshot", snapshot_id=actuals_id)
            assert actuals_id != issued["snapshot"]["snapshot_id"]
            assert actuals["as_of"] == "2026-10-25T00:00:00Z"
            outcome = next(
                o
                for o in actuals["observations"]
                if o["event_time"] == "2026-10-24T00:00:00Z"
            )
            assert outcome["value"] == 4
            assert outcome["available_at"] == "2026-10-24T12:00:00Z"
            assert {
                a for a in actuals["assumptions"] if a.startswith("source_revision=")
            } == {
                a
                for a in issued["snapshot"]["assumptions"]
                if a.startswith("source_revision=")
            }
            evaluation_job = await call(
                client,
                "submit_evaluation",
                run_id=run["run_id"],
                actuals_snapshot_id=actuals_id,
                key="evaluate-issued-vintage-1",
            )
            evaluated = await poll_job(client, evaluation_job["job_id"])
            evaluation = await call(
                client,
                "get_evaluation",
                evaluation_id=evaluated["result"]["evaluation_id"],
            )
            assert evaluation["status"] == "evaluated"
            assert evaluation["origin_count"] == 1
            assert evaluation["actuals_snapshot_id"] == actuals_id
            assert evaluation["discovery"] is None
            assert evaluation["metrics"]["forecast"]["count"] == 1
            assert evaluation["metrics"]["forecast"]["mae"] == 2.0
            assert await call(client, "list_run_evaluations", run_id=run["run_id"]) == [
                evaluation
            ]
            assert await call(client, "get_run", run_id=run["run_id"]) == run
            events = await call(client, "get_events")
            assert (
                len([e for e in events["events"] if e["kind"] == "run_completed"]) == 1
            )
            assert (await call(client, "get_events", after=events["cursor"]))[
                "events"
            ] == []

            # An unrelated catalog identity cannot authorize scoring identical series.
            other = await call(
                client, "register_csv_source", spec=source_spec(workspace, "other")
            )
            other_job = await poll_job(client, other["job_id"])
            other_snapshot = other_job["result"]["source_snapshot_ids"][0]
            await call(
                client,
                "submit_evaluation",
                error="validation_error",
                run_id=run["run_id"],
                actuals_snapshot_id=other_snapshot,
                key="wrong-source",
            )

            # Scenarios enter through the existing API, never an invented MCP tool.
            scenario = workspace.post(
                "/v1/scenarios",
                {
                    "base_graph_id": run["graph_id"],
                    "base_version": 1,
                    "label": "assumed outcome",
                    "source_overrides": {"sales": issued["snapshot"]},
                },
            )
            assumed_id = scenario["snapshot_ids"]["sales"]
            assumed = await call(client, "get_snapshot", snapshot_id=assumed_id)
            assert any(a.startswith("assumed:") for a in assumed["assumptions"])
            await call(
                client,
                "submit_evaluation",
                error="validation_error",
                run_id=run["run_id"],
                actuals_snapshot_id=assumed_id,
                key="assumed-outcome",
            )

            # A real persisted two-history forecast is deliberately unsupported.
            graph = copy.deepcopy(issued["candidate"]["graph"])
            graph["graph_id"] = "two-history-stdio-fixture"
            history = next(n for n in graph["nodes"] if n["kind"] == "source")
            forecast = next(n for n in graph["nodes"] if n["kind"] == "forecast")
            graph["nodes"].append(
                {
                    **copy.deepcopy(history),
                    "node_id": "other-history",
                    "config": {**history["config"], "source_id": "other"},
                }
            )
            graph["nodes"].append(
                {
                    **copy.deepcopy(forecast),
                    "node_id": "other-forecast",
                    "inputs": ["other-history"],
                    "config": {
                        **forecast["config"],
                        "history": "other-history",
                        "relation_type": {"other-history": "statistical"},
                    },
                }
            )
            multi = workspace.post(
                "/v1/jobs",
                {
                    "kind": "run",
                    "key": "two-history",
                    "graph": graph,
                    "snapshot_ids": {"sales": actuals_id, "other": other_snapshot},
                    "as_of": actuals["as_of"],
                },
            )
            multi_job = await poll_job(client, multi["job_id"])
            await call(
                client,
                "submit_evaluation",
                error="validation_error",
                run_id=multi_job["result"]["run_id"],
                actuals_snapshot_id=actuals_id,
                key="multi-history-evaluation",
            )
            # No caller-supplied metrics or source text become execution inputs.
            await call(
                client,
                "submit_evaluation",
                error="validation_error",
                run_id=run["run_id"],
                actuals_snapshot_id=actuals_id,
                key="forged-metric",
                metrics={"mae": 0},
            )
        async with workspace.client() as client:
            await call(
                client,
                "get_source_profile",
                error="source_forbidden",
                source_id="sales",
            )
            await call(
                client,
                "refresh_source",
                error="source_forbidden",
                source_id="sales",
                key="unconfigured-reconnect",
            )

    with LocalWorkspace(tmp_path) as workspace:
        asyncio.run(asyncio.wait_for(journey(workspace), timeout=60))


def test_stdio_errors_and_large_result_are_bounded_and_sanitized(tmp_path):
    async def journey(workspace):
        async with workspace.client(token="wrong-private-token") as client:
            await call(client, "get_capabilities", error="unauthorized")
        async with workspace.client() as client:
            forbidden = source_spec(workspace)
            forbidden["location"] = str(tmp_path.parent / "private-secret.csv")
            await call(
                client, "register_csv_source", error="source_forbidden", spec=forbidden
            )
            invalid = source_spec(workspace)
            invalid["mapping"] = workspace.instruction
            await call(
                client, "register_csv_source", error="validation_error", spec=invalid
            )
            await call(
                client,
                "get_run",
                error="not_found",
                run_id="missing/../private-marker?token=secret",
            )
            # The upstream response fits 1 MiB; the duplicated MCP result exceeds 64 KiB.
            start = datetime(2020, 1, 1, tzinfo=timezone.utc)
            workspace.history.write_text(
                "time,value,published\n"
                + "".join(
                    f"{(start + timedelta(days=i)).date()},1,2020-01-01\n"
                    for i in range(600)
                )
            )
            registered = await call(
                client, "register_csv_source", spec=source_spec(workspace)
            )
            discovered = await poll_job(client, registered["job_id"])
            snapshot_id = discovered["result"]["source_snapshot_ids"][0]
            result = await call(
                client,
                "get_snapshot",
                error="result_too_large",
                snapshot_id=snapshot_id,
            )
            assert result == {"ok": False, "code": "result_too_large"}
        # Each client context has shut down and captured its subprocess stderr.
        text = "\n".join(workspace.errors + workspace.stderr)
        for private in (
            workspace.token,
            "wrong-private-token",
            str(workspace.root),
            workspace.instruction,
        ):
            assert private not in text
        assert not workspace.command_marker.exists()
        assert all(len(error.encode()) <= 65536 for error in workspace.errors)
        assert json.loads(workspace.errors[-1])["code"] == "result_too_large"

    with LocalWorkspace(tmp_path) as workspace:
        asyncio.run(asyncio.wait_for(journey(workspace), timeout=30))


def test_stdio_configured_forecast_and_frozen_multi_origin_recovery(tmp_path):
    from mcp_evidence_journey import evidence_journey

    with LocalWorkspace(tmp_path) as workspace:
        asyncio.run(asyncio.wait_for(evidence_journey(workspace), timeout=60))


def test_stdio_missing_targets_and_unavailable_revision_keep_planned_origins(tmp_path):
    from mcp_evidence_journey import stored, write_evidence_history

    async def journey(workspace):
        write_evidence_history(workspace, gaps=True)
        spec = source_spec(workspace)
        spec["mapping"]["revision"] = "revision"
        async with workspace.client(source_ids=["sales"]) as client:
            registered = await call(client, "register_csv_source", spec=spec)
            await poll_job(client, registered["job_id"])
            job = await call(
                client,
                "submit_backtest",
                key="missing-cells",
                source_id="sales",
                selection={
                    "provider": "seasonal_naive",
                    "options": {"period": 2},
                    "horizon": 2,
                    "baseline_period": 1,
                },
                settings={"max_origins_per_partition": 2},
            )
            await poll_job(client, job["job_id"])
            report = await call(client, "get_backtest", backtest_id=job["job_id"])
            origins = (
                await call(client, "list_backtest_origins", backtest_id=job["job_id"])
            )["origins"]
            legacy_summary = await call(
                client, "summarize_backtest", backtest_id=job["job_id"]
            )
            presentation = await call(
                client,
                "get_backtest_presentation",
                backtest_id=job["job_id"],
            )
            assert presentation["summary"] == legacy_summary
            assert presentation == workspace.get(
                f"/v1/backtests/{job['job_id']}/presentation"
            )
            assert len(origins) == 6
            assert [(o["status"], o["reason_code"]) for o in origins] == [
                ("excluded", "insufficient_history"),
                ("excluded", "missing_history"),  # Jan 3 published only Jan 4
                ("insufficient_evidence", "incomplete_actuals"),  # Jan 14 absent
                ("excluded", "missing_history"),
                ("excluded", "missing_history"),
                ("excluded", "missing_history"),
            ]
            assert origins[1]["nominal_origin"] == "2026-01-03T00:00:00Z"
            assert origins[2]["target_start"] == "2026-01-13T00:00:00Z"
            assert origins[2]["target_end"] == "2026-01-14T00:00:00Z"
            assert report["status"] == "insufficient_evidence"
            assert [p["planned"] for p in report["partitions"]] == [2, 2, 2]
            assert all(
                p["matched_count"] == 0
                and p["relative_mae_reason"] == "no_matched_cells"
                for p in report["partitions"]
            )
            assert stored(workspace, "backtest_origins", job["job_id"]) == origins
            assert (
                len(stored(workspace, "backtest_plans", job["job_id"])[0]["calendar"])
                == 24
            )

    with LocalWorkspace(tmp_path) as workspace:
        asyncio.run(asyncio.wait_for(journey(workspace), timeout=30))


def test_stdio_diagnostics_stays_available_with_api_down(tmp_path):
    import os
    import socket
    import sys
    from pathlib import Path

    from mcp import Client
    from mcp.client.stdio import StdioServerParameters, stdio_client

    from forecast_anything.workspace_config import create_workspace

    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
        config = create_workspace(tmp_path / "workspace", tmp_path, port)

        async def journey():
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "forecast_anything.cli", "mcp", "--config", str(config)],
                env={
                    **os.environ,
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
                },
            )
            async with Client(stdio_client(params), mode="legacy") as client:
                report = await call(client, "get_diagnostics")
                assert report["api"] == "unreachable"
                assert report["authentication"] == "unknown"
                assert report["permissions"]["readable_csv_roots"] == 1
                assert not report["ready"]
                assert str(tmp_path) not in json.dumps(report)

        asyncio.run(asyncio.wait_for(journey(), timeout=10))
