"""Replay the retail demo through a temporary local API, worker and MCP client."""

import argparse
import asyncio
import csv
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from phase7_demo_support import (
    _call,
    _candidate_selection,
    _client,
    _free_port,
    _poll_mcp_job,
    _source_spec,
)


async def replay(prepared_csv: Path, workspace: Path):
    cli = Path(sys.executable).parent / "forecast-anything"
    source = workspace / "retail.csv"
    cutoff = "2011-12-02T00:00:00+00:00"
    with prepared_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    history = [r for r in rows if r["available_at"] <= cutoff]
    with source.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "value", "published"])
        writer.writerows(
            (r["event_time"][:10], r["value"], r["available_at"][:10]) for r in history
        )
    port = _free_port()
    env = dict(os.environ)
    subprocess.run(
        [
            cli,
            "init",
            "--workspace",
            workspace,
            "--csv-root",
            workspace,
            "--port",
            str(port),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    config = workspace / "config.json"
    log = (workspace / "services.log").open("w")
    supervisor = subprocess.Popen(
        [cli, "up", "--config", config, "--verify-model"],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        for _ in range(300):
            try:
                if (
                    httpx.get(f"http://127.0.0.1:{port}/health", timeout=1)
                    .json()
                    .get("worker")
                    == "running"
                ):
                    break
            except httpx.HTTPError:
                pass
            if supervisor.poll() is not None:
                raise RuntimeError(f"service exited: {workspace}")
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError(f"Worker did not become ready: {workspace}")
        spec = _source_spec(source)
        spec["source_id"] = "retail"
        spec["mapping"]["unit"] = {"constant": "items"}
        spec["mapping"]["series_id"] = {"constant": "retail"}
        async with await _client(cli, config, workspace, env) as client:
            preview = await _call(client, "preview_csv_source", spec=spec, as_of=cutoff)
            accepted = await _call(
                client,
                "confirm_csv_source",
                spec=spec,
                proposal_version=preview["proposal_version"],
                as_of=cutoff,
                key="retail-demo-capture",
            )
            discovery = await _poll_mcp_job(client, accepted["job_id"], timeout=60)
            for candidate_id in discovery["result"]["candidate_ids"]:
                candidate = await _call(
                    client, "get_candidate", candidate_id=candidate_id
                )
                if any(
                    node["node_id"] == "forecast"
                    for node in candidate["graph"]["nodes"]
                ):
                    break
            else:
                raise RuntimeError(
                    f"No executable candidate: {candidate.get('unresolved')}"
                )
            snapshot = discovery["result"]["source_snapshot_ids"][0]
            selection = _candidate_selection(candidate)
            question = await _call(
                client,
                "create_question",
                key="retail-demo-question",
                title="How many items will this retailer sell?",
                meaning="Forecast daily positive non-cancelled item quantities.",
                source_ids=["retail"],
                selection=selection,
            )
            job = await _call(
                client,
                "submit_forecast",
                candidate_id=candidate["candidate_id"],
                snapshot_ids={"retail": snapshot},
                as_of=cutoff,
                key="retail-demo-forecast",
            )
            run_id = (await _poll_mcp_job(client, job["job_id"], timeout=120))[
                "result"
            ]["run_id"]
            await _call(
                client,
                "link_question_reference",
                question_id=question["question_id"],
                key="retail-demo-link",
                revision=1,
                target_type="run",
                target_id=run_id,
            )
            run = await _call(client, "get_run", run_id=run_id)
        async with await _client(cli, config, workspace, env) as client:
            recovered = await _call(
                client,
                "get_question_presentation",
                question_id=question["question_id"],
                limit=3,
                offset=0,
            )
            if not any(
                item["reference"]["target_id"] == run_id
                and item["reference"]["target_type"] == "run"
                for item in recovered["references"]
            ):
                raise RuntimeError("Reopened question is missing the forecast run.")
            if run != await _call(client, "get_run", run_id=run_id):
                raise RuntimeError("Forecast record changed after reconnect.")
        result = {
            key: {k: value[k] for k in ("point", "timestamps", "units", "assumptions")}
            for key, value in run["results"].items()
            if key in ("forecast", "reference")
        }
        targets = {
            t.replace("Z", "+00:00")
            for model in result.values()
            for t in model["timestamps"]
        }
        return {
            "cutoff": cutoff,
            "observations": len(history),
            "question_id": question["question_id"],
            "run_id": run_id,
            "forecasts": result,
            "actuals": {
                row["event_time"]: float(row["value"])
                for row in rows
                if row["event_time"] in targets
            },
            "recent_history": history[-14:],
        }
    finally:
        if supervisor.poll() is None:
            os.killpg(supervisor.pid, signal.SIGTERM)
            supervisor.wait(timeout=15)
        log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_csv", type=Path)
    args = parser.parse_args()
    expected = "93f21b1765d979bd1ba39245af7f5665ff7b770417f1ea19ebe1007dd44beed1"
    if hashlib.sha256(args.prepared_csv.read_bytes()).hexdigest() != expected:
        parser.error("expected the pinned retail.csv from benchmarks.prepare")
    with tempfile.TemporaryDirectory(prefix="forecast-retail-") as directory:
        record = asyncio.run(replay(args.prepared_csv, Path(directory).resolve()))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
