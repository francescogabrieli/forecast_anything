"""One hand-checkable public-tool journey, reusable against the installed wheel.

Mutations this catches: recapturing CSV on recovery, latest-only history, model
options/horizon dropped, duplicated child emissions, or biased score denominators.
"""

import asyncio
import json
import sqlite3
import time

from mcp_processes import call, poll_job, source_spec


async def wait_file(path):
    deadline = time.monotonic() + 12
    while not path.exists():
        assert time.monotonic() < deadline, f"worker did not reach {path.name}"
        await asyncio.sleep(0.03)


def stored(workspace, table, backtest_id):
    assert table in {"backtest_plans", "backtest_origins", "backtest_reports"}
    with sqlite3.connect(workspace.root / "state.db") as db:
        return [
            json.loads(row[0])
            for row in db.execute(
                f"SELECT content FROM {table} WHERE backtest_id = ? ORDER BY rowid",
                (backtest_id,),
            )
        ]


def write_evidence_history(workspace, *, gaps=False):
    # Jan 1..24 alternates 1,3. period=2 is perfect; period=1 repeats the
    # origin value, giving absolute errors (2,0), MAE=1 per two-cell window.
    rows = ["time,value,published,revision"]
    for day in range(1, 25):
        if gaps and day == 14:
            continue
        published = f"2026-01-{day:02}"
        if gaps and day == 3:
            published = "2026-01-04"  # unavailable at the second origin
        rows.append(f"2026-01-{day:02},{1 if day % 2 else 3},{published},1")
    rows += [
        "2026-01-01,9,2026-01-10,2",  # only later histories see this revision
        "2026-02-20,999,2026-01-01,1",  # known early, not occurred at capture
    ]
    workspace.history.write_text("\n".join(rows) + "\n")
    workspace.set_clock("2026-01-24T12:00:00+00:00")


async def evidence_journey(workspace):
    write_evidence_history(workspace)
    workspace.history.write_text(
        workspace.history.read_text().replace("2026-02-20,999,2026-01-01,1\n", "")
    )
    spec = source_spec(workspace)
    spec["mapping"]["revision"] = "revision"
    async with workspace.client() as client:
        registered = await call(client, "register_csv_source", spec=spec)
        discovery = await poll_job(client, registered["job_id"])
        snapshot_id = discovery["result"]["source_snapshot_ids"][0]
        workspace.stop_worker()
        with workspace.history.open("a") as stream:
            stream.write("2026-02-20,999,2026-01-01,1\n")
    async with workspace.client() as client:
        # Stored snapshots need no raw-source grant, even on a new MCP connection.
        configured_request = dict(
            key="configured-evidence",
            source_id="sales",
            snapshot_id=snapshot_id,
            selection={
                "provider": "seasonal_naive",
                "options": {"period": 2},
                "horizon": 3,
                "baseline_period": 1,
            },
        )
        configured = await call(
            client, "submit_configured_forecast", **configured_request
        )
        await call(
            client,
            "submit_backtest",
            error="source_forbidden",
            key="denied-evidence",
            source_id="sales",
            selection=configured_request["selection"],
        )
    request = dict(
        key="frozen-evidence",
        source_id="sales",
        selection={
            "provider": "seasonal_naive",
            "options": {"period": 2},
            "horizon": 2,
            "baseline_period": 1,
        },
        settings={"max_origins_per_partition": 2, "origin_offset_seconds": 0},
    )
    async with workspace.client(source_ids=["sales"]) as client:
        accepted = await call(client, "submit_backtest", **request)
        identity = accepted["job_id"]
        await call(client, "get_backtest", error="not_found", backtest_id=identity)
        await call(
            client, "list_backtest_origins", error="not_found", backtest_id=identity
        )
    # Real persistence runs while no MCP process is connected. Pause only after
    # real origin persistence, then kill the OS worker and reclaim its lease.
    (workspace.root / "pause-after-origin").touch()
    workspace.start_worker()
    await wait_file(workspace.root / "origin-persisted")
    workspace.stop_worker()
    plan = stored(workspace, "backtest_plans", identity)[0]
    partial = stored(workspace, "backtest_origins", identity)
    assert [o["ordinal"] for o in partial] == [0, 1]
    assert len(plan["calendar"]) == 24  # future row never extends membership
    assert len(plan["archive"]["observations"]) == 26
    assert len(plan["origins"]) == 6
    assert partial[0]["reason_code"] == "insufficient_history"
    assert partial[1]["matched_count"] == 2
    frozen_bytes = json.dumps(plan, sort_keys=True)
    workspace.history.write_text("changed source cannot be parsed\n")
    (workspace.root / "pause-after-origin").unlink()
    workspace.set_clock("2026-01-24T12:02:00+00:00")
    # Restart API too: no interpreter may retain the archive or report in memory.
    workspace.stop(workspace.api)
    workspace.api = workspace.launch("api")
    await workspace.wait_api()
    workspace.start_worker()
    async with workspace.client(source_ids=["sales"]) as client:
        completed = await poll_job(client, identity)
        report = await call(client, "get_backtest", backtest_id=identity)
        assert completed["result"]["backtest_id"] == identity
        assert report["plan_id"] == plan["plan_id"]
        assert report["archive_id"] == plan["archive"]["archive_id"]
        assert report["source_revision"] == plan["archive"]["source_revision"]
        assert report["captured_at"] == "2026-01-24T12:00:00Z"
        assert report["status"] == "completed"
        assert report["selection"] == request["selection"]
        assert report["settings"] == request["settings"]
        exploration, selection, final = report["partitions"]
        assert (
            exploration["planned"],
            exploration["excluded"],
            exploration["evaluated"],
            exploration["matched_count"],
        ) == (2, 1, 1, 2)
        for score in (selection, final):
            assert (score["planned"], score["evaluated"], score["matched_count"]) == (
                2,
                2,
                4,
            )
        for score in (exploration, selection, final):
            assert (
                score["model_mae"],
                score["baseline_mae"],
                score["relative_mae"],
            ) == (0, 1, 0)
        origins = []
        offset = 0
        while True:
            page = await call(
                client,
                "list_backtest_origins",
                backtest_id=identity,
                offset=offset,
                limit=2,
            )
            assert page["offset"] == offset and page["limit"] == 2
            origins += page["origins"]
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        assert len(origins) == 6 and origins[:2] == partial
        assert origins == stored(workspace, "backtest_origins", identity)
        for origin in origins[1:]:
            run = await call(client, "get_run", run_id=origin["run_id"])
            evaluation = await call(
                client, "get_evaluation", evaluation_id=origin["evaluation_id"]
            )
            assert evaluation["run_id"] == run["run_id"]
            assert evaluation["discovery"] is None
            assert evaluation["actuals_snapshot_id"] == report["actuals_snapshot_id"]
            assert evaluation["metrics"]["model"]["count"] == 2
            assert evaluation["metrics"]["model"]["mae"] == 0
            assert evaluation["metrics"]["baseline"]["mae"] == 1
            assert await call(client, "list_run_evaluations", run_id=run["run_id"]) == [
                evaluation
            ]
            history = await call(
                client, "get_snapshot", snapshot_id=run["snapshot_ids"][0]
            )
            first = history["observations"][0]
            assert (first["value"], first["revision"]) == (
                (1, "1") if origin["ordinal"] == 1 else (9, "2")
            )
            assert all(
                o["event_time"] <= origin["nominal_origin"]
                and o["available_at"] <= origin["issuance_time"]
                for o in history["observations"]
            )
        configured_job = await poll_job(client, configured["job_id"])
        run = await call(client, "get_run", run_id=configured_job["result"]["run_id"])
        assert run["results"]["model"]["point"] == [[1, 3, 1]]
        assert run["results"]["baseline"]["point"] == [[3, 3, 3]]
        assert run["results"]["model"]["timestamps"] == [
            "2026-01-25T00:00:00Z",
            "2026-01-26T00:00:00Z",
            "2026-01-27T00:00:00Z",
        ]
        graph = await call(
            client, "get_graph", graph_id=run["graph_id"], version=run["graph_version"]
        )
        assert next(n for n in graph["nodes"] if n["node_id"] == "model")["config"][
            "options"
        ] == {"period": 2}
        assert (await call(client, "submit_backtest", **request))["job_id"] == identity
        assert (await call(client, "submit_configured_forecast", **configured_request))[
            "result"
        ]["run_id"] == run["run_id"]
    assert (
        json.dumps(stored(workspace, "backtest_plans", identity)[0], sort_keys=True)
        == frozen_bytes
    )
    assert stored(workspace, "backtest_reports", identity) == [report]
    with sqlite3.connect(workspace.root / "state.db") as db:
        assert (
            db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 7
        )  # 6 origins (one failed) + configured
        assert db.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] == 5
    # A second disconnect/reconnect reads identical report and child identities.
    async with workspace.client() as client:
        assert await call(client, "get_backtest", backtest_id=identity) == report
        assert (await call(client, "list_backtest_origins", backtest_id=identity))[
            "origins"
        ] == origins
        await call(client, "submit_backtest", error="source_forbidden", **request)
    return report
