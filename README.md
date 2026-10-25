# Forecast Anything

Open-source predictive infrastructure built around a **Future Graph**: connect data sources, discover useful questions, and maintain composable, inspectable views of possible futures.

Timestral is the first forecasting-model candidate. Language-model agents interpret sources and propose work; the runtime validates plans, executes numerical tools, preserves provenance, and evaluates issued forecasts against later observations.

## Project status

- Design approved on 24 October 2026.
- Roadmap approved on 24 October 2026; subagent-driven execution selected on 25 October 2026.
- Core plan C1–C6 implemented on `feat/future-graph-core`; branch integration pending.
- CSV CLI, point-in-time snapshots, typed DAG validation, seasonal-naive forecasts, immutable SQLite runs and durable events are available.
- The optional Timestral library adapter is implemented; acceptance remains pending license clarification and real CPU parity. Probabilistic operators, agents, API and observatory UI remain planned.
- The repository is currently private. The code license and final public branding will be resolved before public release.

## Try the core

From the repository root, with [uv](https://docs.astral.sh/uv/) installed:

```sh
uv sync --python 3.12 --extra dev
mkdir -p .local
uv run forecast-anything run examples/minimal/graph.json --data examples/minimal/observations.csv --as-of 2026-10-24T00:00:00Z --db .local/example.db
```

The JSON response identifies the source snapshot and the actual provider, `seasonal_naive`. The example declares `options.period: 2` and produces `[[20.0, 30.0, 20.0]]`. This is a point forecast; it supplies no uncertainty intervals or event probabilities.

Copy `run_id` from that response to retrieve the issued result:

```sh
uv run forecast-anything show RUN_ID --db .local/example.db
uv run pytest -q
```

Repeating the same request returns the same stored run. The initial CLI accepts one explicitly described CSV source and the seasonal-naive provider. The library runtime supports separately bound snapshots and registered providers/operators; builtin numerical operators arrive in plan 02. SQLite files must live on local disk. Overlapping first requests may repeat computation; durable publication remains unique. Job leasing arrives in plan 03.

See [core implementation and decisions](docs/implementation/core.md) for contracts, verification and limits. For optional model installation, pinned revisions, separate code/weights licenses and the pending acceptance gate, see [Timestral provider status](docs/implementation/timestral.md).

## Local quality checks

CI runs these checks on Python 3.12 and 3.14 for pull requests to `main`, pushes to `main`, and manual runs. With uv installed, run the same checks locally:

```sh
uv sync --locked --extra dev
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
uv run --locked pytest -q
uv build
```

Ruff checks core errors and import ordering (`E4`, `E7`, `E9`, `F`, `I`) and formats Python. The build produces a wheel and source distribution in `dist/`.

## Start here

- [Approved design](docs/superpowers/specs/2026-10-24-forecast-anything-design.md)
- [Complete roadmap](docs/roadmap.md)
- [Quality and CI roadmap](docs/quality-roadmap.md)
- [Core and temporal ledger](docs/superpowers/plans/2026-10-24-01-core.md)
- [Models, composition and evidence](docs/superpowers/plans/2026-10-24-02-models-and-evidence.md)
- [Autonomous observatory and agents](docs/superpowers/plans/2026-10-24-03-observatory-and-agents.md)
- [Experience and release](docs/superpowers/plans/2026-10-24-04-experience-and-release.md)

The planning documents are currently in Italian. The four implementation plans contain 21 tasks and 105 checkable steps.

## Working materials

Local scratch files, the pasted source conversation and pre-migration copies are preserved under the ignored work/ directory. The ignored outputs/ directory contains compatibility links for documents already shared in the original chat.
