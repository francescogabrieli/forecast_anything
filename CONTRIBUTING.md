# Contributing

This repository is preparing a release candidate. The project name, public owner and publishing destinations remain provisional. Do not infer that a registry package, container image, support address or public deployment exists.

Use the [capability matrix](docs/capabilities.md) to distinguish implemented behavior from the [roadmap](docs/roadmap.md). Small contributions with a reproducible example and explicit limits are welcome. Report suspected vulnerabilities through [SECURITY](SECURITY.md), and keep secrets and private observations out of issues and fixtures.

## Set up and check the core

Use Python 3.12+ and uv from the repository root:

```sh
uv sync --locked --extra dev
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
uv run --locked pytest -q
uv run --locked python scripts/export_contracts.py contracts/v1 --check
uv run --locked python scripts/export_contracts.py apps/console/src/api --check
uv build
```

CI targets Python 3.12 and 3.14. Keep dependency locks and generated contracts synchronized with intentional changes. Do not hand-edit generated schemas or use a skipped model test as evidence that the provider works. The Timestral real-model test is gated; see [its acceptance conditions](docs/implementation/timestral.md). Routine tests require neither model weights nor paid API calls.

## Console and browser checks

Use Node 24.5+ and the console's lockfile:

```sh
cd apps/console
npm ci
npm run check:types
npm run typecheck
npm test -- --run
npm run build
npx playwright install chromium
npm run test:e2e
```

The Playwright configuration starts a Python API/worker and a Vite console on loopback ports 8000 and 4173. Keep those ports free so the test uses its own fixture services. Its synthetic source, fixed clock and seasonal-naive provider exercise the browser/API path, SSE reconnect and scenario comparison without external model calls. They do not validate live LLM discovery, Timestral quality or real-world data freshness.

For a development console on port 5173, configure the API with `FORECAST_ANYTHING_CONSOLE_ORIGINS=http://127.0.0.1:5173,http://localhost:5173`. Origins must match the browser's scheme, host and port. Keep workspace tokens in memory and out of URLs, browser storage, logs and screenshots.

## Optional agent checks

The agent is separate from the numerical core. In `apps/agent`, run:

```sh
npm ci --ignore-scripts
npm run contracts:check
npm run typecheck
npm test -- --run
npm run build
bash scripts/check-egress-policy.sh
bash scripts/check-postgres-restart.sh
```

Build and Docker integration checks require a running Docker daemon. The checks use controlled model responses and disposable state; they do not authorize a paid live request. The restart fixture simulates expiry of the stale job lock instead of waiting four hours. See the [agent README](apps/agent/README.md) for token separation, Postgres and service-level egress requirements.

## Contracts and review expectations

Preserve point-in-time semantics: `event_time` describes the observation and `available_at` describes when it became usable. Corrections must not rewrite issued runs. Keep source text untrusted, use structured errors, and add numerical evidence through the runtime rather than model prose.

New sources use the existing `SourceSpec` and ingestion contracts; start with the [connector guide](docs/connectors.md). Providers implement `ForecastProvider`; operators implement `Operator`. Declare only representations actually supported, preserve units and lineage, and reject incompatible calendars or sample identities. Document unsupported cases alongside the feature.

For a pull request, describe the concrete before/after behavior, a minimal reproducer or fixture, verification commands and results, and any untested path. Meaningful tests should cover the behavior or failure mode, including credential handling for source changes. Update documentation and generated contracts when their observable behavior changes. Keep unrelated refactors separate.

## Starter contribution proposals

These starter issues are open; check the linked discussion before starting work:

| Proposal | Fixture | Acceptance |
| --- | --- | --- |
| [Connector: add explicit HTTP pagination #9](https://github.com/francescogabrieli/forecast_anything/issues/9) | Loopback server with two pages, repeated cursors and a cross-origin next link | Bounded requests and response sizes; reject unsafe credential forwarding; deterministic rows and provenance; keep existing non-paginated reads working. A new connector kind requires explicit contract review. |
| [Data recipe: a new public daily series #10](https://github.com/francescogabrieli/forecast_anything/issues/10) | Small attributed raw sample, checksum, documented timezone and publication-time assumptions | Reproducible normalized observations; missing values retained; frozen selection/verification origins; no download or redistribution without checking the dataset terms. |
| [Operator: calendar-aligned difference #11](https://github.com/francescogabrieli/forecast_anything/issues/11) | Two compatible point/path results and fixtures with mismatched units, dates and sample groups | Explicit existing `OperatorContract`; correct subtraction and lineage; reject incompatible inputs; no probability or quantile arithmetic without a justified representation. |

## Licensing

The candidate prepares Apache-2.0 for project code under the [LICENSE](LICENSE), following the roadmap proposal. Include the provenance and license of any contributed external material and preserve required notices. Dataset and model-weight terms remain separate; [NOTICE](NOTICE) points to their inventories. Do not introduce a guessed copyright holder or publication destination.
