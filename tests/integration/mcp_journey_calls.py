"""MCP journey tool calls and CSV registration data."""

from __future__ import annotations

import asyncio
import json
import time


def source_spec(workspace, source_id="sales"):
    return {
        "source_id": source_id,
        "kind": "csv",
        "location": str(workspace.history),
        "refresh_seconds": 864000,
        "mapping": {
            "event_time": "time",
            "value": "value",
            "available_at": "published",
            "revision": {"constant": "1"},
            "series_id": {"constant": "sales"},
            "unit": {"constant": "count"},
            "frequency": {"constant": "1d"},
            "timezone": {"constant": "UTC"},
            "calendar": {"constant": "gregorian"},
            "missing_values": {"constant": [""]},
        },
    }


async def call(client, name, *, error=None, **arguments):
    result = await client.call_tool(name, arguments)
    assert len(result.model_dump_json(by_alias=True).encode("utf-8")) <= 65536
    envelope = result.structured_content
    assert envelope is not None
    assert json.loads(result.content[0].text) == envelope
    assert result.is_error is (error is not None), envelope
    if error is not None:
        assert envelope["ok"] is False and envelope["code"] == error, envelope
        client.fixture_errors.append(json.dumps(envelope))
        return envelope
    assert envelope["ok"] is True, envelope
    return envelope["data"]


async def poll_job(client, job_id):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        job = await call(client, "get_job", job_id=job_id)
        assert job["state"] not in {"failed", "cancelled"}, job
        if job["state"] == "completed":
            return job
        await asyncio.sleep(0.03)
    raise AssertionError(f"job did not complete: {job_id}")
