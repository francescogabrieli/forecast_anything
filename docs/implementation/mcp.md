# Local MCP adapter

The optional stdio adapter exposes the existing authenticated API to an MCP client. It registers mapped CSV sources, submits existing executable candidates or explicit configured forecasts, submits bounded historical backtests, reads immutable results and submits single-run evaluations. The API owns graphs, snapshots, jobs, computation and evidence; MCP creates no second ledger.

The reference client is the official Python `mcp==2.3.0` SDK, locked in `uv.lock`. Real subprocess tests exercise stdio, loopback HTTP and an independent worker, including an installed wheel outside the checkout. No desktop assistant host has been validated. These tests use synthetic observations and the real seasonal baseline; they make no language-model or forecast-quality claim.

## Install and operate

### Private workspace configuration

The following uses one configuration file for the API, worker and MCP adapter. It creates a new token and refuses to overwrite an existing configuration:

```sh
uv sync --locked --extra dev --extra mcp
mkdir -p .local/mcp/sources
uv run --locked --extra mcp forecast-anything init --workspace .local/mcp --csv-root .local/mcp/sources
uv run --locked --extra mcp forecast-anything up --config .local/mcp/config.json
```

Keep `config.json` private: it contains the workspace token and is created with owner-only file permissions. Back up the configuration and database together; losing or changing the token requires updating every client using it. `--port` may be supplied to `init` (default 8000). The CSV root must already exist. The file records absolute paths, so update them deliberately if moving the workspace. To grant access to previously registered sources after an MCP restart, edit the `source_ids` JSON array in this private file; CSV roots are likewise explicit. Restart MCP to apply changes.

Configure the host to launch the installed executable with arguments `mcp --config /absolute/path/to/config.json`. For example:

```json
{
  "command": "/absolute/path/forecast_anything/.venv/bin/forecast-anything",
  "args": ["mcp", "--config", "/absolute/path/forecast_anything/.local/mcp/config.json"]
}
```

In another terminal, `forecast-anything status --config .local/mcp/config.json` checks authenticated API access. `worker: unknown` is intentional: the check cannot establish that the worker is running or that the responding API uses the intended database. `up` stops both services on Ctrl+C; accepted jobs remain in the database for the next start. The command remains in the foreground and does not install an OS service. No desktop host has been validated.

### Environment-based setup

From the checkout with Python 3.12+ and uv:

```sh
uv sync --locked --extra dev --extra mcp
mkdir -p .local/mcp/sources
export FORECAST_ANYTHING_WORKSPACE_TOKEN="$(uv run --locked --extra mcp python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export FORECAST_ANYTHING_MCP_API_URL=http://127.0.0.1:8000
export FORECAST_ANYTHING_MCP_CSV_ROOTS="$(uv run --locked --extra mcp python -c 'import json,pathlib; print(json.dumps([str(pathlib.Path(".local/mcp/sources").resolve())]))')"
export FORECAST_ANYTHING_MCP_SOURCE_IDS='["sales"]'
```

Keep the token private. Supply the same token to the API and the MCP host using its private environment configuration. Separate terminals do not automatically share exported variables.

1. Start API and worker together: `uv run --locked --extra mcp forecast-anything up --db .local/mcp/state.db`. The command stays in the foreground, binds the API to `127.0.0.1:8000` (change the port with `--port`), and stops both processes on Ctrl+C or SIGTERM. If either process exits unexpectedly, it stops the other and returns an error; restart the command to resume durable jobs.
2. The MCP host launches the absolute `.venv/bin/forecast-anything` executable with argument `mcp` and the environment below. A terminal alone is not an MCP client; stdout carries protocol messages only.

For separate process management, `forecast-anything serve --db .local/mcp/state.db` and `forecast-anything worker --db .local/mcp/state.db` remain available. The foreground command is not a background service manager and does not provide persistent setup or a status command.

The API and worker must use the same local SQLite file. MCP and API must see the same absolute CSV paths in the same filesystem namespace. Container paths and host paths are not interchangeable. The adapter does not start or stop either service. Accepted work survives a disconnected MCP process and finishes when the independently operated worker runs. The baseline path requires no LLM keys, model weights, Eve or Postgres.

A generic stdio launch object follows. Replace the absolute paths and token through your host's configuration mechanism; this JSON does not imply environment-variable expansion or a tested desktop-specific configuration schema.

```json
{
  "command": "/absolute/path/forecast_anything/.venv/bin/forecast-anything",
  "args": ["mcp"],
  "env": {
    "FORECAST_ANYTHING_MCP_API_URL": "http://127.0.0.1:8000",
    "FORECAST_ANYTHING_WORKSPACE_TOKEN": "OPERATOR_SUPPLIED_PRIVATE_TOKEN",
    "FORECAST_ANYTHING_MCP_CSV_ROOTS": "[\"/absolute/path/forecast_anything/.local/mcp/sources\"]",
    "FORECAST_ANYTHING_MCP_SOURCE_IDS": "[\"sales\"]"
  }
}
```

For an artifact installation, build with `uv build` and install the local wheel's `[mcp]` extra in a virtual environment. The artifact test exports exact dependency versions from `uv.lock`, installs that set and the wheel extra into a fresh environment, and verifies package, server and SDK imports resolve there. Nothing has been published to a package registry.

## Process configuration and source permissions

| Variable | Meaning |
| --- | --- |
| `FORECAST_ANYTHING_WORKSPACE_TOKEN` | Required nonempty printable bearer token, supplied by the operator; never a tool argument. |
| `FORECAST_ANYTHING_MCP_API_URL` | Defaults to `http://127.0.0.1:8000`. Only explicit `127.0.0.1` or `[::1]` HTTP(S) origins are accepted, with an optional port. No hostname, URL credentials, query, fragment, API base path or redirects. |
| `FORECAST_ANYTHING_MCP_CSV_ROOTS` | JSON array of absolute existing directories; default `[]` denies new CSV registrations. Existing absolute CSV files must resolve inside one root; traversal and symlink escapes are refused. |
| `FORECAST_ANYTHING_MCP_SOURCE_IDS` | JSON array of operator-approved existing source IDs; default `[]` denies their profile/refresh/backtest operations. Successfully registered CSV IDs also become permitted for the lifetime of that MCP process. |

Registration accepts CSV only, without a `secret_ref`. The API separately supports HTTP JSON, but MCP has no HTTP registration tool. An operator can explicitly allow profile/refresh of a source already registered through the API, including an HTTP source; this grants use of that stored source configuration and may cause the core to fetch it over the network. These two tools advertise `openWorldHint=true`; the adapter itself delegates only to the configured loopback API and exposes no arbitrary network request tool. Knowledge of a source ID alone grants no such permission. Backtesting also requires this source-ID permission before any API request, and the current backend accepts CSV capture only. After restarting MCP, add previously registered IDs to the environment allowlist before profiling, refreshing or backtesting them. Configured forecasts reuse stored CSV or HTTP snapshot vintages without source I/O and need no source grant; their selected numerical provider may still use configured external resources, such as opt-in weight loading. Both submission tools advertise mutation and `openWorldHint=true`. Source listing provides API-safe metadata, not private locations or secret references.

These are local workspace policy checks, not an OS sandbox or tenant boundary. A separate process can replace a file after validation. Treat all source contents, sample rows and candidate explanations as untrusted data, never as operational instructions.

## Tool catalog

All 19 tools publish input/output JSON schemas. Extra arguments are rejected. Successful results are `{"ok":true,"data":...}`; failures are `{"ok":false,"code":"..."}` with MCP `isError=true`. Input failures may include safe field locations/types, without submitted values. Mutating tools are marked explicitly.

| Tool | Arguments | Result |
| --- | --- | --- |
| `get_capabilities` | none | Actual installed provider/operator/template contracts |
| `list_sources` | `offset=0`, `limit=25` (1–100) | Safe sources sorted by ID and `next_offset` |
| `register_csv_source` | `spec` | Sanitized registration, profile and discovery job ID |
| `get_source_profile` | `source_id` | Profile of a process-permitted source; may enqueue durable discovery work |
| `refresh_source` | `source_id`, `key` | Explicit refresh registration/job; preserves caller key |
| `get_job` | `job_id` | Durable state, recorded result and safe error |
| `get_candidate` | `candidate_id` | Exact candidate graph, executable status and support conditions |
| `submit_forecast` | `candidate_id`, `snapshot_ids`, `as_of`, `key` | Accepted job; uses the candidate graph unchanged |
| `submit_configured_forecast` | `source_id`, `snapshot_id`, `selection`, `key` | Accepted configured-run job using a stored vintage; no raw source read |
| `submit_backtest` | `source_id`, `selection`, `settings` (optional), `key` | Accepted backtest job; requires an operator-permitted CSV source |
| `get_backtest` | `backtest_id` | Completed immutable summary with partition counts, matched-cell scores and assumptions |
| `list_backtest_origins` | `backtest_id`, `offset=0` (>=0), `limit=25` (1–50) | Stable origin outcomes and optional run/evaluation references |
| `get_run` | `run_id` | Immutable emission, actual provider and evidence IDs |
| `get_graph` | `graph_id`, `version` (>0) | Exact stored graph version |
| `get_snapshot` | `snapshot_id` | Immutable availability-aware snapshot |
| `list_run_evaluations` | `run_id` | Persisted evaluations; `[]` means unevaluated |
| `get_evaluation` | `evaluation_id` | Recorded metrics and assumptions |
| `submit_evaluation` | `run_id`, `actuals_snapshot_id`, `key` | Evaluation job; core computes metrics |
| `get_events` | `after=0` (>=0), `limit=100` (1–1000) | Durable events and continuation cursor |

Profiling is a mutating operation (`readOnlyHint=false`): the existing core GET route inspects the source and enqueues template discovery. A changed profile can create a new durable job; its worker can persist epochs, snapshots, candidates and graphs, and enqueue optional agent discovery when configured. The profile response contains the profile only, without that job ID. Profiling has no caller key, so it advertises `idempotentHint=false`; do not assume that repeating it is side-effect-free.

`as_of` must be timezone-aware. Snapshot bindings must exactly match the candidate's declared sources. Unresolved/non-executable candidates cannot be submitted. A forecast does not manufacture snapshots or select another provider. Refresh, forecast and evaluation require stable caller keys; registration and profiling have no caller-key replay guarantee.

`selection` is an object with `provider`, `horizon` (strict integer 1–366), `options` (finite JSON object, default `{}`), and `baseline_period` (strict integer 1–10000, default 1). `settings` contains `max_origins_per_partition` (strict integer 1–50, default 10) and `origin_offset_seconds` (non-negative strict integer, default zero); the backend requires the offset to be less than the declared source interval. For example:

```json
{
  "source_id": "sales",
  "selection": {"provider": "seasonal_naive", "horizon": 2, "options": {"period": 2}, "baseline_period": 1},
  "settings": {"max_origins_per_partition": 10, "origin_offset_seconds": 0},
  "key": "sales/backtest-v1"
}
```

Pass this object to `submit_backtest`; the adapter injects the fixed `backtest` job kind. `submit_configured_forecast` takes the same `source_id`, `selection` and caller `key`, plus `snapshot_id`, with no `settings`, and injects `configured_run`. Neither tool accepts arbitrary jobs or graphs. Caller keys and route identities are never silently trimmed; replay the exact original request with the same key. JSON option values `true`, `1` and `1.0` retain their types for the backend's intent comparison.

Poll `get_job` after submission. A configured job completes with `run_id`; a backtest completes with `backtest_id` and `report_id`. Only then read `get_backtest` and `list_backtest_origins`. Until a completed report is published, reads return `not_found`, rather than empty reports; inspect a pending or failed job's recorded state/error. Completed reads do not compute, enqueue or expose the private archive/plan. Failed and excluded origins retain reason codes and the planned denominator.

The initial backtest backend supports one registered CSV source, one numerical series/unit, and fixed UTC hourly/daily grids. It captures the supplied revision archive once and freezes origin membership before inference. It cannot reconstruct revisions removed upstream or invent historical publication dates. Partition summaries compare matched cells only, retain failed/excluded/insufficient counts and express unavailable relative MAE explicitly. An `insufficient_evidence` summary is not a qualification or model-quality certificate. Scenarios, multiple history sources and automatic tuning/watch promotion are outside this workflow.

## Complete SDK example

Start the API and worker above. Save this as a local script and run it with `uv run --locked --extra mcp python /path/to/script.py` from the repository root. It writes three synthetic daily observations, registers their explicit mapping, waits for discovery, binds the returned snapshot and submits the existing one-step baseline candidate. The target is tomorrow's UTC midnight, relative to the date the example creates its inputs. The example has no historical replay clock or invented publication dates: the synthetic fixture declares each row available at that day's midnight.

```python
import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

root = Path.cwd()
source = root / ".local/mcp/sources/sales.csv"
source.parent.mkdir(parents=True, exist_ok=True)
today = datetime.now(timezone.utc).date()
source.write_text("time,value,published\n" + "".join(
    f"{today - timedelta(days=2-i)},{i+1},{today - timedelta(days=2-i)}\n"
    for i in range(3)
))
parameters = StdioServerParameters(
    command=str(root / ".venv/bin/forecast-anything"),
    args=["mcp"],
    env={key: os.environ[key] for key in (
        "FORECAST_ANYTHING_WORKSPACE_TOKEN", "FORECAST_ANYTHING_MCP_API_URL",
        "FORECAST_ANYTHING_MCP_CSV_ROOTS", "FORECAST_ANYTHING_MCP_SOURCE_IDS",
    )},
)

async def call(client, tool, **arguments):
    result = await client.call_tool(tool, arguments)
    body = result.structured_content
    if result.is_error or not body["ok"]:
        raise RuntimeError(body["code"])
    return body["data"]

async def wait(client, job_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = await call(client, "get_job", job_id=job_id)
        if job["state"] == "completed":
            return job["result"]
        if job["state"] == "failed":
            raise RuntimeError("job_failed")
        await asyncio.sleep(0.1)
    raise TimeoutError("job remains pending; keep its ID and check the worker")

async def main():
    async with Client(parameters, mode="legacy", read_timeout_seconds=20) as client:
        print([tool.name for tool in (await client.list_tools()).tools])
        registration = await call(client, "register_csv_source", spec={
            "source_id": "sales", "kind": "csv", "location": str(source),
            "refresh_seconds": 86400,
            "mapping": {
                "event_time": "time", "value": "value", "available_at": "published",
                "revision": {"constant": "1"}, "series_id": {"constant": "sales"},
                "unit": {"constant": "count"}, "frequency": {"constant": "1d"},
                "timezone": {"constant": "UTC"}, "calendar": {"constant": "gregorian"},
                "missing_values": {"constant": [""]},
            },
        })
        discovery = await wait(client, registration["job_id"])
        candidate = await call(client, "get_candidate", candidate_id=discovery["candidate_ids"][0])
        snapshot = await call(client, "get_snapshot", snapshot_id=discovery["source_snapshot_ids"][0])
        request = {
            "candidate_id": candidate["candidate_id"],
            "snapshot_ids": {"sales": snapshot["snapshot_id"]},
            "as_of": snapshot["as_of"],
            "key": "sales/example/forecast-v1",
        }
        # Persist BEFORE submission: replay this exact body/key after a lost response.
        Path(".local/mcp/original-request.json").write_text(json.dumps(request))
        accepted = await call(client, "submit_forecast", **request)
        print("job_id:", accepted["job_id"])
    # Reconnection launches a new MCP process; API and worker keep running.
    async with Client(parameters, mode="legacy", read_timeout_seconds=20) as client:
        replay = await call(client, "submit_forecast", **request)
        assert replay["job_id"] == accepted["job_id"]
        completed = await wait(client, replay["job_id"])
        run = await call(client, "get_run", run_id=completed["run_id"])
        graph = await call(client, "get_graph", graph_id=run["graph_id"], version=run["graph_version"])
        print(json.dumps({"run": run, "graph": graph}, indent=2))

asyncio.run(main())
```

To recover an ambiguous HTTP/MCP submission, reuse the persisted original body and key. Do not rerun registration or replace the key as a recovery strategy. A changed plan with the same key conflicts; a new intentional computation needs a new key. The adapter makes one HTTP attempt per mutation and never transparently retries it. On a later independent run of the example, choose a new key for the new snapshot/origin.

For evaluation, append genuine observed outcomes to the same registered source, preserving its catalog identity and explicit `available_at` semantics. Once the outcomes are available, call `refresh_source(source_id="sales", key="actuals-vintage-1")`, poll its job, and read its `source_snapshot_ids[0]`. Call `submit_evaluation(run_id=..., actuals_snapshot_id=..., key="evaluate-issued-vintage-1")`, poll that job and pass its `evaluation_id` to `get_evaluation`. The original run remains immutable. An unrelated source with the same series name does not supply authorized actuals. Assumed/scenario outcomes and multiple forecast-history source bindings are refused. Callers cannot supply metrics or eligibility attestations. This is single-run evaluation, not multi-origin backtesting or automatic watch promotion.

## Measured synthetic journey and limits

`tests/integration/test_mcp_stdio.py` fixes a test-only clock at **2026-10-23 12:00 UTC**, with values `1, 2, 3` on October 21–23. The existing candidate explicitly uses seasonal period 2 and horizon 1: the recorded `forecast` point is **2 count for October 24 00:00 UTC**, with a separate period-1 reference of 3. It closes MCP after acceptance while the worker is stopped, starts the independent worker, then reconnects and obtains the same job/run by replaying the original key. The run's evidence list is correctly empty at issuance.

The fixture appends an observed October 24 value **4**, available October 24 at **12:00 UTC**, advances only the test clock to October 25, refreshes the original source and persists evaluation: **MAE 2, count 1, origin_count 1** for `forecast`. No issued record is modified and no calibrated probability, predictive superiority or qualified watch is claimed. These dates are a labeled historical synthetic fixture; the production CLI uses the real clock. The installed-wheel test repeats the real baseline/disconnect/replay journey through the installed executable outside the checkout.

The combined serialized MCP `CallToolResult`, including both text and structured copies, is bounded at **64 KiB**. Larger results return only `result_too_large`, without a partial successful payload. The HTTP adapter separately bounds serialized requests and streamed upstream responses at **1 MiB**, with a 15-second request deadline. Compressed responses are refused. Errors expose safe codes rather than upstream bodies, tokens or private locations.

Source listing first loads the complete bounded upstream list before sorting/slicing. Event pagination similarly operates within the upstream response bound. A very large workspace or snapshot may be refused; pagination cannot bypass either bound. Read a smaller collection/page where supported or use the core's separate interfaces for larger artifacts. MCP does not expose a generic HTTP request, SQL operation, filesystem reader, shell command, arbitrary graph editor, HTTP source registration, lifecycle scheduler or private backtest archive/plan reader.

Run the acceptance journeys with:

```sh
uv run --locked --extra dev --extra mcp pytest tests/integration/test_mcp_stdio.py tests/integration/test_packaged_mcp.py -q
```

SDK-dependent test modules skip explicitly without the optional extra; the ordinary CLI's missing-extra error remains covered separately. The four evidence tools have protocol/schema/HTTP-boundary coverage and a real subprocess/installed-wheel configured/backtest recovery journey. A 24-day alternating series explicitly selects period 2 against comparator period 1: model MAE 0, comparator MAE 1, relative MAE 0. Two planned origins per partition remain fixed, including an early insufficient-history exclusion. The worker is terminated after partial persisted origins; API/worker restart after CSV corruption preserves the original capture, plan, child identities and paginated report. A separate process case retains unavailable-history and missing-target exclusions. A configured horizon-3 forecast separately proves options and future target dates. [Full numerical fixture, verification and limits](../research/forecast-evidence.md). Generic backtest reports contain no discovery attestation and do not activate or qualify watches. Desktop-host validation, a guided setup/site and autonomous lifecycle controls remain pending work in the [roadmap](../roadmap.md).
