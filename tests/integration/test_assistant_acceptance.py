"""Public MCP acceptance: qualified recurring evidence survives real reconnects."""

import asyncio
from datetime import date, timedelta

import pytest

pytest.importorskip("mcp", reason="install the optional mcp extra")

from mcp_processes import LocalWorkspace, call, poll_job, source_spec


def test_assistant_watch_report_permissions_and_automatic_update(tmp_path):
    async def journey(workspace, webhook_url, received):
        start = date(2026, 1, 1)
        workspace.history.write_text(
            "time,value,published\n"
            + "".join(
                f"{start + timedelta(days=i)},{1 if i % 2 == 0 else 3},"
                f"{start + timedelta(days=i)}\n"
                for i in range(296)
            )
        )
        selection = dict(
            provider="seasonal_naive",
            options={"period": 2},
            horizon=1,
            baseline_period=1,
        )
        async with workspace.client() as client:
            registered = await call(
                client, "register_csv_source", spec=source_spec(workspace)
            )
            discovered = await poll_job(client, registered["job_id"])
            watch = await call(
                client,
                "create_watch",
                candidate_id=discovered["result"]["candidate_ids"][0],
                next_due_at="2026-10-24T12:00:00Z",
            )
            watch_id = watch["watch_id"]
            candidate_id = watch["candidate_id"]
            original_snapshots = watch["source_snapshot_ids"]
            question = await call(
                client,
                "create_question",
                key="saved-sales-continuity",
                title="Sales outlook",
                meaning="Forecast daily sales",
                source_ids=["sales"],
                selection=selection,
            )
            await call(
                client,
                "link_question_reference",
                question_id=question["question_id"],
                key="saved-sales-watch-link",
                revision=1,
                target_type="watch",
                target_id=watch_id,
            )
            webhook = workspace.post(
                "/v1/webhook-subscriptions",
                {"target_url": webhook_url, "active": True},
            )
        request = dict(
            key="qualified-assistant",
            source_id="sales",
            selection=selection,
            settings={"max_origins_per_partition": 30},
            watch_id=watch_id,
        )
        # New MCP process has no source grant; explicit access is required again.
        async with workspace.client() as client:
            await call(client, "submit_backtest", error="source_forbidden", **request)
        async with workspace.client(source_ids=["sales"]) as client:
            await call(
                client,
                "submit_backtest",
                error="validation_error",
                **{
                    **request,
                    "key": "mismatch",
                    "selection": {**selection, "horizon": 2},
                },
            )
            job = await call(client, "submit_backtest", **request)
            completed = await poll_job(client, job["job_id"])
            backtest_id = completed["result"]["backtest_id"]
            summary = await call(
                client, "summarize_backtest", backtest_id=backtest_id, watch_id=watch_id
            )
            report = await call(client, "get_backtest", backtest_id=backtest_id)
            assert summary["partitions"] == report["partitions"]
            assert summary["watch"]["linked_to_backtest"]
            assert summary["watch"]["operational"]
            assert summary["watch"]["final_evaluation_count"] == 30
            assert len(summary["final_origin_points"]) == 30
            assert all(
                p["model_mae"] == 0 and p["baseline_mae"] == 2
                for p in summary["final_origin_points"]
            )
            assert "do not establish future accuracy" in summary["interpretation_limit"]
            assert (await call(client, "submit_backtest", **request))["job_id"] == job[
                "job_id"
            ]
        # Stop and restart API/worker; fresh MCP connection has revoked source access.
        workspace.stop_worker()
        workspace.stop(workspace.api)
        workspace.api = workspace.launch("api")
        await workspace.wait_api()
        workspace.start_worker()
        async with workspace.client() as client:
            assert await call(client, "get_backtest", backtest_id=backtest_id) == report
            assert (
                await call(
                    client,
                    "summarize_backtest",
                    backtest_id=backtest_id,
                    watch_id=watch_id,
                )
                == summary
            )
            await call(
                client,
                "get_source_profile",
                source_id="sales",
                error="source_forbidden",
            )
        # Change source and clock while disconnected. Only the independent worker
        # schedules source refresh and successor discovery; no manual refresh call.
        with workspace.history.open("a") as stream:
            stream.write("2026-10-24,7,2026-10-24\n")
        workspace.set_clock("2026-10-24T12:00:00+00:00")
        deadline = asyncio.get_running_loop().time() + 12
        while True:
            watches = workspace.get("/v1/watches")
            updated = next((w for w in watches if w["watch_id"] == watch_id), None)
            if (
                updated is not None
                and len(updated["source_snapshot_ids"]) > len(original_snapshots)
                and updated.get("last_run_id") is not None
                and any(
                    payload.get("question_id") == question["question_id"]
                    and payload.get("event_kind") == "forecast_issued"
                    for _, payload in received
                )
            ):
                break
            assert asyncio.get_running_loop().time() < deadline, watches
            await asyncio.sleep(0.05)
        async with workspace.client() as client:
            old = await call(client, "get_watch", watch_id=watch_id)
            assert old["candidate_id"] == candidate_id
            assert not old["candidate_invalidated"] and not old["operational"]
            assert old["quality"] == "provisional"
            assert not old["evidence_applicable"]
            assert old["source_snapshot_ids"][-1] != original_snapshots[-1]
            assert await call(client, "get_backtest", backtest_id=backtest_id) == report
            changed = await call(
                client, "summarize_backtest", backtest_id=backtest_id, watch_id=watch_id
            )
            assert changed["partitions"] == summary["partitions"]
            assert not changed["watch"]["operational"]
            inbox = await call(
                client,
                "list_inbox_events",
                question_id=question["question_id"],
                limit=100,
            )
            updates = [
                event
                for event in inbox["events"]
                if event["event_kind"] == "forecast_issued"
            ]
            assert updates and updates[0]["payload"]["quality"] == "provisional"
            deliveries = workspace.get(
                f"/v1/webhook-subscriptions/{webhook['subscription_id']}/deliveries"
            )
            forecast_delivery = next(
                delivery
                for delivery in deliveries["deliveries"]
                if delivery["event_id"]
                == next(
                    event_id
                    for event_id, payload in received
                    if payload.get("question_id") == question["question_id"]
                    and payload.get("event_kind") == "forecast_issued"
                )
            )
            assert forecast_delivery["state"] == "delivered"
            assert forecast_delivery["attempts"] == 1
            recovered_question = await call(
                client, "get_question", question_id=question["question_id"]
            )
            assert recovered_question["question_id"] == question["question_id"]
            assert recovered_question["current_revision"] == 1
            recovered_references = await call(
                client,
                "list_question_references",
                question_id=question["question_id"],
                revision=1,
                limit=5,
            )
            assert any(
                reference["target_type"] == "run"
                and reference["target_id"] == updated["last_run_id"]
                for reference in recovered_references["references"]
            )
            entries = []
            offset = 0
            while True:
                history = await call(
                    client,
                    "get_watch_history",
                    watch_id=watch_id,
                    offset=offset,
                    limit=1,
                )
                entries.extend(history["entries"])
                if history["next_offset"] is None:
                    break
                offset = history["next_offset"]
            assert len(entries) >= 3

    import json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    received = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            event_id = self.headers.get("X-Forecast-Event-Id")
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((event_id, payload))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        webhook_url = f"http://127.0.0.1:{server.server_port}/updates"
        with LocalWorkspace(tmp_path) as workspace:
            asyncio.run(journey(workspace, webhook_url, received))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_assistant_corrects_temporal_mapping_and_persists_source_grants(tmp_path):
    import json
    import subprocess

    from forecast_anything.workspace_config import create_workspace

    async def journey(workspace):
        spec = source_spec(workspace)
        spec["mapping"].pop("timezone")
        async with workspace.client() as client:
            unresolved = await call(client, "register_csv_source", spec=spec)
            assert "timezone" in unresolved["profile"]["unresolved"]
            spec["mapping"]["timezone"] = {"constant": "UTC"}
            corrected = await call(client, "register_csv_source", spec=spec)
            assert "timezone" not in corrected["profile"]["unresolved"]
            await poll_job(client, corrected["job_id"])
        config = create_workspace(workspace.root, workspace.root, workspace.port)
        for action, expected in (("grant", ["sales"]), ("revoke", [])):
            result = subprocess.run(
                [
                    workspace.executable,
                    "permissions",
                    action,
                    "sales",
                    "--config",
                    str(config),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            assert json.loads(result.stdout)["restart_required"]
            grants = json.loads(config.read_text())["source_ids"]
            assert grants == expected
            async with workspace.client(source_ids=grants) as client:
                profile = await call(
                    client,
                    "get_source_profile",
                    source_id="sales",
                    **({"error": "source_forbidden"} if action == "revoke" else {}),
                )
                if action == "grant":
                    assert "timezone" not in profile["unresolved"]
                else:
                    assert len((await call(client, "list_sources"))["sources"]) == 1

    with LocalWorkspace(tmp_path) as workspace:
        asyncio.run(journey(workspace))
