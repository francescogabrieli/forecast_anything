"""Fresh MCP processes can recover durable questions and revision links."""

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="install the optional mcp extra")

from mcp_processes import LocalWorkspace, baseline_journey, call


def test_question_revisions_and_references_survive_mcp_reconnect(tmp_path):
    async def journey(workspace):
        issued = await baseline_journey(workspace)
        run = issued["run"]
        create = {
            "key": "persistent-demand-question",
            "title": "Demand outlook",
            "meaning": "Forecast daily demand for the next day",
            "source_ids": ["sales"],
            "selection": {"provider": "seasonal_naive", "horizon": 1},
        }
        async with workspace.client(source_ids=["sales"]) as client:
            forecast_presentation = await call(
                client,
                "get_forecast_presentation",
                run_id=run["run_id"],
            )
            assert forecast_presentation == workspace.get(
                f"/v1/runs/{run['run_id']}/presentation"
            )
            question = await call(client, "create_question", **create)
            assert question["current_revision"] == 1
            for kind, resource_id in (
                ("run", run["run_id"]),
                ("question", question["question_id"]),
            ):
                link = await call(
                    client,
                    "get_browser_link",
                    kind=kind,
                    resource_id=resource_id,
                    browser_url="http://127.0.0.1:4173",
                )
                assert (
                    link["url"]
                    == f"http://127.0.0.1:4173/#/w/{link['workspace_id']}/{kind}/{resource_id}"
                )
                assert (
                    link["workspace_id"]
                    == workspace.get("/v1/workspace")["workspace_id"]
                )
                assert workspace.token not in str(link)
            reference = await call(
                client,
                "link_question_reference",
                question_id=question["question_id"],
                key="link-issued-run",
                revision=1,
                target_type="run",
                target_id=run["run_id"],
                note="Issued against the recorded snapshot.",
            )
            assert reference["revision"] == 1
            revised = await call(
                client,
                "revise_question",
                question_id=question["question_id"],
                key="question-revision-2",
                expected_revision=1,
                meaning="Forecast demand for the next two days",
                source_ids=["sales"],
                selection={"provider": "seasonal_naive", "horizon": 2},
            )
            assert revised["current_revision"] == 2
            renamed = await call(
                client,
                "update_question",
                question_id=question["question_id"],
                title="Two day demand outlook",
            )
            assert renamed["current_revision"] == 2

            operation_args = {
                "key": "reconnectable-evaluation",
                "question_id": question["question_id"],
                "question_revision": 2,
                "phase": "ready",
                "missing_data": [],
            }
            operation_results = await asyncio.gather(
                call(client, "create_operation", **operation_args),
                call(client, "create_operation", **operation_args),
            )
            operation = operation_results[0]
            assert operation_results[1] == operation
            operation_reference = await call(
                client,
                "link_question_reference",
                question_id=question["question_id"],
                key="link-durable-operation",
                revision=2,
                target_type="operation",
                target_id=operation["operation_id"],
            )
            renamed = await call(
                client, "get_question", question_id=question["question_id"]
            )
            await call(
                client,
                "create_operation",
                error="conflict",
                **{**operation_args, "phase": "collecting"},
            )
            submit_args = {
                "operation_id": operation["operation_id"],
                "expected_version": 1,
                "request": {
                    "kind": "evaluation",
                    "key": "mcp-evaluation-retry-key",
                    "run_id": run["run_id"],
                    "actuals_snapshot_id": issued["snapshot"]["snapshot_id"],
                },
            }
            submitted = await asyncio.gather(
                call(client, "submit_operation", **submit_args),
                call(client, "submit_operation", **submit_args),
            )
            assert submitted[0]["job_id"] == submitted[1]["job_id"]
            assert submitted[0]["request_digest"] == submitted[1]["request_digest"]

        async with workspace.client(source_ids=["sales"]) as reconnected:
            recovered = await call(
                reconnected, "get_question", question_id=question["question_id"]
            )
            assert recovered == renamed
            presentation = await call(
                reconnected,
                "get_question_presentation",
                question_id=question["question_id"],
                offset=0,
                limit=3,
            )
            assert presentation == workspace.get(
                f"/v1/questions/{question['question_id']}/presentation"
            )
            applicability = {
                item["reference"]["target_type"]: item["applies_to_current_revision"]
                for item in presentation["references"]
            }
            assert applicability == {"run": False, "operation": True}
            revisions = await call(
                reconnected,
                "list_question_revisions",
                question_id=question["question_id"],
                offset=0,
                limit=1,
            )
            assert revisions["revisions"][0]["revision"] == 1
            assert revisions["next_offset"] == 1
            historical = await call(
                reconnected,
                "get_question_revision",
                question_id=question["question_id"],
                revision=1,
            )
            assert historical["meaning"] == "Forecast daily demand for the next day"
            references = await call(
                reconnected,
                "list_question_references",
                question_id=question["question_id"],
            )
            assert references["references"] == sorted(
                [reference, operation_reference], key=lambda item: item["reference_id"]
            )
            assert (
                await call(
                    reconnected,
                    "list_questions",
                    offset=0,
                    limit=2,
                )
            )["questions"] == [recovered]
            resumed = await call(
                reconnected,
                "resume_operation",
                operation_id=operation["operation_id"],
            )
            assert resumed["job_id"] == submitted[0]["job_id"]
            assert resumed["request_digest"] == submitted[0]["request_digest"]
            stored_operations = await call(
                reconnected, "list_operations", question_id=question["question_id"]
            )
            assert [
                item["operation_id"] for item in stored_operations["operations"]
            ] == [operation["operation_id"]]
            result = await call(
                reconnected,
                "get_job",
                job_id=submitted[0]["job_id"],
            )
            assert result["state"] in {"pending", "running", "completed"}

    with LocalWorkspace(
        tmp_path, source_root=Path(__file__).resolve().parents[2]
    ) as workspace:
        asyncio.run(journey(workspace))


def test_context_view_resource_and_text_fallback_over_stdio(tmp_path):
    from mcp.client.extension import advertise

    async def journey(workspace):
        issued = await baseline_journey(workspace)
        async with workspace.client(source_ids=["sales"]) as client:
            tools = await client.list_tools()
            view_tool = next(
                tool for tool in tools.tools if tool.name == "open_context_view"
            )
            assert (
                view_tool.meta["ui"]["resourceUri"]
                == "ui://forecast-anything/context.html"
            )
            resources = await client.list_resources()
            assert any(
                item.uri == "ui://forecast-anything/context.html"
                and item.mime_type == "text/html;profile=mcp-app"
                for item in resources.resources
            )
            html = await client.read_resource("ui://forecast-anything/context.html")
            assert html.contents[0].mime_type == "text/html;profile=mcp-app"
            result = await client.call_tool(
                "open_context_view",
                {
                    "kind": "run",
                    "resource_id": issued["run"]["run_id"],
                    "browser_url": "http://127.0.0.1:4173",
                },
            )
            assert not result.is_error
            data = result.structured_content["data"]
            assert data["presentation"]["run_id"] == issued["run"]["run_id"]
            assert data["browser_link"]["url"] in result.content[0].text
            assert workspace.token not in result.model_dump_json()
            assert len(result.model_dump_json(by_alias=True).encode()) <= 65536
            expected = data
        for extensions in (
            [advertise("io.modelcontextprotocol/ui", {"mimeTypes": []})],
            [
                advertise(
                    "io.modelcontextprotocol/ui",
                    {"mimeTypes": ["text/html;profile=mcp-app"]},
                )
            ],
        ):
            async with workspace.client(
                source_ids=["sales"], extensions=extensions, mode="auto"
            ) as reconnected:
                assert (
                    "io.modelcontextprotocol/ui"
                    in reconnected.server_capabilities.extensions
                )
                result = await reconnected.call_tool(
                    "open_context_view",
                    {
                        "kind": "run",
                        "resource_id": issued["run"]["run_id"],
                        "browser_url": "http://127.0.0.1:4173",
                    },
                )
                assert result.structured_content["data"] == expected
                assert expected["browser_link"]["url"] in result.content[0].text

    with LocalWorkspace(tmp_path) as workspace:
        asyncio.run(journey(workspace))
