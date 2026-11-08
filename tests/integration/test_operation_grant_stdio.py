"""A queued operation remains readable while source permission is revoked."""

import asyncio

import pytest

pytest.importorskip("mcp")

from mcp_processes import LocalWorkspace, call, poll_job, source_spec


def test_queued_backtest_requires_current_grant_to_resume(tmp_path):
    async def journey(workspace):
        async with workspace.client(source_ids=["sales"]) as client:
            spec = source_spec(workspace)
            as_of = "2026-10-23T12:00:00Z"
            preview = await call(client, "preview_csv_source", spec=spec, as_of=as_of)
            confirm = {
                "spec": spec,
                "as_of": as_of,
                "proposal_version": preview["proposal_version"],
                "key": "grant-capture",
            }
            registered = await call(client, "confirm_csv_source", **confirm)
            await poll_job(client, registered["job_id"])
            workspace.stop_worker()
            operation = await call(
                client,
                "create_operation",
                key="grant-recovery",
                phase="ready",
                missing_data=[],
            )
            operation_id = operation["operation_id"]
            submitted = await call(
                client,
                "submit_operation",
                operation_id=operation_id,
                expected_version=1,
                request={
                    "kind": "backtest",
                    "key": "grant-backtest",
                    "source_id": "sales",
                    "selection": {"provider": "seasonal_naive", "horizon": 1},
                    "settings": {"max_origins_per_partition": 2},
                },
            )
            job_id = submitted["job_id"]
            assert (await call(client, "get_job", job_id=job_id))["state"] == "pending"

        async with workspace.client(source_ids=[]) as revoked:
            replay = await call(revoked, "confirm_csv_source", **confirm)
            assert replay["job_id"] == registered["job_id"]
            assert (await call(revoked, "get_operation", operation_id=operation_id))[
                "job_id"
            ] == job_id
            assert (await call(revoked, "get_job", job_id=job_id))["state"] == "pending"
            await call(
                revoked,
                "resume_operation",
                operation_id=operation_id,
                error="source_forbidden",
            )

        async with workspace.client(source_ids=["sales"]) as restored:
            resumed = await asyncio.gather(
                *[
                    call(restored, "resume_operation", operation_id=operation_id)
                    for _ in range(3)
                ]
            )
            assert {item["job_id"] for item in resumed} == {job_id}
            assert (await call(restored, "get_job", job_id=job_id))[
                "state"
            ] == "pending"
            operations = await call(restored, "list_operations")
            assert [item["job_id"] for item in operations["operations"]] == [job_id]

    with LocalWorkspace(tmp_path) as workspace:
        asyncio.run(journey(workspace))
