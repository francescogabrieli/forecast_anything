"""Baseline forecast journey over the real MCP transport."""

from __future__ import annotations

import asyncio
import time

from mcp_journey_calls import call, poll_job, source_spec

TOOLS = {
    "get_browser_link",
    "open_context_view",
    "create_question",
    "list_questions",
    "get_question",
    "update_question",
    "revise_question",
    "list_question_revisions",
    "get_question_revision",
    "link_question_reference",
    "list_question_references",
    "list_inbox_events",
    "list_source_subscriptions",
    "set_source_subscription",
    "create_webhook_subscription",
    "list_webhook_subscriptions",
    "update_webhook_subscription",
    "list_webhook_deliveries",
    "get_capabilities",
    "get_diagnostics",
    "create_operation",
    "update_operation",
    "list_operations",
    "get_operation",
    "submit_operation",
    "resume_operation",
    "list_sources",
    "preview_csv_source",
    "confirm_csv_source",
    "register_csv_source",
    "get_source_profile",
    "refresh_source",
    "get_job",
    "get_candidate",
    "submit_forecast",
    "submit_configured_forecast",
    "submit_backtest",
    "get_backtest",
    "get_backtest_presentation",
    "summarize_backtest",
    "list_backtest_origins",
    "get_run",
    "get_forecast_presentation",
    "get_question_presentation",
    "get_graph",
    "get_snapshot",
    "summarize_snapshot",
    "list_snapshot_series",
    "list_run_evaluations",
    "get_evaluation",
    "submit_evaluation",
    "get_events",
    "create_watch",
    "list_watches",
    "get_watch",
    "update_watch",
    "get_watch_history",
    "summarize_watch_change",
}


async def baseline_journey(workspace):
    workspace.wait_for_worker()
    async with workspace.client() as client:
        assert {t.name for t in (await client.list_tools()).tools} == TOOLS
        capabilities = await call(client, "get_capabilities")
        assert "seasonal_naive" in capabilities["providers"]
        registered = await call(
            client, "register_csv_source", spec=source_spec(workspace)
        )
        assert "location" not in registered and "secret_ref" not in registered
        job = await poll_job(client, registered["job_id"])
        candidate = await call(
            client, "get_candidate", candidate_id=job["result"]["candidate_ids"][0]
        )
        assert candidate["executable"]
        watch = await call(
            client,
            "create_watch",
            candidate_id=candidate["candidate_id"],
            next_due_at="2026-10-26T12:00:00Z",
        )
        assert watch["lifecycle"] == "candidate" and not watch["operational"]
        assert (await call(client, "get_watch", watch_id=watch["watch_id"])) == watch
        page = await call(client, "list_watches", limit=10)
        assert [item["watch_id"] for item in page["watches"]] == [watch["watch_id"]]
        watch = await call(
            client,
            "update_watch",
            watch_id=watch["watch_id"],
            muted=True,
            priority=5,
        )
        assert watch["muted"] and watch["priority"] == 5
        history = await call(
            client, "get_watch_history", watch_id=watch["watch_id"], limit=10
        )
        assert [item["event"]["kind"] for item in history["entries"]] == [
            "created",
            "muted",
            "priority_changed",
        ]
        assert history["next_offset"] is None
        snapshot = await call(
            client, "get_snapshot", snapshot_id=job["result"]["source_snapshot_ids"][0]
        )
        assert snapshot["as_of"] == "2026-10-23T12:00:00Z"
        assert len(snapshot["observations"]) == 3
        assert any(a.startswith("source_revision=") for a in snapshot["assumptions"])
        assert (await call(client, "list_sources"))["sources"][0][
            "source_id"
        ] == "sales"
        workspace.stop_worker()
        request = {
            "candidate_id": candidate["candidate_id"],
            "snapshot_ids": {"sales": snapshot["snapshot_id"]},
            "as_of": snapshot["as_of"],
            "key": "original-stable-forecast-key",
        }
        accepted = await call(client, "submit_forecast", **request)
        assert accepted["state"] == "pending"
    # There is no MCP process or connected assistant while the independent worker completes.
    assert workspace.get("/v1/jobs/" + accepted["job_id"])["state"] == "pending"
    workspace.start_worker()
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        offline = workspace.get("/v1/jobs/" + accepted["job_id"])
        assert offline["state"] != "failed", offline
        if offline["state"] == "completed":
            break
        await asyncio.sleep(0.03)
    assert offline["state"] == "completed", offline
    async with workspace.client(source_ids=["sales"]) as client:
        completed = await call(client, "get_job", job_id=accepted["job_id"])
        assert completed == offline
        run = await call(client, "get_run", run_id=completed["result"]["run_id"])
        assert run["state"] == "completed"
        assert run["evidence_ids"] == []
        forecast = run["results"]["forecast"]
        assert forecast["provider_id"] == "seasonal_naive"
        assert forecast["point"] == [[2.0]]
        assert forecast["timestamps"] == ["2026-10-24T00:00:00Z"]
        assert forecast["quantiles"] is None and forecast["paths"] is None
        replay = await call(client, "submit_forecast", **request)
        assert replay["job_id"] == accepted["job_id"]
        assert replay["result"]["run_id"] == run["run_id"]
        assert await call(client, "get_run", run_id=run["run_id"]) == run
        summary = await call(
            client,
            "summarize_watch_change",
            watch_id=watch["watch_id"],
            previous_run_id=run["run_id"],
            current_run_id=run["run_id"],
        )
        assert summary["question"] == candidate["reason"]
        assert summary["common_target_count"] >= 1
    return {"run": run, "candidate": candidate, "snapshot": snapshot}
