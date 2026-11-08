"""Guided CSV preview is available before registration through MCP."""

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp_processes import LocalWorkspace, call, poll_job, source_spec


def test_csv_preview_before_registration(tmp_path):
    async def journey(workspace):
        spec = source_spec(workspace, "sales")
        spec["mapping"] = {}
        async with workspace.client(source_ids=[]) as client:
            preview = await call(
                client, "preview_csv_source", spec=spec, as_of="2026-10-24T12:00:00Z"
            )
            assert preview["profile"]["proposed_mapping"]["value"] == "value"
            assert "timezone" in preview["profile"]["unresolved"]
            assert len(preview["content_digest"]) == 64
            assert len(preview["proposal_version"]) == 64
            assert (await call(client, "list_sources"))["sources"] == []

    with LocalWorkspace(
        tmp_path, source_root=Path(__file__).resolve().parents[2]
    ) as workspace:
        asyncio.run(journey(workspace))


def test_confirmation_rejects_replaced_file_and_captures_confirmed_bytes(tmp_path):
    async def journey(workspace):
        spec = source_spec(workspace, "sales")
        async with workspace.client(source_ids=[]) as client:
            preview = await call(
                client, "preview_csv_source", spec=spec, as_of="2026-10-24T12:00:00Z"
            )
            await call(
                client,
                "confirm_csv_source",
                error="source_content_changed",
                spec=spec,
                key="wrong-cutoff",
                proposal_version=preview["proposal_version"],
                as_of="2026-10-25T12:00:00Z",
            )
            original = workspace.history.read_text()
            workspace.history.write_text("invalid,invalid\n")
            await call(
                client,
                "confirm_csv_source",
                error="source_content_changed",
                spec=spec,
                key="bad-replacement",
                proposal_version=preview["proposal_version"],
                as_of="2026-10-24T12:00:00Z",
            )
            workspace.history.write_text(original.replace(",1,", ",11,"))
            await call(
                client,
                "confirm_csv_source",
                error="source_content_changed",
                spec=spec,
                key="capture-sales",
                proposal_version=preview["proposal_version"],
                as_of="2026-10-24T12:00:00Z",
            )
            fresh = await call(
                client, "preview_csv_source", spec=spec, as_of="2026-10-24T12:00:00Z"
            )
            accepted = await call(
                client,
                "confirm_csv_source",
                spec=spec,
                key="capture-sales",
                proposal_version=fresh["proposal_version"],
                as_of="2026-10-24T12:00:00Z",
            )
            # A replacement after acceptance cannot change the frozen capture.
            workspace.history.unlink()
        async with workspace.client(source_ids=[]) as client:
            replay = await call(
                client,
                "confirm_csv_source",
                spec=spec,
                key="capture-sales",
                proposal_version=fresh["proposal_version"],
                as_of="2026-10-24T12:00:00Z",
            )
            assert replay["job_id"] == accepted["job_id"]
            job = await poll_job(client, accepted["job_id"])
            assert job["state"] == "completed"
            assert job["result"]["source_snapshot_ids"]
            snap = await call(
                client,
                "get_snapshot",
                snapshot_id=job["result"]["source_snapshot_ids"][0],
            )
            assert [row["value"] for row in snap["observations"]] == [11, 2, 3]
            summary = await call(
                client, "summarize_snapshot", snapshot_id=snap["snapshot_id"]
            )
            assert (
                f"csv_content_sha256={fresh['content_digest']}"
                in summary["assumptions"]
            )
            await call(
                client,
                "confirm_csv_source",
                error="conflict",
                spec=spec,
                key="capture-sales",
                proposal_version=fresh["proposal_version"],
                as_of="2026-10-25T12:00:00Z",
            )

    with LocalWorkspace(
        tmp_path, source_root=Path(__file__).resolve().parents[2]
    ) as workspace:
        asyncio.run(journey(workspace))


def test_preview_offers_observed_hints_without_resolving_semantics(tmp_path):
    async def journey(workspace):
        workspace.history.write_text(
            "date,value,unit\n2026-10-21,1,kWh\n2026-10-22,2,kWh\n2026-10-23,3,kWh\n"
        )
        spec = source_spec(workspace, "sales")
        spec["mapping"] = {}
        async with workspace.client(source_ids=[]) as client:
            preview = await call(
                client, "preview_csv_source", spec=spec, as_of="2026-10-24T12:00:00Z"
            )
            assert preview["suggestions"] == {"frequency": "1d", "unit": "kWh"}
            assert "frequency" in preview["profile"]["unresolved"]
            assert "unit" in preview["profile"]["unresolved"]

    with LocalWorkspace(
        tmp_path, source_root=Path(__file__).resolve().parents[2]
    ) as workspace:
        asyncio.run(journey(workspace))


def test_guided_preview_distinguishes_missing_file_from_forbidden_path(tmp_path):
    async def journey(workspace):
        spec = source_spec(workspace, "sales")
        async with workspace.client(source_ids=[]) as client:
            await call(
                client,
                "preview_csv_source",
                error="source_unavailable",
                spec={**spec, "location": str(workspace.root / "missing.csv")},
                as_of="2026-10-24T12:00:00Z",
            )
            await call(
                client,
                "preview_csv_source",
                error="source_forbidden",
                spec={**spec, "location": "/etc/passwd"},
                as_of="2026-10-24T12:00:00Z",
            )

    with LocalWorkspace(
        tmp_path, source_root=Path(__file__).resolve().parents[2]
    ) as workspace:
        asyncio.run(journey(workspace))


def test_ambiguous_irregular_data_remains_unresolved(tmp_path):
    async def journey(workspace):
        workspace.history.write_text(
            "date,time,value,unit\n"
            "2026-10-20,2026-10-20,1,kWh\n"
            "2026-10-21,2026-10-21,2,MW\n"
            "2026-10-23,2026-10-23,3,kWh\n"
        )
        spec = source_spec(workspace, "sales")
        spec["mapping"] = {}
        async with workspace.client(source_ids=[]) as client:
            preview = await call(
                client, "preview_csv_source", spec=spec, as_of="2026-10-24T12:00:00Z"
            )
            assert "event_time" in preview["profile"]["unresolved"]
            assert "event_time" not in preview["profile"]["proposed_mapping"]
            assert preview["suggestions"] == {}
            await call(
                client,
                "confirm_csv_source",
                error="unresolved_source_mapping",
                spec=spec,
                key="unresolved",
                proposal_version=preview["proposal_version"],
                as_of="2026-10-24T12:00:00Z",
            )
            assert (await call(client, "list_sources"))["sources"] == []

    with LocalWorkspace(
        tmp_path, source_root=Path(__file__).resolve().parents[2]
    ) as workspace:
        asyncio.run(journey(workspace))
