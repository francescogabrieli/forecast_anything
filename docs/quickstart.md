# Quickstart

Forecast Anything runs locally with a seasonal baseline. The default path needs no LLM key, model weights or hosted account.

The [MCP-first product direction](superpowers/specs/2026-10-29-mcp-first-product-design.md) is planned. There is no MCP installation command or supported client configuration yet. The CLI and optional console paths below describe the current implementation.

## Run a forecast from the checkout

Install Python 3.12+ and [uv](https://docs.astral.sh/uv/), then run the included minimal example:

```sh
uv sync --locked --extra dev
mkdir -p .local
uv run --locked forecast-anything run \
  examples/minimal/graph.json \
  --data examples/minimal/observations.csv \
  --as-of 2026-10-24T00:00:00Z \
  --db .local/example.db
```

The CLI returns an immutable run record using `seasonal_naive`. The input is synthetic and point-only; it provides no uncertainty interval or event probability. Repeat the command to retrieve the same run ID. Use `forecast-anything show RUN_ID --db .local/example.db` to read it again.

Three additional synthetic domain examples use the same core and declare their assumptions in their output:

```sh
uv run --locked python scripts/run_example.py retail --db .local/retail.db
uv run --locked python scripts/run_example.py energy --db .local/energy.db
uv run --locked python scripts/run_example.py activity --db .local/activity.db
```

These examples do not claim to model real retail seasonality, energy operations or Wikimedia activity. Their calendars and repetition periods are illustrative.

## Start the local console

Create a private local workspace file, then start the API, its single worker and the console:

```sh
uv run --locked python scripts/bootstrap_demo.py .local/demo
docker compose --env-file .local/demo/demo.env --profile demo up --build
```

Open [http://localhost:5173](http://localhost:5173). Copy `FORECAST_ANYTHING_WORKSPACE_TOKEN` from `.local/demo/demo.env` into the workspace form. The token stays in browser memory. The API listens only on local port 8000, and browser access is limited to the configured console origins.

Open **Workspace** to enter the API address and token, then **Fonti** to connect or review a source. **Home** lists recent forecasts and lets you prepare a new forecast from a registered source. **Osservatorio** opens recorded results, their Future Graph, evaluations, watches and scenarios.

To connect a CSV, place it in the workspace directory printed by the bootstrap command and enter its container path as `/data/your-file.csv`. Use the guided column/constant fields to identify observation time, value, availability time, revision, series, unit, frequency, timezone, calendar and missing-value markers. Availability must be declared explicitly, even when it uses the observation-time column. Review the proposed profile and resolve every required field before activating the source. **Mappatura avanzata** retains JSON configuration for extensions; browser file upload is deferred behind the primary assistant/MCP journey.

Once discovery has prepared a compatible single-series source, **Calcola la prima previsione** submits its existing one-step seasonal-baseline candidate to the worker. The issued value, unit and UTC target appear in the console with a link to its recorded run. This initial result is provisional and not yet evaluated. **Aggiorna dati** explicitly rereads the registered source into a new snapshot. A target that is no longer in the future according to the snapshot and device clock is not offered as a new forecast; update the data and check the device clock if necessary.

The console shows recorded discoveries, their current quality, event history, graph dependencies and run evidence when available. Forecast charts use only the history source resolved through the recorded graph and snapshot binding; unavailable or ambiguous history stays unavailable. Recorded evaluation metrics are displayed as issued; the multi-origin backtesting workflow remains a core/product milestone, prioritized for access through tools before browser controls. Its deterministic E2E flow runs the production frontend against two local fixtures, mutes a watch, resumes an interrupted event stream from the durable history, navigates the graph by keyboard and compares an assumed scenario with a worker-produced run. It is a functional test fixture, not a forecast-quality benchmark or a completed external usability study.

Stop the stack with `Ctrl+C`. The workspace database and generated token remain under `.local/demo`; removing that directory deletes the local demo state.

## Optional integrations

- Timestral has separately pinned code and weight revisions. Real CPU fp32 parity passed for the pinned provider, and one local personal evaluation was authorized by the project owner. The weights use a separate Modified MIT license; each downstream user must assess whether its terms apply to their use. Weights are not included in this repository. The default demo does not install Timestral or download weights; see the [provider notes](implementation/timestral.md) before opting in.
- `compose.agent.yaml` requires a separate workspace agent setup, distinct bridge/core tokens, a URL-safe Postgres password and an OpenAI API key. It makes paid provider calls when configured. The agent runs behind the repository's restricted egress proxy and does not receive the Docker socket. Do not start this override without intended credentials and approval for any paid inference.

## Verify changes

From the repository root:

```sh
uv run --locked ruff check src tests apps/agent/egress-proxy/proxy.py
uv run --locked ruff format --check src tests apps/agent/egress-proxy/proxy.py
uv run --locked pytest -q
npm --prefix apps/console test -- --run
npm --prefix apps/console run typecheck
npm --prefix apps/console run build
```

For the deterministic browser test, install Chromium once with `npx --prefix apps/console playwright install chromium`, then run `npm --prefix apps/console run test:e2e`. It starts a local API and worker using fixed synthetic input and a fixed test-only token.
