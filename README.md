# Forecast Anything

Connect explicit data sources, compose forecasts in a **Future Graph**, and inspect what changed, which inputs were available, and which results have evidence behind them.

Forecast Anything is an open-source forecasting infrastructure under development, with an **MCP-first product direction**: use it through your own assistant, with a website for setup and examples and an optional console for graphs and evidence. The local stdio MCP adapter is implemented and tested with the official Python SDK; the supported Desktop MCP workflow has [recorded acceptance](docs/research/desktop-assistant-acceptance.md), while public website delivery remains separate. See the [product direction](docs/superpowers/specs/2026-10-29-mcp-first-product-design.md).

The current implementation is a local forecasting observatory. The Python runtime validates typed graphs, freezes point-in-time inputs, records immutable forecasts in SQLite, and evaluates them against later observations. A React console uses the same authenticated API. The working name, public owner, package registry and domain remain provisional; this checkout prepares a release candidate and does not identify a published package or hosted service.

## Try a forecast without model keys or weights

From this checkout, with Python 3.12+ and [uv](https://docs.astral.sh/uv/) installed:

```sh
uv sync --locked --extra dev
mkdir -p .local
uv run --locked forecast-anything run examples/minimal/graph.json --data examples/minimal/observations.csv --as-of 2026-10-24T00:00:00Z --db .local/example.db
```

The response names the actual provider, `seasonal_naive`, and contains the point forecast `[[20.0, 30.0, 20.0]]`. The example explicitly sets period 2. It is a synthetic fixture with no uncertainty intervals or event probabilities. Repeating the request returns the same stored run; copy its `run_id` to read it later:

```sh
uv run --locked forecast-anything show RUN_ID --db .local/example.db
```

For the assistant/MCP path, see the [MCP guide](docs/implementation/mcp.md). For the console, local API, worker, installed-wheel path and packaging status, follow the [quickstart](docs/quickstart.md). Source mapping, availability time, timezone, cadence, missing values and units must be explicit before ingestion. The minimal CLI accepts exactly one normalized CSV source; API/library source registration supports CSV and bounded HTTP JSON.

## What works, and what the tests establish

| Path | Implemented behavior | Evidence and limits |
| --- | --- | --- |
| Baseline demo | Real seasonal-naive computation, deterministic source discovery templates, immutable ledger | No LLM or downloaded model weights required. It does not establish forecast quality on arbitrary data. |
| MCP stdio | 26 typed tools for CSV registration/refresh, candidate and configured forecasts, frozen multi-origin CSV backtests, recurring-question watches, report/change summaries, immutable evidence reads and single-run evaluation | Official `mcp==2.3.0` client over real subprocess stdio, authenticated API and independent worker; disconnect/reconnect and original-key replay, plus installed-wheel baseline and configured/backtest journeys outside checkout. Desktop source correction, candidate-bound qualification, automatic refresh and textual report interpretation were exercised; the owner confirmed quit/reopen and immutable reread. No live-model compatibility claim. |
| Console and API | Source inspection, explicit first forecast and refresh, discoveries, graph/run details, durable events and isolated scenario comparison | Component/API tests and two Playwright journeys against a real local API/worker: first forecast and two-source evaluation/update/scenario. External usability testing is on hold by owner decision. |
| Composition | Aligned sum, cumulative balance and empirical window events | Representation, unit and sample-identity checks; marginal quantiles cannot be converted into joint paths. |
| Timestral | Optional pinned library adapter for point forecasts and marginal quantiles | CPU fp32 parity and an owner-authorized local comparison across three domains passed. The measured benchmark includes a retail result worse than the baseline; it does not show general superiority. Weight terms apply separately to each user/deployment. |
| Joint residual trajectories | Experimental shared-origin residual-panel sampling with temporal and cross-series sample identity | The recorded experiment did not pass its positive lower Brier-skill acceptance bound in any domain. Available for research; calibrated joint forecast probabilities remain unaccepted. |
| Discovery agent | Optional Eve service with budgeted tools and separate Postgres state | Scripted tests and restart/egress checks exercise integration. A bounded GPT-6 Luna live smoke on 2026-10-26 completed one `inspect_source` tool call against synthetic local data and confirmed a persisted core operation ID; this does not establish model quality or production readiness. |

See the [capability matrix](docs/capabilities.md) for precise boundaries and [Timestral status](docs/implementation/timestral.md) for the separate code/weights licenses. Historical replay and synthetic assumptions must remain labeled. Generic backtest reports carry no discovery attestation and do not qualify or activate watches; that lifecycle integration remains future work.

## Run the local API

Start the API and one worker against the same local SQLite file. Use the same exported environment in both terminals:

```sh
mkdir -p .local
export FORECAST_ANYTHING_WORKSPACE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export FORECAST_ANYTHING_CONSOLE_ORIGINS="http://127.0.0.1:5173,http://localhost:5173"
uv run --locked forecast-anything serve --db .local/observatory.db
# In a second terminal:
uv run --locked forecast-anything worker --db .local/observatory.db
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
