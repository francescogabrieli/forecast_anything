# Forecast Anything

Connect explicit data sources, compose forecasts in a **Future Graph**, and inspect what changed, which inputs were available, and which results have evidence behind them.

Forecast Anything is an open-source forecasting infrastructure under development, with an **MCP-first product direction**: use it through your own assistant, with a website for setup and examples and an optional console for graphs and evidence. The local stdio MCP adapter is implemented and tested with the official Python SDK; the supported Desktop MCP workflow has [recorded acceptance](docs/research/desktop-assistant-acceptance.md), and the [local site source](site/README.md) is ready for review before publication. [The console](apps/console/) is optional. See the [product direction](docs/superpowers/specs/2026-10-29-mcp-first-product-design.md).

The current implementation is a local forecasting observatory. The Python runtime validates typed graphs, freezes point-in-time inputs, records immutable forecasts in SQLite, and evaluates them against later observations. A React console uses the same authenticated API. The working name, public owner, package registry and domain remain provisional; this checkout prepares a release candidate and does not identify a published package or hosted service.

## Connect Codex on macOS

Install the local wheel and its locked MCP dependencies, then run `forecast-anything setup --prepare-model`. The setup command starts the workspace service and registers the stdio adapter with Codex. See the [installation guide](docs/installation.md) for the artifact, lifecycle and recovery steps.

## Try a local Timestral forecast

From this checkout, with Python 3.12+ and [uv](https://docs.astral.sh/uv/) installed:

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra mcp forecast-anything model status
uv run --locked --extra mcp forecast-anything model prepare
mkdir -p .local
uv run --locked --extra mcp forecast-anything run examples/minimal/graph.json --data examples/minimal/observations.csv --as-of 2026-10-24T00:00:00Z --db .local/example.db
```

The required forecasting engine is the pinned local **Mistral Timestral-28M**, running on CPU. It needs installed model dependencies and prepared weights, but no Mistral API key. `model prepare` explicitly downloads missing pinned weights and verifies that they load; metadata reads never download them. Weight licensing is separate from the project's code license; see the [model guide](docs/implementation/timestral.md).

The synthetic example records actual Timestral provenance, point forecasts and marginal quantiles, without claiming general accuracy or joint-event probabilities. Repeating the same request returns its stored run; copy its `run_id` to read it later:

```sh
uv run --locked --extra mcp forecast-anything show RUN_ID --db .local/example.db
```

For the assistant/MCP path, see the [MCP guide](docs/implementation/mcp.md). For the console, local API, worker, installed-wheel path and packaging status, follow the [quickstart](docs/quickstart.md). Source mapping, availability time, timezone, cadence, missing values and units must be explicit before ingestion. The minimal CLI accepts exactly one normalized CSV source; API/library source registration supports CSV and bounded HTTP JSON.

## What works, and what the tests establish

| Path | Implemented behavior | Evidence and limits |
| --- | --- | --- |
| Local model demo | Real pinned Timestral computation, deterministic discovery templates and immutable ledger | Prepared weights required; no remote inference key. Seasonal-naive is the comparison baseline, never a silent substitute. |
| MCP stdio | 27 typed tools for CSV registration/refresh, candidate and configured forecasts, frozen multi-origin CSV backtests, recurring-question watches, report/change summaries, immutable evidence reads and single-run evaluation | The official Python SDK exercised real Timestral forecasts, backtests, reconnect and replay through the product API and worker. Earlier Desktop acceptance covered source correction, qualification, automatic refresh and textual reports using the historical baseline runtime. The connected Desktop MCP tools have also read the current Timestral capabilities and a stored real Timestral run. |
| Console and API | Source inspection, explicit first forecast and refresh, discoveries, graph/run details, durable events and isolated scenario comparison | Component/API tests and two Playwright journeys against a real local API/worker: first forecast and two-source evaluation/update/scenario. External usability testing is on hold by owner decision. |
| Composition | Aligned sum, cumulative balance and empirical window events | Representation, unit and sample-identity checks; marginal quantiles cannot be converted into joint paths. |
| Timestral | Required pinned local forecasting adapter for point forecasts and marginal quantiles | CPU fp32 parity and an owner-authorized local comparison across three domains passed. The measured benchmark includes a retail result worse than the baseline; it does not show general superiority. Weight terms apply separately to each user/deployment. |
| Joint residual trajectories | Experimental shared-origin residual-panel sampling with temporal and cross-series sample identity | The recorded experiment did not pass its positive lower Brier-skill acceptance bound in any domain. Available for research; calibrated joint forecast probabilities remain unaccepted. |
| Discovery agent | Optional Eve service with budgeted tools and separate Postgres state | Scripted tests and restart/egress checks exercise integration. A bounded GPT-6 Luna live smoke on 2026-10-26 completed one `inspect_source` tool call against synthetic local data and confirmed a persisted core operation ID; this does not establish model quality or production readiness. |

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

The server defaults to `127.0.0.1:8000`. Except for `/health`, workspace routes, documentation and event streams require `Authorization: Bearer YOUR_TOKEN`. The optional agent operation route requires a separate agent token. Console tokens stay in browser memory. `FORECAST_ANYTHING_CONSOLE_ORIGINS` is a comma-separated list of exact browser origins; when unset, the CLI enables no cross-origin access. Set the actual console origin, including its port. CORS does not replace authentication.

Keep the SQLite ledger on local disk and run one worker per workspace. This is an initial local deployment, with no multi-host coordination claim. See [API contracts](docs/implementation/api.md) and [security guidance](SECURITY.md) before configuring sources or optional agents.

## Contribute and verify

Start with [CONTRIBUTING](CONTRIBUTING.md), the [connector guide](docs/connectors.md), or the [approved design](docs/superpowers/specs/2026-10-24-forecast-anything-design.md). The [roadmap](docs/roadmap.md) includes planned work and unresolved acceptance gates; it is not the capability matrix.

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra dev --extra mcp ruff check src tests
uv run --locked --extra dev --extra mcp ruff format --check src tests
uv run --locked --extra dev --extra mcp pytest -q
uv run --locked --extra dev --extra mcp python scripts/export_contracts.py contracts/v1 --check
uv build
```

Console and agent checks, including the deterministic browser test, are documented in [CONTRIBUTING](CONTRIBUTING.md). Passing offline tests does not prove live model acceptance. The five-person usability study is on hold by owner decision on 2026-10-27; development and technical-preview preparation continue with external usability explicitly unvalidated.

## License and release status

The release candidate includes the [Apache License 2.0](LICENSE), following the roadmap's proposed license for project code. [NOTICE](NOTICE) separates project materials, dependencies, datasets and model weights. Public release remains gated on owner/name/registry decisions, artifact checks and the roadmap's release conditions. No public destination or trademark ownership is implied by this working name.

## Required model and historical evidence

New product forecasts and discovery candidates use Timestral; baseline-only primary requests are rejected, including unused-model and mixed-baseline bypasses. Model setup/inference failures remain errors. Old runs/reports stay immutable and readable. Pending baseline-primary jobs fail with `required_provider_migration`; legacy watches pause with an explicit migration reason and require a new Timestral candidate and fresh evidence. See [real Timestral MCP acceptance](docs/research/required-timestral-acceptance.md).
