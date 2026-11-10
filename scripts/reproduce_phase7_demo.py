"""Reproduce the public synthetic CSV journey through the installed MCP runtime."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import importlib.metadata
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "release-demo"


class DemoError(RuntimeError):
    pass


def _run_cli(cli: Path, arguments: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        [str(cli), *arguments],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode:
        raise DemoError(
            f"forecast-anything {' '.join(arguments)} failed ({result.returncode}): "
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout.strip()


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _source_spec(path: Path) -> dict[str, Any]:
    return {
        "source_id": "demand",
        "kind": "csv",
        "location": str(path.resolve()),
        # This faster-than-daily interval is confined to the synthetic source.
        "refresh_seconds": 60,
        "mapping": {
            "event_time": "time",
            "value": "value",
            "available_at": "published",
            "revision": {"constant": "1"},
            "series_id": {"constant": "demand"},
            "unit": {"constant": "orders"},
            "frequency": {"constant": "1d"},
            "timezone": {"constant": "UTC"},
            "calendar": {"constant": "gregorian"},
            "missing_values": {"constant": [""]},
        },
    }


def _candidate_selection(candidate: dict[str, Any]) -> dict[str, Any]:
    nodes = {node["node_id"]: node for node in candidate["graph"]["nodes"]}
    model = nodes["forecast"]["config"]
    baseline = nodes["reference"]["config"]
    return {
        "provider": model["provider"],
        "options": model["options"],
        "horizon": model["horizon"],
        "baseline_period": baseline["options"]["period"],
    }


async def _call(client: Client, name: str, **arguments: Any) -> dict[str, Any]:
    result = await client.call_tool(name, arguments)
    envelope = result.structured_content
    if result.is_error or not isinstance(envelope, dict) or not envelope.get("ok"):
        raise DemoError(f"MCP tool {name} failed: {envelope or result.content}")
    return envelope["data"]


async def _client(cli: Path, config: Path, cwd: Path, env: dict[str, str]):
    parameters = StdioServerParameters(
        command=str(cli),
        args=["mcp", "--config", str(config)],
        cwd=str(cwd),
        env=env,
    )
    return Client(stdio_client(parameters), mode="legacy", read_timeout_seconds=12)


async def _poll_mcp_job(client: Client, job_id: str, *, timeout: float = 900) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = await _call(client, "get_job", job_id=job_id)
        if job["state"] == "failed":
            raise DemoError(f"worker job {job_id} failed: {job.get('error')}")
        if job["state"] == "completed":
            return job
        await asyncio.sleep(0.25)
    raise DemoError(f"worker job {job_id} timed out")


def _http_json(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict:
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def _point_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    point = result["point"]
    series = point[0] if point and isinstance(point[0], list) else point
    timestamps = result["timestamps"]
    unit = result.get("units", ["unknown"])[0]
    return [
        {"time": timestamp, "value": float(value), "unit": unit}
        for timestamp, value in zip(timestamps, series, strict=True)
    ]


def _trim_partitions(summary: dict[str, Any]) -> list[dict[str, Any]]:
    fields = (
        "partition",
        "planned",
        "matched_count",
        "model_mae",
        "baseline_mae",
        "relative_mae",
        "relative_mae_reason",
    )
    return [
        {field: partition.get(field) for field in fields if field in partition}
        for partition in summary.get("partitions", [])
    ]


def _load_public_data(output: Path) -> dict[str, Any]:
    if output.exists():
        data = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("examples"), list):
            raise DemoError("output must be the existing site demo-data.json")
        return data
    return {"source": "scripts/reproduce_phase7_demo.py", "examples": []}


async def reproduce(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    cli = args.cli.resolve(strict=True)
    if not os.access(cli, os.X_OK):
        raise DemoError(f"CLI is not executable: {cli}")
    workspace = args.workspace.expanduser().resolve()
    config_path = workspace / "config.json"
    if config_path.exists():
        raise DemoError(f"workspace already exists; choose a fresh path: {workspace}")
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    source_root = workspace / "sources"
    source_root.mkdir(mode=0o700)
    source_path = source_root / "demand.csv"
    shutil.copyfile(FIXTURE / "observations.csv", source_path)
    assumptions = json.loads((FIXTURE / "assumptions.json").read_text(encoding="utf-8"))
    fixture_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    port = _free_port()
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}

    model_status = json.loads(
        _run_cli(cli, ["model", "status"], cwd=workspace, env=env)
    )
    if not model_status.get("cached", False):
        raise DemoError(
            "Pinned Timestral weights are not cached. Review docs/implementation/timestral.md, "
            "then run forecast-anything model prepare explicitly."
        )
    _run_cli(
        cli,
        [
            "init",
            "--workspace",
            str(workspace),
            "--csv-root",
            str(source_root),
            "--port",
            str(port),
        ],
        cwd=workspace,
        env=env,
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    api_url = f"http://127.0.0.1:{port}"
    log_path = workspace / "services.log"
    log_stream = log_path.open("w", encoding="utf-8")
    supervisor = subprocess.Popen(
        [str(cli), "up", "--config", str(config_path), "--verify-model"],
        cwd=workspace,
        env=env,
        stdout=log_stream,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    webhook_received: list[tuple[str | None, dict[str, Any]]] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            webhook_received.append((self.headers.get("X-Forecast-Event-Id"), payload))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args):
            pass

    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    receiver_thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    receiver_thread.start()
    sdk_version = importlib.metadata.version("mcp")
    if sdk_version != "2.3.0":
        raise DemoError(f"expected MCP SDK 2.3.0, found {sdk_version}")

    try:
        headers = {"Authorization": f"Bearer {config['token']}"}
        with httpx.Client(
            base_url=api_url, headers=headers, timeout=3, trust_env=False
        ) as http:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if supervisor.poll() is not None:
                    raise DemoError(f"local supervisor exited; inspect {log_path}")
                try:
                    health = _http_json(http, "GET", "/health")
                    if health.get("worker") == "running":
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise DemoError(
                    f"local API/worker did not become ready; inspect {log_path}"
                )

            async with await _client(cli, config_path, workspace, env) as client:
                source_spec = _source_spec(source_path)
                preview = await _call(
                    client,
                    "preview_csv_source",
                    spec=source_spec,
                    as_of=assumptions["initial_as_of"],
                )
                accepted = await _call(
                    client,
                    "confirm_csv_source",
                    key="phase7-demand-capture",
                    spec=source_spec,
                    proposal_version=preview["proposal_version"],
                    as_of=assumptions["initial_as_of"],
                )
                discovery = await _poll_mcp_job(client, accepted["job_id"])
            _run_cli(
                cli,
                ["permissions", "grant", "demand", "--config", str(config_path)],
                cwd=workspace,
                env=env,
            )
            config = json.loads(config_path.read_text(encoding="utf-8"))

            event_id = None
            question_id = None
            watch_id = None
            initial_run_id = None
            backtest_summary = None
            initial_run = None
            first_forecast_seconds = None
            browser_link = None
            webhook_subscription = None
            question_record = None
            view_result = None
            # Keep the listener open through the disconnected worker-delivery wait;
            # the explicit finally block owns shutdown and socket closure.
            with nullcontext(receiver):
                async with await _client(cli, config_path, workspace, env) as client:
                    candidate_id = discovery["result"]["candidate_ids"][0]
                    candidate = await _call(
                        client, "get_candidate", candidate_id=candidate_id
                    )
                    selection = _candidate_selection(candidate)
                    snapshot_id = discovery["result"]["source_snapshot_ids"][0]
                    snapshot_summary = await _call(
                        client, "summarize_snapshot", snapshot_id=snapshot_id
                    )
                    question = await _call(
                        client,
                        "create_question",
                        key="phase7-demand-question",
                        title="The next daily demand point",
                        meaning="Forecast daily synthetic demand and explain changes when a new observation arrives.",
                        source_ids=["demand"],
                        selection=selection,
                    )
                    question_id = question["question_id"]
                    watch = await _call(
                        client,
                        "create_watch",
                        candidate_id=candidate_id,
                        next_due_at=(
                            datetime.now(timezone.utc) + timedelta(seconds=2)
                        ).isoformat(),
                    )
                    watch_id = watch["watch_id"]
                    await _call(
                        client,
                        "link_question_reference",
                        question_id=question_id,
                        key="phase7-link-watch",
                        revision=1,
                        target_type="watch",
                        target_id=watch_id,
                        note="Recurring worker checks for new demand observations.",
                    )
                    backtest_job = await _call(
                        client,
                        "submit_backtest",
                        key="phase7-demand-historical-backtest",
                        source_id="demand",
                        selection=selection,
                        settings={"max_origins_per_partition": 30},
                        watch_id=watch_id,
                    )
                    backtest = await _poll_mcp_job(client, backtest_job["job_id"])
                    backtest_id = backtest["result"]["backtest_id"]
                    backtest_summary = await _call(
                        client,
                        "summarize_backtest",
                        backtest_id=backtest_id,
                        watch_id=watch_id,
                    )
                    issued = await _call(
                        client,
                        "submit_forecast",
                        candidate_id=candidate_id,
                        snapshot_ids={"demand": snapshot_id},
                        as_of=snapshot_summary["as_of"],
                        key="phase7-demand-first-forecast",
                    )
                    issued_job = await _poll_mcp_job(client, issued["job_id"])
                    first_forecast_seconds = time.monotonic() - started
                    initial_run_id = issued_job["result"]["run_id"]
                    initial_run = await _call(client, "get_run", run_id=initial_run_id)
                    await _call(
                        client,
                        "link_question_reference",
                        question_id=question_id,
                        key="phase7-link-first-run",
                        revision=1,
                        target_type="run",
                        target_id=initial_run_id,
                        note="First forecast for the saved question.",
                    )
                    webhook_subscription = await _call(
                        client,
                        "create_webhook_subscription",
                        target_url=f"http://127.0.0.1:{receiver.server_port}/updates",
                        secret="phase-7-demo-test-secret",
                    )
                    browser_link = await _call(
                        client,
                        "get_browser_link",
                        kind="question",
                        resource_id=question_id,
                        browser_url="http://127.0.0.1:4173",
                    )
                    try:
                        view_result = await _call(
                            client,
                            "open_context_view",
                            kind="question",
                            resource_id=question_id,
                            browser_url="http://127.0.0.1:4173",
                        )
                    except DemoError:
                        view_result = None

                    # Append the synthetic later observation only after the original run is immutable.
                    with source_path.open("a", newline="", encoding="utf-8") as stream:
                        csv.writer(stream).writerow(
                            [
                                assumptions["worker_observation"][key]
                                for key in ("time", "value", "published")
                            ]
                        )
                    disconnect_started = time.monotonic()

            # The active watch subscription polls the appended source while MCP
            # is disconnected; no assistant-side refresh tool is used here.
            inbox = None
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                inbox = _http_json(
                    http,
                    "GET",
                    "/v1/inbox",
                    params={"question_id": question_id, "offset": 0, "limit": 100},
                )
                if (
                    any(
                        item.get("event_kind") == "forecast_issued"
                        and item.get("watch_id") == watch_id
                        for item in inbox.get("events", [])
                    )
                    and webhook_received
                ):
                    break
                if supervisor.poll() is not None:
                    raise DemoError(
                        f"local supervisor exited during disconnected update; inspect {log_path}"
                    )
                time.sleep(0.25)
            else:
                raise DemoError(
                    "worker did not publish the disconnected forecast update and test webhook"
                )

            update_event = next(
                item
                for item in inbox["events"]
                if item.get("event_kind") == "forecast_issued"
                and item.get("watch_id") == watch_id
            )
            event_id = update_event["event_id"]
            successor_run_id = update_event.get("run_id") or update_event.get(
                "payload", {}
            ).get("run_id")
            watch_after = _http_json(
                http, "GET", f"/v1/watches/{quote(watch_id, safe='')}"
            )
            successor_run_id = successor_run_id or watch_after.get("last_run_id")
            if not successor_run_id:
                raise DemoError(
                    "forecast event did not identify its persisted successor run"
                )
            if successor_run_id == initial_run_id:
                raise DemoError("worker event did not identify a successor run")
            if not any(received_id == event_id for received_id, _ in webhook_received):
                raise DemoError("test webhook did not receive the forecast event")

            reconnect_started = time.monotonic()
            async with await _client(cli, config_path, workspace, env) as client:
                question_record = await _call(
                    client, "get_question", question_id=question_id
                )
                question_presentation = await _call(
                    client,
                    "get_question_presentation",
                    question_id=question_id,
                    offset=0,
                    limit=3,
                )
                if not any(
                    item["reference"]["target_type"] == "run"
                    and item["reference"]["target_id"] == successor_run_id
                    for item in question_presentation.get("references", [])
                ):
                    raise DemoError(
                        "worker successor run is not linked to the saved question"
                    )
                current_run = await _call(client, "get_run", run_id=successor_run_id)
                if current_run.get("run_id") != successor_run_id:
                    raise DemoError(
                        "reconnected MCP read returned a different successor run"
                    )
                change = await _call(
                    client,
                    "summarize_watch_change",
                    watch_id=watch_id,
                    previous_run_id=initial_run_id,
                    current_run_id=successor_run_id,
                )
                deliveries = await _call(
                    client,
                    "list_webhook_deliveries",
                    subscription_id=webhook_subscription["subscription_id"],
                    offset=0,
                    limit=50,
                )
                recovered_inbox = await _call(
                    client,
                    "list_inbox_events",
                    question_id=question_id,
                    offset=0,
                    limit=100,
                )
                if not any(
                    item.get("event_id") == event_id
                    for item in recovered_inbox.get("events", [])
                ):
                    raise DemoError(
                        "reconnected MCP inbox did not recover the worker event"
                    )
            reconnect_seconds = time.monotonic() - reconnect_started

            first_result = initial_run["results"].get("forecast") or initial_run[
                "results"
            ].get("model")
            baseline_result = initial_run["results"].get("baseline") or initial_run[
                "results"
            ].get("reference")
            if (
                not first_result
                or not baseline_result
                or first_result.get("provider_id") != "timestral"
            ):
                raise DemoError(
                    "first run did not preserve Timestral and baseline outputs"
                )
            metrics = _trim_partitions(backtest_summary)
            origin_count = sum(part.get("matched_count", 0) for part in metrics)
            update_payload = update_event.get("payload", {})
            quality = update_payload.get("quality") or watch_after.get("quality")
            reason = (
                update_payload.get("reason")
                or watch_after.get("quality_reason")
                or watch_after.get("requalification_reason")
            )
            if quality == "provisional" and not reason:
                raise DemoError(
                    "worker marked the successor provisional without exposing a reason"
                )
            delivery = next(
                item
                for item in deliveries["deliveries"]
                if item.get("event_id") == event_id
            )
            record = {
                "schema_version": 1,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "interface": "official MCP Python SDK over stdio",
                "sdk_version": sdk_version,
                "source": {
                    "id": "demand",
                    "fixture": "examples/release-demo/observations.csv",
                    "fixture_sha256": fixture_hash,
                    "snapshot_id": snapshot_id,
                    "snapshot_as_of": snapshot_summary["as_of"],
                    "observation_count": snapshot_summary["observation_count"],
                    "event_time_start": snapshot_summary["event_time_start"],
                    "event_time_end": snapshot_summary["event_time_end"],
                    "synthetic": True,
                    "assumptions": assumptions["assumptions"],
                },
                "forecast": {
                    "job_id": issued["job_id"],
                    "run_id": initial_run_id,
                    "state": initial_run["state"],
                    "as_of": initial_run.get("as_of", assumptions["initial_as_of"]),
                    "provider": first_result["provider_id"],
                    "provider_revision": first_result.get("provider_revision"),
                    "forecast": _point_rows(first_result),
                    "baseline_provider": baseline_result["provider_id"],
                    "baseline_forecast": _point_rows(baseline_result),
                },
                "historical_comparison": {
                    "backtest_id": backtest_id,
                    "status": backtest_summary.get("status"),
                    "origin_count": origin_count,
                    "partitions": metrics,
                    "interpretation_limit": backtest_summary.get(
                        "interpretation_limit",
                        "Synthetic historical origins describe this fixture only and do not establish general accuracy.",
                    ),
                },
                "question": {
                    "id": question_id,
                    "title": question_record["title"],
                    "revision": question_record["current_revision"],
                    "recovered_after_mcp_reconnect": bool(question_presentation),
                    "references": [
                        item["reference"]["target_type"]
                        for item in question_presentation.get("references", [])
                    ],
                    "exact_browser_link": browser_link["url"],
                    "context_view_tool_returned": view_result is not None,
                },
                "worker_update": {
                    "source_update_state": "processed_by_independent_worker",
                    "run_id": successor_run_id,
                    "source_snapshot_id": watch_after["source_snapshot_ids"][-1],
                    "observation": {
                        **assumptions["worker_observation"],
                        "unit": assumptions["unit"],
                    },
                    "event_id": event_id,
                    "event_kind": update_event["event_kind"],
                    "quality": quality,
                    "reason": reason,
                    "requalification_new_origins": watch_after.get(
                        "requalification_new_origins", 0
                    ),
                    "change_summary": change,
                    "webhook_state": delivery["state"],
                    "webhook_attempts": delivery["attempts"],
                    "received_while_mcp_disconnected": True,
                },
                "timings": {
                    "automation_seconds_to_first_forecast": round(
                        first_forecast_seconds, 3
                    ),
                    "automation_end_to_end_seconds": round(
                        time.monotonic() - started, 3
                    ),
                    "mcp_reconnect_recovery_seconds": round(reconnect_seconds, 3),
                    "disconnected_processing_seconds": round(
                        time.monotonic() - disconnect_started, 3
                    ),
                },
                "manual_steps_before_first_forecast": [
                    "Install the pinned Python dependencies and MCP extra.",
                    "Review the separate Timestral weights license and prepare the pinned model.",
                    "Review and explicitly approve the synthetic CSV mapping and UTC cutoff; the runner records this declared approval.",
                    "Choose a fresh private workspace path and run the reproduction command.",
                ],
                "provenance": {
                    "model": first_result.get("provider_revision"),
                    "weights_revision": model_status.get("revision"),
                    "code_revision": model_status.get("code_revision"),
                    "model_device": model_status.get("device"),
                    "model_dtype": model_status.get("dtype"),
                    "baseline": "seasonal_naive; independent comparator, not a silent fallback",
                    "dataset": "hand-authored synthetic CSV; no external data source",
                },
                "limits": [
                    "Synthetic values and a historical comparison on this fixture do not establish real-world accuracy or provider superiority.",
                    "No prepared model weights are included in the wheel or source archive.",
                ],
            }
            if quality == "provisional":
                record["worker_update"]["provisional_notice"] = {
                    "status": "provisional",
                    "reason": reason,
                }
            # Keep only public, allowlisted fields; the token, webhook secret and local paths are excluded.
            output = args.output.expanduser().resolve()
            public_data = _load_public_data(output)
            public_data["journey"] = record
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(public_data, indent=2, ensure_ascii=False, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
            return record
    finally:
        receiver.shutdown()
        receiver.server_close()
        receiver_thread.join(timeout=2)
        try:
            os.killpg(supervisor.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            supervisor.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        stop_deadline = time.monotonic() + 12
        while time.monotonic() < stop_deadline:
            try:
                os.killpg(supervisor.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            try:
                os.killpg(supervisor.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            supervisor.wait(timeout=5)
        log_stream.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cli",
        type=Path,
        default=Path(shutil.which("forecast-anything") or "forecast-anything"),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="new private workspace; it must not already contain config.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="site/demo-data.json or another output file",
    )
    args = parser.parse_args()
    try:
        record = asyncio.run(reproduce(args))
    except ExceptionGroup as error:
        details = []
        pending = [error]
        while pending:
            item = pending.pop()
            if isinstance(item, BaseExceptionGroup):
                pending.extend(item.exceptions)
            else:
                frames = traceback.extract_tb(item.__traceback__)
                location = (
                    f" at {frames[-1].name}:{frames[-1].lineno}" if frames else ""
                )
                details.append(f"{item}{location}")
        print(json.dumps({"ok": False, "error": "; ".join(details)}), file=sys.stderr)
        return 1
    except (DemoError, OSError, ValueError, httpx.HTTPError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "journey": record}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
