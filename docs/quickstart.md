# Quickstart

Forecast Anything requires pinned local Mistral Timestral-28M for product forecasts. Install its dependencies and prepare the weights before submitting forecasts. No Mistral API key or hosted inference account is needed; seasonal-naive is only the comparison baseline.

The local stdio MCP adapter is implemented. The [MCP guide](implementation/mcp.md) documents installation with `uv sync --locked --extra dev --extra mcp`, foreground API/worker startup, CSV roots and source-ID permissions, all 26 tools and complete official-SDK requests for forecasts and recurring questions. The `mcp==2.3.0` SDK is the tested reference client. Configured forecasts and watch tools also completed through Codex CLI's MCP client against the local API and worker; Desktop MCP reads/reconnect and the supported CSV-to-watch/report workflow have recorded acceptance evidence. Site publication and guided setup remain separate release tasks. The CLI and optional console paths below remain available.

After an MCP restart, put previously registered IDs in `FORECAST_ANYTHING_MCP_SOURCE_IDS` before profiling, refreshing, backtesting or creating watches for them. Preserve the original forecast body/key after an ambiguous response; the independent worker can finish while the assistant is disconnected. MCP output is bounded at 64 KiB and upstream requests/responses at 1 MiB; listing pagination cannot bypass those bounds. New MCP registration accepts local CSV under configured roots, with no secret reference; HTTP registration remains pending. Configured forecasts, frozen CSV backtests and recurring-question watches are available through the tools below.

## Configure a forecast or replay historical evidence through MCP

First register/map a CSV and wait for its discovery job using the [MCP guide](implementation/mcp.md). Keep its `source_id` and stored `snapshot_id`. In the same connected SDK client, submit a configured forecast with explicit model options, horizon and independent comparator period:

```python
result = await client.call_tool(
    "submit_configured_forecast",
    {
        "key": "sales-configured-v1",
        "source_id": "sales",
        "snapshot_id": snapshot_id,
        "selection": {
            "provider": "timestral",
            "options": {},
            "horizon": 3,
            "baseline_period": 1,
        },
    },
)
```

Check `result.is_error` and the `structured_content` success envelope. Poll `get_job(job_id=...)` until completed or failed, then read `get_run(run_id=...)` from the completed job result. This uses the stored snapshot vintage without source I/O. The graph records separate `model` and `baseline` results; the console prefers `forecast` for legacy runs, then `model`.

To compare historical origins, grant `sales` in `FORECAST_ANYTHING_MCP_SOURCE_IDS` when starting a new MCP process, then submit:

```python
result = await client.call_tool(
    "submit_backtest",
    {
        "key": "sales-backtest-v1",
        "source_id": "sales",
        "selection": {
            "provider": "timestral",
            "options": {},
            "horizon": 2,
            "baseline_period": 1,
        },
        "settings": {"max_origins_per_partition": 2, "origin_offset_seconds": 0},
    },
)
```

Poll `get_job` first. On completion, use its `backtest_id` with `summarize_backtest` for the three partition scores, final-origin MAE points and assumptions. For a watch-bound backtest, pass the returned `watch_id` to include current state and whether its decision names this report. `relative_mae` is model MAE divided by baseline MAE; below 1 means lower error on these matched cells only. It does not establish future accuracy. Use `get_backtest` for the immutable full report, `list_backtest_origins` for paged origin records, `get_run` for issued point forecasts and `list_run_evaluations` for recorded accuracy metrics. Pending reports/pages return `not_found`; failed jobs do not become empty successful reports. Retry an ambiguous submission with its original body and key. Accepted work can finish without a connected assistant while the worker is running.

Assuming `completed_job` is the `data` member returned by a completed `get_job` call:

```python
summary = await client.call_tool(
    "summarize_backtest",
    {
        "backtest_id": completed_job["result"]["backtest_id"],
        "watch_id": completed_job["result"].get("watch_id"),
    },
)
```

Backtests capture one registered CSV series/unit on a regular UTC hourly/daily grid. They freeze supplied revisions, source vintage, provider contracts, calendar and earliest bounded origins in 50/25/25 partitions before inference. History requires both occurred events and revisions available by issuance; missing cells remain missing. A later edit to the CSV cannot change an already captured report. Upstream-discarded revisions cannot be reconstructed. Horizon is 1–366, comparator period 1–10000, and origins per partition 1–50 (default 10); raw capture and complete calendar are bounded at 100000 rows/instants. Configured forecasts can also reuse supported stored HTTP snapshots; raw HTTP backtesting, scenarios and multi-history scoring are unsupported.

The [reproducible synthetic acceptance](research/forecast-evidence.md) compares a period-2 alternating series with a period-1 comparator. It verifies calculation and persistence, not general predictive quality. Generic backtests do not attach discovery attestations or activate watches. Managed installation, direct desktop-host acceptance, assistant acceptance of the summaries and public onboarding remain release work.

## Run a forecast from the checkout

Install Python 3.12+ and [uv](https://docs.astral.sh/uv/), then run the included minimal example:

```sh
uv sync --locked --extra dev --extra mcp
mkdir -p .local
uv run --locked --extra mcp forecast-anything run \
  examples/minimal/graph.json \
  --data examples/minimal/observations.csv \
  --as-of 2026-10-24T00:00:00Z \
  --db .local/example.db
```

The CLI returns an immutable run record using pinned `timestral`, with point forecasts and marginal quantiles. The input is synthetic; it does not establish calibrated joint-event probabilities or general predictive accuracy. Repeat the command to retrieve the same run ID. Use `forecast-anything show RUN_ID --db .local/example.db` to read it again.

Three additional synthetic domain examples use the same core and declare their assumptions in their output:

```sh
uv run --locked --extra mcp python scripts/run_example.py retail --db .local/retail.db
uv run --locked --extra mcp python scripts/run_example.py energy --db .local/energy.db
uv run --locked --extra mcp python scripts/run_example.py activity --db .local/activity.db
```

These examples do not claim to model real retail seasonality, energy operations or Wikimedia activity. Their calendars and repetition periods are illustrative.

## Start the local console

Create a private local workspace file, then start the API, its single worker and the console:

```sh
uv run --locked python scripts/bootstrap_demo.py .local/demo
docker compose --env-file .local/demo/demo.env build core worker
docker compose --env-file .local/demo/demo.env run --rm core model prepare
docker compose --env-file .local/demo/demo.env --profile demo up --build
```

Open [http://localhost:5173](http://localhost:5173). Copy `FORECAST_ANYTHING_WORKSPACE_TOKEN` from `.local/demo/demo.env` into the workspace form. The token stays in browser memory. The API listens only on local port 8000, and browser access is limited to the configured console origins.

Open **Workspace** to enter the API address and token, then **Fonti** to connect or review a source. **Home** lists recent forecasts and lets you prepare a new forecast from a registered source. **Osservatorio** opens recorded results, their Future Graph, evaluations, watches and scenarios.

To connect a CSV, place it in the workspace directory printed by the bootstrap command and enter its container path as `/data/your-file.csv`. Use the guided column/constant fields to identify observation time, value, availability time, revision, series, unit, frequency, timezone, calendar and missing-value markers. Availability must be declared explicitly, even when it uses the observation-time column. Review the proposed profile and resolve every required field before activating the source. **Mappatura avanzata** retains JSON configuration for extensions; browser file upload is deferred behind the primary assistant/MCP journey.

The first source mapping leaves frequency and timezone blank so the profile cannot treat `1d` or `UTC` as facts about your data. Choose the actual cadence and the IANA timezone used by timestamps without an offset; the profile reports candidate columns for review but does not select them for you. Local times that are ambiguous or do not exist because of daylight-saving changes are rejected.

To allow the assistant to read a registered source after the MCP server restarts, manage its persistent grant from the workspace config:

```sh
forecast-anything permissions list --config .local/demo/config.json
forecast-anything permissions grant sales --config .local/demo/config.json
forecast-anything permissions revoke sales --config .local/demo/config.json
```

Grant only source IDs you trust. A grant for an HTTP JSON source permits the local worker to fetch its registered URL during refresh or watch updates. Restart the assistant's MCP server after granting or revoking; the source catalog itself remains available in the workspace.

Once discovery has prepared a compatible single-series source, **Calcola la prima previsione** submits its existing one-step Timestral candidate to the worker. The issued value, unit and UTC target appear in the console with a link to its recorded run. This initial result is provisional and not yet evaluated. **Aggiorna dati** explicitly rereads the registered source into a new snapshot. A target that is no longer in the future according to the snapshot and device clock is not offered as a new forecast; update the data and check the device clock if necessary.

The console shows recorded discoveries, their current quality, event history, graph dependencies and run evidence when available. Forecast charts use only the history source resolved through the recorded graph and snapshot binding; unavailable or ambiguous history stays unavailable. Recorded evaluation metrics are displayed as issued; the multi-origin backtesting workflow remains a core/product milestone, prioritized for access through tools before browser controls. Its deterministic E2E flow runs the production frontend against two local fixtures, mutes a watch, resumes an interrupted event stream from the durable history, navigates the graph by keyboard and compares an assumed scenario with a worker-produced run. It is a functional test fixture, not a forecast-quality benchmark or a completed external usability study.

Stop the stack with `Ctrl+C`. The workspace database and generated token remain under `.local/demo`; removing that directory deletes the local demo state.

## Optional integrations

- Timestral has separately pinned code and weight revisions. Real CPU fp32 parity passed for the pinned provider, and one local personal evaluation was authorized by the project owner. The weights use a separate Modified MIT license; each downstream user must assess whether its terms apply to their use. Weights are not included in this repository. The default demo does not install Timestral or download weights; see the [provider notes](implementation/timestral.md) before opting in.
- `compose.agent.yaml` requires a separate workspace agent setup, distinct bridge/core tokens, a URL-safe Postgres password and an OpenAI API key. It makes paid provider calls when configured. The agent runs behind the repository's restricted egress proxy and does not receive the Docker socket. Do not start this override without intended credentials and approval for any paid inference.

## Verify changes

From the repository root:

```sh
uv run --locked --extra dev --extra mcp ruff check src tests apps/agent/egress-proxy/proxy.py
uv run --locked --extra dev --extra mcp ruff format --check src tests apps/agent/egress-proxy/proxy.py
uv run --locked --extra dev --extra mcp pytest -q
npm --prefix apps/console test -- --run
npm --prefix apps/console run typecheck
npm --prefix apps/console run build
```

For the deterministic browser test, install Chromium once with `npx --prefix apps/console playwright install chromium`, then run `npm --prefix apps/console run test:e2e`. It starts a local API and worker using fixed synthetic input and a fixed test-only token.

For the accepted Desktop workflow, source correction, qualification, automatic update, permission revocation and report boundaries, see the [acceptance record](research/desktop-assistant-acceptance.md).

## Required-model readiness and migration

Run `forecast-anything model status` to inspect dependency/provenance and local cache state without importing Torch or downloading weights. `cached` means artifacts exist; only `model prepare` or actual inference verifies loading in that process. Run `forecast-anything model prepare` explicitly to prepare the pinned CPU model. API/worker liveness does not establish model readiness; `get_capabilities` separately reports the required provider and inspected model status.

A baseline-only primary request, a baseline mixed into the primary calculation, or a disconnected Timestral node cannot bypass the model requirement. Legacy baseline reports remain readable. Legacy recurring watches pause with `migration_reason=required_provider_migration`; refresh/re-profile the source and create a new Timestral watch with fresh qualification evidence. Do not rewrite old graphs or reuse qualified final windows. Restart the API, worker and assistant's MCP server after upgrading so all processes load the new contracts.
