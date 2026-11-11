"""Process, MCP and report helpers for the release demo."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client


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


def wait_for_update(
    *,
    http,
    question_id,
    watch_id,
    webhook_received,
    supervisor,
    log_path,
    initial_run_id,
):
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
    watch_after = _http_json(http, "GET", f"/v1/watches/{quote(watch_id, safe='')}")
    successor_run_id = successor_run_id or watch_after.get("last_run_id")
    if not successor_run_id:
        raise DemoError("forecast event did not identify its persisted successor run")
    if successor_run_id == initial_run_id:
        raise DemoError("worker event did not identify a successor run")
    if not any(received_id == event_id for received_id, _ in webhook_received):
        raise DemoError("test webhook did not receive the forecast event")
    return update_event, event_id, successor_run_id, watch_after


def write_demo_record(
    *,
    args,
    assumptions,
    fixture_hash,
    snapshot_id,
    snapshot_summary,
    issued,
    initial_run_id,
    initial_run,
    backtest_id,
    backtest_summary,
    question_id,
    question_record,
    question_presentation,
    browser_link,
    view_result,
    update_event,
    watch_after,
    deliveries,
    event_id,
    successor_run_id,
    change,
    first_forecast_seconds,
    started,
    reconnect_seconds,
    disconnect_started,
    model_status,
    sdk_version,
):
    first_result = initial_run["results"].get("forecast") or initial_run["results"].get(
        "model"
    )
    baseline_result = initial_run["results"].get("baseline") or initial_run[
        "results"
    ].get("reference")
    if (
        not first_result
        or not baseline_result
        or first_result.get("provider_id") != "timestral"
    ):
        raise DemoError("first run did not preserve Timestral and baseline outputs")
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
        item for item in deliveries["deliveries"] if item.get("event_id") == event_id
    )
    record = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
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
            "automation_seconds_to_first_forecast": round(first_forecast_seconds, 3),
            "automation_end_to_end_seconds": round(time.monotonic() - started, 3),
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
        json.dumps(public_data, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return record


def stop_services(receiver, receiver_thread, supervisor, log_stream):
    receiver.shutdown()
    receiver.server_close()
    receiver_thread.join(timeout=2)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(supervisor.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        supervisor.wait(timeout=5)
    stop_deadline = time.monotonic() + 12
    while time.monotonic() < stop_deadline:
        try:
            os.killpg(supervisor.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(supervisor.pid, signal.SIGKILL)
        supervisor.wait(timeout=5)
    log_stream.close()
