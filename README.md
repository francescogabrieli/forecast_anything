# Forecast Anything

Connect explicit data sources, compose forecasts in a **Future Graph**, and inspect what changed, which inputs were available, and which results have evidence behind them.

Forecast Anything is a local predictive observatory. The **assistant connected over MCP is the main interface**: ask a question, keep its forecast and evidence, and return after new data arrives. The public site explains setup and shows a [reproducible synthetic journey](docs/release-demo.md); contextual views expose exact results and their evidence. [The advanced console](apps/console/) is optional. The local stdio adapter is tested with the official Python SDK; host-specific acceptance is tracked separately in the [MCP compatibility matrix](docs/capabilities.md).

The current implementation is a local forecasting observatory. The Python runtime validates typed graphs, freezes point-in-time inputs, records immutable forecasts in SQLite, and evaluates them against later observations. A React console uses the same authenticated API. Forecasting runs in your local workspace.

## Connect your assistant

Install the local wheel and its locked MCP dependencies, prepare the pinned local Timestral model, and connect the stdio server to your assistant. On macOS, `forecast-anything setup --prepare-model` starts the workspace service and registers Codex. For another MCP client, follow the [MCP connection guide](docs/implementation/mcp.md). Then ask for a CSV preview, confirm its explicit time and unit assumptions, and submit the first forecast. The [quickstart](docs/quickstart.md) and [installation guide](docs/installation.md) walk through the same path.

The [release demo](docs/release-demo.md) reproduces a synthetic CSV, historical Timestral-versus-baseline comparison, saved question, disconnected worker update and change explanation. Its scores do not establish predictive accuracy.

## Try a local Timestral forecast

From this checkout, with Python 3.12+ and [uv](https://docs.astral.sh/uv/) installed:

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra mcp forecast-anything model status
uv run --locked --extra mcp forecast-anything model prepare
mkdir -p .local
uv run --locked --extra mcp forecast-anything run examples/minimal/graph.json --data examples/minimal/observations.csv --as-of 2026-10-24T00:00:00Z --db .local/example.db
```

The default forecasting engine is pinned local **Mistral Timestral**, running on CPU. New workspaces default to 28M and can select 123M at setup. It needs installed model dependencies and prepared weights, but no Mistral API key. `model prepare` installs missing pinned inference code, downloads missing weights and verifies CPU loading. Metadata reads are read-only. Weight licensing is separate from the project's code license; see the [model guide](docs/implementation/timestral.md).

The synthetic example records actual Timestral provenance, point forecasts and marginal quantiles, without claiming general accuracy or joint-event probabilities. Repeating the same request returns its stored run; copy its `run_id` to read it later:

```sh
uv run --locked --extra mcp forecast-anything show RUN_ID --db .local/example.db
```

For the assistant/MCP path, see the [MCP guide](docs/implementation/mcp.md). For the console, local API, worker, installed-wheel path and packaging status, follow the [quickstart](docs/quickstart.md). Source mapping, availability time, timezone, cadence, missing values and units must be explicit before ingestion. The minimal CLI accepts exactly one normalized CSV source; API/library source registration supports CSV and bounded HTTP JSON.

## What works, and what the tests establish

| Path | Implemented behavior | Evidence and limits |
| --- | --- | --- |
| Local model demo | Real pinned Timestral computation, deterministic discovery templates and immutable ledger | Prepared weights required; no remote inference key. Seasonal-naive is the comparison baseline, never a silent substitute. |
| MCP stdio | Typed tools for CSV registration/refresh, candidate and configured forecasts, frozen multi-origin CSV backtests, recurring-question watches, report/change summaries, immutable evidence reads and single-run evaluation | The official Python SDK exercised real Timestral forecasts, backtests, reconnect and replay through the product API and worker. Earlier Desktop acceptance covered source correction, qualification, automatic refresh and textual reports using the historical baseline runtime. The connected Desktop MCP tools have also read the current Timestral capabilities and a stored real Timestral run. |
| Console and API | Source inspection, explicit first forecast and refresh, discoveries, graph/run details, durable events and isolated scenario comparison | Component/API tests and two Playwright journeys against a real local API/worker: first forecast and two-source evaluation/update/scenario. External usability remains unvalidated. |
| Composition | Aligned sum, cumulative balance and empirical window events | Representation, unit and sample-identity checks; marginal quantiles cannot be converted into joint paths. |
| Timestral | Required pinned local forecasting adapter for point forecasts and marginal quantiles | CPU fp32 parity and a local comparison across three domains passed. The measured benchmark includes a retail result worse than the baseline; it does not show general superiority. Weight terms apply separately to each user/deployment. |
| Joint residual trajectories | Experimental shared-origin residual-panel sampling with temporal and cross-series sample identity | The recorded experiment did not pass its positive lower Brier-skill acceptance bound in any domain. Available for research; calibrated joint forecast probabilities remain unaccepted. |

See the [capability matrix](docs/capabilities.md) for precise boundaries and [Timestral status](docs/implementation/timestral.md) for the separate code/weights licenses. Historical replay and synthetic assumptions must remain labeled. Only a backtest bound to a watch’s frozen candidate can qualify it, with positive measured skill on at least 30 evaluated non-overlapping final origins and previously unused windows for the source revision. Generic reports and `summarize_backtest` show the recorded comparison. See the [MCP guide](docs/implementation/mcp.md).

For a service that starts at macOS login, see [installation, updates and removal](docs/installation.md). See [public repository readiness](docs/public-repository.md) for the publication checklist.

## Run the local API

Start the API and one worker against the same local SQLite file. Use the same exported environment in both terminals:

```sh
mkdir -p .local
export FORECAST_ANYTHING_WORKSPACE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export FORECAST_ANYTHING_CONSOLE_ORIGINS="http://127.0.0.1:5173,http://localhost:5173"
uv run --locked --extra mcp forecast-anything serve --db .local/observatory.db
# In a second terminal:
uv run --locked --extra mcp forecast-anything worker --db .local/observatory.db
```

The server defaults to `127.0.0.1:8000`. Except for `/health`, workspace routes, documentation and event streams require `Authorization: Bearer YOUR_TOKEN`. Console tokens stay in browser memory. `FORECAST_ANYTHING_CONSOLE_ORIGINS` is a comma-separated list of exact browser origins; when unset, the CLI enables no cross-origin access. Set the actual console origin, including its port. CORS does not replace authentication.

The supported setup uses one SQLite ledger. Keep it on local disk and run one worker per workspace. This is an initial local deployment, with no multi-host coordination claim. See [API contracts](docs/implementation/api.md) and [security guidance](SECURITY.md) before configuring sources.

## Contribute and verify

Start with [CONTRIBUTING](CONTRIBUTING.md), the [connector guide](docs/connectors.md), or the [architecture overview](docs/implementation/core.md). The [roadmap](docs/roadmap.md) describes product priorities.

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra dev --extra mcp ruff check src tests
uv run --locked --extra dev --extra mcp ruff format --check src tests
uv run --locked --extra dev --extra mcp pytest -q
uv run --locked --extra dev --extra mcp python scripts/export_contracts.py contracts/v1 --check
uv build
```

Console and agent checks, including the deterministic browser test, are documented in [CONTRIBUTING](CONTRIBUTING.md). Passing offline tests does not prove live model acceptance.

## License and release status

Project code is available under the [Apache License 2.0](LICENSE). [NOTICE](NOTICE) describes the terms for dependencies, datasets and model weights.

## Required model and historical evidence

Timestral is the default. Configured forecasts can [select a provider using held-out backtest results](docs/implementation/mcp.md#choose-a-provider-using-backtest-evidence). Raw graph submissions and discovery candidates use the default provider policy. Model setup/inference failures remain errors. Old runs/reports stay immutable and readable. Pending baseline-primary jobs fail with `required_provider_migration`; legacy watches pause with an explicit migration reason and require a new Timestral candidate and fresh evidence. See the [Timestral guide](docs/implementation/timestral.md).
