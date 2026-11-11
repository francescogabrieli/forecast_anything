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
import subprocess
import sys
import threading
import time
import traceback
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from phase7_demo_support import (
    DemoError,
    _call,
    _candidate_selection,
    _client,
    _free_port,
    _http_json,
    _poll_mcp_job,
    _run_cli,
    _source_spec,
    stop_services,
    wait_for_update,
    write_demo_record,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "release-demo"


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
                            datetime.now(UTC) + timedelta(seconds=2)
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

            update_event, event_id, successor_run_id, watch_after = wait_for_update(
                http=http,
                question_id=question_id,
                watch_id=watch_id,
                webhook_received=webhook_received,
                supervisor=supervisor,
                log_path=log_path,
                initial_run_id=initial_run_id,
            )

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

            return write_demo_record(
                args=args,
                assumptions=assumptions,
                fixture_hash=fixture_hash,
                snapshot_id=snapshot_id,
                snapshot_summary=snapshot_summary,
                issued=issued,
                initial_run_id=initial_run_id,
                initial_run=initial_run,
                backtest_id=backtest_id,
                backtest_summary=backtest_summary,
                question_id=question_id,
                question_record=question_record,
                question_presentation=question_presentation,
                browser_link=browser_link,
                view_result=view_result,
                update_event=update_event,
                watch_after=watch_after,
                deliveries=deliveries,
                event_id=event_id,
                successor_run_id=successor_run_id,
                change=change,
                first_forecast_seconds=first_forecast_seconds,
                started=started,
                reconnect_seconds=reconnect_seconds,
                disconnect_started=disconnect_started,
                model_status=model_status,
                sdk_version=sdk_version,
            )
    finally:
        stop_services(receiver, receiver_thread, supervisor, log_stream)


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
