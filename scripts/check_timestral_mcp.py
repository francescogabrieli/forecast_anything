"""Explicit real-model acceptance; no baseline substitution or paid inference.

Run after `forecast-anything model prepare`, with the mcp extra installed.
Creates a fresh private workspace, starts production CLI services, exercises the
real stdio adapter, and writes a synthetic-data evidence report. No existing
workspace is modified; all child processes are stopped on exit.
"""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from forecast_anything.providers.configuration import (
    TIMESTRAL_CHECKPOINT,
    TIMESTRAL_CODE_REVISION,
    TIMESTRAL_REVISION,
)
from forecast_anything.workspace_config import create_workspace

JOB_TIMEOUT_SECONDS = 180


async def journey(root: Path, report_path: Path):
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    sources = root / "sources"
    sources.mkdir()
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=359)
    rows = [
        f"{start + timedelta(days=i)},{1 if i % 2 == 0 else 3},{start + timedelta(days=i)}"
        for i in range(360)
    ]
    csv = sources / "synthetic.csv"
    csv.write_text("time,value,published\n" + "\n".join(rows) + "\n")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    config_path = create_workspace(root, sources, port)
    config = json.loads(config_path.read_text())
    executable = str(Path(sys.executable).parent / "forecast-anything")
    environment = {
        **os.environ,
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "HF_HUB_OFFLINE": "1",
    }
    log = (root / "services.log").open("w")
    mcp_log = (root / "mcp.log").open("w")
    process = subprocess.Popen(
        [executable, "up", "--config", str(config_path)],
        env=environment,
        stdout=log,
        stderr=log,
    )
    http = httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{port}",
        headers={"Authorization": f"Bearer {config['token']}"},
        trust_env=False,
    )
    evidence = {
        "synthetic": True,
        "model": TIMESTRAL_CHECKPOINT,
        "weights_revision": TIMESTRAL_REVISION,
        "code_revision": TIMESTRAL_CODE_REVISION,
    }

    async def call(client, name, **arguments):
        result = await client.call_tool(name, arguments)
        envelope = result.structured_content
        assert envelope and envelope.get("ok"), (name, envelope)
        return envelope["data"]

    async def poll(client, job_id):
        deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            job = await call(client, "get_job", job_id=job_id)
            assert job["state"] not in {"failed", "cancelled"}, job
            if job["state"] == "completed":
                return job["result"]
            await asyncio.sleep(0.1)
        raise AssertionError("Timed out waiting for model job")

    def client():
        return Client(
            stdio_client(
                StdioServerParameters(
                    command=executable,
                    args=["mcp", "--config", str(config_path)],
                    env=environment,
                ),
                errlog=mcp_log,
            ),
            mode="legacy",
            read_timeout_seconds=30,
        )

    try:
        deadline = time.monotonic() + 20
        while True:
            assert process.poll() is None, "Production services exited"
            try:
                if (await http.get("/health")).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            assert time.monotonic() < deadline, "API did not start"
            await asyncio.sleep(0.1)
        async with client() as mcp:
            capabilities = await call(mcp, "get_capabilities")
            assert capabilities["required_provider"] == "timestral"
            assert capabilities["model_status"]["cached"]
            evidence["capabilities"] = capabilities
            spec = {
                "source_id": "timestral-synthetic",
                "kind": "csv",
                "location": str(csv),
                "refresh_seconds": 3600,
                "mapping": {
                    "event_time": "time",
                    "value": "value",
                    "available_at": "published",
                    **{
                        key: {"constant": value}
                        for key, value in {
                            "revision": "1",
                            "series_id": "sales",
                            "unit": "count",
                            "frequency": "1d",
                            "timezone": "UTC",
                            "calendar": "gregorian",
                            "missing_values": [""],
                        }.items()
                    },
                },
            }
            registration = await call(mcp, "register_csv_source", spec=spec)
            discovery = await poll(mcp, registration["job_id"])
            candidate_id = discovery["candidate_ids"][0]
            candidate = await call(mcp, "get_candidate", candidate_id=candidate_id)
            assert (
                next(
                    n for n in candidate["graph"]["nodes"] if n["node_id"] == "forecast"
                )["config"]["provider"]
                == "timestral"
            )
            snapshot_id = discovery["source_snapshot_ids"][0]
            selection = {
                "provider": "timestral",
                "options": {},
                "horizon": 1,
                "baseline_period": 1,
            }
            configured_request = {
                "source_id": spec["source_id"],
                "snapshot_id": snapshot_id,
                "selection": selection,
                "key": "real-configured",
            }
            configured = await call(
                mcp, "submit_configured_forecast", **configured_request
            )
            configured_run = await call(
                mcp, "get_run", run_id=(await poll(mcp, configured["job_id"]))["run_id"]
            )
            assert configured_run["primary_node_id"] == "model"
            assert configured_run["results"]["model"]["provider_id"] == "timestral"
            assert (
                configured_run["results"]["model"]["provider_revision"]
                == f"{TIMESTRAL_CHECKPOINT}@{TIMESTRAL_REVISION};code={TIMESTRAL_CODE_REVISION}"
            )
            assert (
                configured_run["results"]["baseline"]["provider_id"] == "seasonal_naive"
            )
            evidence["configured_run"] = configured_run
            before = await call(
                mcp,
                "submit_forecast",
                candidate_id=candidate_id,
                snapshot_ids={spec["source_id"]: snapshot_id},
                as_of=configured_run["as_of"],
                key="real-before",
            )
            before_id = (await poll(mcp, before["job_id"]))["run_id"]
            # Use independent synthetic data so this exploratory comparison
            # does not consume the watch candidate's final windows.
            comparator_csv = sources / "synthetic-comparator.csv"
            comparator_rows = [
                f"{start + timedelta(days=i)},{2 if i % 2 == 0 else 6},{start + timedelta(days=i)}"
                for i in range(360)
            ]
            comparator_csv.write_text(
                "time,value,published\n" + "\n".join(comparator_rows) + "\n"
            )
            comparator_source = "timestral-comparator"
            await call(
                mcp,
                "register_csv_source",
                spec={
                    **spec,
                    "source_id": comparator_source,
                    "location": str(comparator_csv),
                },
            )
            comparator_job = await call(
                mcp,
                "submit_backtest",
                source_id=comparator_source,
                selection={**selection, "baseline_period": 2},
                settings={"max_origins_per_partition": 2},
                key="real-perfect-comparator",
            )
            comparator_result = await poll(mcp, comparator_job["job_id"])
            comparator_id = comparator_result["backtest_id"]
            comparator_report = await call(
                mcp, "get_backtest", backtest_id=comparator_id
            )
            final = next(
                p for p in comparator_report["partitions"] if p["partition"] == "final"
            )
            assert final["evaluated"] == 2
            assert final["baseline_mae"] == 0 and final["model_mae"] > 0, final
            assert final["relative_mae"] is None
            evidence["losing_comparison"] = {
                "backtest_id": comparator_id,
                "final": final,
            }
            # Keep the watch from refreshing before its backtest and MCP reads finish.
            due = datetime.now(timezone.utc) + timedelta(
                seconds=JOB_TIMEOUT_SECONDS + 30
            )
            watch = await call(
                mcp,
                "create_watch",
                candidate_id=candidate_id,
                next_due_at=due.isoformat(),
            )
            watch_id = watch["watch_id"]
            request = dict(
                source_id=spec["source_id"],
                selection=selection,
                settings={"max_origins_per_partition": 30},
                watch_id=watch_id,
                key="real-watch-backtest",
            )
            accepted = await call(mcp, "submit_backtest", **request)
            result = await poll(mcp, accepted["job_id"])
            report = await call(mcp, "get_backtest", backtest_id=result["backtest_id"])
            summary = await call(
                mcp,
                "summarize_backtest",
                backtest_id=result["backtest_id"],
                watch_id=watch_id,
            )
            assert summary["partitions"] == report["partitions"]
            assert summary["watch"]["linked_to_backtest"]
            assert (await call(mcp, "submit_backtest", **request))[
                "job_id"
            ] == accepted["job_id"]
            evidence.update(
                candidate_id=candidate_id,
                watch_id=watch_id,
                before_run_id=before_id,
                backtest_result=result,
                backtest_summary=summary,
            )
            current = await call(mcp, "get_watch", watch_id=watch_id)
            assert current["operational"] == (result["eligibility"] == "activate")
            evidence["watch_before_refresh"] = {
                k: current[k]
                for k in ("lifecycle", "quality", "operational", "next_due_at")
            }
            # Preserve authorization for subsequent real MCP processes.
            grant = subprocess.run(
                [
                    executable,
                    "permissions",
                    "grant",
                    spec["source_id"],
                    "--config",
                    str(config_path),
                ],
                capture_output=True,
                text=True,
            )
            assert grant.returncode == 0
        # No MCP connection exists while the independent worker refreshes.
        for i in range(346, 360):
            parts = rows[i].split(",")
            parts[1] = str(int(parts[1]) + 10)
            rows[i] = ",".join(parts)
        replacement = csv.with_suffix(".tmp")
        replacement.write_text("time,value,published\n" + "\n".join(rows) + "\n")
        refresh_at = datetime.fromisoformat(current["next_due_at"]).timestamp()
        assert time.time() < refresh_at, (
            "Backtest and setup consumed the watch refresh deadline"
        )
        replacement.replace(csv)
        deadline = refresh_at + 75
        successor = None
        while time.time() < deadline:
            response = await http.get("/v1/watches")
            response.raise_for_status()
            successor = next(
                (w for w in response.json() if w["supersedes_watch_id"] == watch_id),
                None,
            )
            if successor:
                break
            await asyncio.sleep(0.25)
        assert successor, "No automatic successor after real deadline"
        async with client() as mcp:
            replay = await call(mcp, "submit_configured_forecast", **configured_request)
            assert replay["job_id"] == configured["job_id"]
            replay_run_id = (await poll(mcp, replay["job_id"]))["run_id"]
            assert replay_run_id == configured_run["run_id"]
            assert await call(mcp, "get_run", run_id=replay_run_id) == configured_run
            evidence["forecast_replay"] = {
                "job_id": replay["job_id"],
                "run_id": replay_run_id,
            }
            assert (
                await call(mcp, "get_backtest", backtest_id=comparator_id)
                == comparator_report
            )
            assert (
                await call(mcp, "get_backtest", backtest_id=result["backtest_id"])
                == report
            )
            old = await call(mcp, "get_watch", watch_id=watch_id)
            assert old["candidate_invalidated"] and not old["operational"]
            after_configured = await call(
                mcp,
                "submit_configured_forecast",
                source_id=spec["source_id"],
                snapshot_id=successor["source_snapshot_ids"][0],
                selection=selection,
                key="real-configured-after",
            )
            after_origin = await call(
                mcp,
                "get_run",
                run_id=(await poll(mcp, after_configured["job_id"]))["run_id"],
            )
            after = await call(
                mcp,
                "submit_forecast",
                candidate_id=candidate_id,
                snapshot_ids={spec["source_id"]: successor["source_snapshot_ids"][0]},
                as_of=after_origin["as_of"],
                key="real-after",
            )
            after_id = (await poll(mcp, after["job_id"]))["run_id"]
            change = await call(
                mcp,
                "summarize_watch_change",
                watch_id=watch_id,
                previous_run_id=before_id,
                current_run_id=after_id,
            )
            assert change["new_snapshot_ids"]
            assert any(item.get("delta") not in (None, 0) for item in change["changes"])
            evidence.update(
                after_run_id=after_id,
                change=change,
                successor_watch_id=successor["watch_id"],
                watch_after_refresh={
                    k: old[k]
                    for k in (
                        "lifecycle",
                        "quality",
                        "operational",
                        "candidate_invalidated",
                    )
                },
            )
            # New setup/status must be distinguishable from metadata-only cache checks.
            evidence["completed"] = True
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(evidence, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "completed": True,
                    "report": str(report_path),
                    "backtest_id": result["backtest_id"],
                    "qualification": result.get("eligibility"),
                    "change": [
                        item
                        for item in change["changes"]
                        if item["representation"] == "point"
                    ],
                }
            )
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        await http.aclose()
        log.close()
        mcp_log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(journey(args.workspace.resolve(), args.report.resolve()))
