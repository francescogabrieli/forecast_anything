# Quickstart

Forecast Anything runs locally with a seasonal baseline. The default path needs no LLM key, model weights or hosted account.

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

To connect a CSV, place it in the workspace directory printed by the bootstrap command and enter its container path as `/data/your-file.csv`. The mapping must explicitly identify observation time, value, availability time, revision, series, unit, frequency, timezone, calendar and missing-value markers. Review the proposed profile and resolve every required field before activating the source.

The console shows recorded discoveries, their current quality, event history, graph dependencies and run evidence when available. Its deterministic E2E flow connects two local fixtures, mutes a watch, resumes an interrupted event stream from the durable history, navigates the graph by keyboard and compares an assumed scenario with a worker-produced run. It is a functional test fixture, not a forecast-quality benchmark or a completed external usability study.

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
