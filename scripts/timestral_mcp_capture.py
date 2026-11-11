"""Capture a guided CSV and its first Timestral forecast over MCP."""

import asyncio
import time
from datetime import UTC, datetime

from forecast_anything.providers.configuration import (
    TIMESTRAL_CHECKPOINT,
    TIMESTRAL_CODE_REVISION,
    TIMESTRAL_REVISION,
)

JOB_TIMEOUT_SECONDS = 180


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


async def capture_forecast(mcp, csv, evidence):
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
    cutoff = datetime.now(UTC).isoformat()
    initial_preview = await call(
        mcp, "preview_csv_source", spec={**spec, "mapping": {}}, as_of=cutoff
    )
    assert "timezone" in initial_preview["profile"]["unresolved"]
    preview = await call(mcp, "preview_csv_source", spec=spec, as_of=cutoff)
    confirmation = {
        "spec": spec,
        "proposal_version": preview["proposal_version"],
        "as_of": cutoff,
        "key": "guided-real-capture",
    }
    registration = await call(mcp, "confirm_csv_source", **confirmation)
    evidence["guided_preview"] = {
        "proposal_version": preview["proposal_version"],
        "content_digest": preview["content_digest"],
        "job_id": registration["job_id"],
    }
    discovery = await poll(mcp, registration["job_id"])
    candidate_id = discovery["candidate_ids"][0]
    candidate = await call(mcp, "get_candidate", candidate_id=candidate_id)
    assert (
        next(n for n in candidate["graph"]["nodes"] if n["node_id"] == "forecast")[
            "config"
        ]["provider"]
        == "timestral"
    )
    snapshot_id = discovery["source_snapshot_ids"][0]
    snapshot_summary = await call(mcp, "summarize_snapshot", snapshot_id=snapshot_id)
    assert snapshot_summary["observation_count"] == 360
    assert (
        f"csv_content_sha256={preview['content_digest']}"
        in snapshot_summary["assumptions"]
    )
    evidence["snapshot_summary"] = snapshot_summary
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
    question = await call(
        mcp,
        "create_question",
        key="real-question",
        title="Synthetic sales outlook",
        meaning="Forecast daily synthetic sales one day ahead",
        source_ids=[spec["source_id"]],
        selection=selection,
    )
    operation = await call(
        mcp,
        "create_operation",
        key="real-operation",
        question_id=question["question_id"],
        question_revision=question["current_revision"],
        phase="ready",
        missing_data=[],
    )
    configured = await call(
        mcp,
        "submit_operation",
        operation_id=operation["operation_id"],
        expected_version=operation["version"],
        request={"kind": "configured_run", **configured_request},
    )
    evidence["question_id"] = question["question_id"]
    evidence["operation_id"] = operation["operation_id"]
    configured_run = await call(
        mcp, "get_run", run_id=(await poll(mcp, configured["job_id"]))["run_id"]
    )
    assert configured_run["primary_node_id"] == "model"
    assert configured_run["results"]["model"]["provider_id"] == "timestral"
    assert (
        configured_run["results"]["model"]["provider_revision"]
        == f"{TIMESTRAL_CHECKPOINT}@{TIMESTRAL_REVISION};code={TIMESTRAL_CODE_REVISION}"
    )
    assert configured_run["results"]["baseline"]["provider_id"] == "seasonal_naive"
    evidence["configured_run"] = configured_run
    forecast_view = await call(
        mcp, "get_forecast_presentation", run_id=configured_run["run_id"]
    )
    assert forecast_view["primary_node_id"] == "model"
    evidence["forecast_presentation"] = forecast_view
    await call(
        mcp,
        "link_question_reference",
        question_id=question["question_id"],
        key="link-run",
        revision=question["current_revision"],
        target_type="run",
        target_id=configured_run["run_id"],
    )
    before = await call(
        mcp,
        "submit_forecast",
        candidate_id=candidate_id,
        snapshot_ids={spec["source_id"]: snapshot_id},
        as_of=configured_run["as_of"],
        key="real-before",
    )
    before_id = (await poll(mcp, before["job_id"]))["run_id"]
    return (
        spec,
        selection,
        candidate_id,
        before_id,
        question,
        operation,
        configured,
        configured_run,
    )
