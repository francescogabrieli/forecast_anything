# Repository Guidelines

## Project Structure & Module Organization

The Python runtime lives in `src/forecast_anything/`; API, connectors, backtesting, operators, migrations, and evaluation code are grouped by module. `apps/console/` contains the React/Vite workspace, while `apps/agent/` contains the optional TypeScript agent. Python tests are under `tests/unit`, `tests/integration`, and `tests/model`; console and agent tests live with their apps. Shared contracts are in `contracts/`, examples in `examples/`, docs in `docs/`, and the public site in `site/`.

## Build, Test, and Development Commands

Use Python 3.12+ and `uv`; the apps require Node 24.5+.

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra dev --extra mcp pytest -q
uv run --locked --extra dev --extra mcp ruff check src tests
uv run --locked --extra dev --extra mcp ruff format --check src tests
uv build
```

For the console, run `cd apps/console && npm ci && npm test -- --run && npm run build`; run `npm run test:e2e` for browser coverage. For the agent, use `cd apps/agent && npm ci --ignore-scripts`, then `npm run typecheck`, `npm test -- --run`, and `npm run build`. See `CONTRIBUTING.md` for full contract, browser, and integration checks.

## Coding Style & Naming Conventions

Keep every Python file under `src/`, `tests/`, and `scripts/` at 450 lines or fewer. When a change would cross that limit, split the implementation or tests by responsibility as part of the change. Run `python scripts/check_python_file_lengths.py` locally before handing off or opening a PR when working on a branch that includes the checker used by `main`.

Follow existing module boundaries and nearby patterns. Python is formatted and linted with Ruff (four-space indentation, double quotes; lint checks include import sorting). Use descriptive `snake_case` names in Python and the existing TypeScript conventions (`camelCase` functions, `PascalCase` React components). Regenerate or check contract outputs with the scripts documented in `CONTRIBUTING.md`; do not hand-edit generated files.

Use `SourceSpec` and the existing ingestion contracts for connectors, `ForecastProvider` for providers, and `Operator` for operators. Declare the representations the implementation supports and preserve units and lineage. Keep generated contracts and dependency locks synchronized with the source changes that affect them.

## Testing Guidelines

Add focused tests for behavior changes and failure cases. Name Python tests `test_*.py`; TypeScript tests use `*.test.ts` or `*.test.tsx`. Keep fixtures deterministic and synthetic where possible. Routine checks should not require live model calls or private data; model-specific acceptance limits are documented separately.

When working on benchmarks, keep datasets, model weights, and generated run artifacts in ignored local locations. Keep reserved holdouts out of tuning and routine evaluation. Report real-model acceptance checks separately from offline tests and identify any skipped checks in the handoff.

## Commit & Pull Request Guidelines

Recent commits use short conventional prefixes such as `feat:`, `fix:`, and `docs:`. Keep each commit focused. Pull requests should explain the before/after behavior, provide a reproducer or fixture, list verification commands and results, and disclose untested paths. Update docs and generated contracts when observable behavior changes. Keep credentials and private observations out of commits, fixtures, and screenshots; report vulnerabilities through `SECURITY.md`.
