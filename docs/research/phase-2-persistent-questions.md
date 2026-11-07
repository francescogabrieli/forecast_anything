# Phase 2 — Persistent questions and MCP recovery

## Scope and baseline

This phase is implemented on branch `codex/phase-2-persistent-questions`, starting at merged `origin/main` SHA `41edb94b20ca1d41103f66b7928c5bd023f872d2` (PR #18). Implementation commit: `464f34f` (`feat: add persistent questions and operation recovery`). It adds durable questions and semantic revisions, recoverable operations backed by the existing job queue, compact snapshot summaries, and shared versioned presentations for API and MCP. It does not add guided conversation, source preparation UI, notifications, or embedded MCP Apps.

## Contracts and storage

Migration `src/forecast_anything/migrations/011_persistent_questions.sql` advances the ledger to schema version 11. It creates durable question identity, immutable semantic revisions and revision-bound references, plus idempotency and state for resumable operations. Existing schema version 10 data remains readable.

The additive Pydantic contracts in `src/forecast_anything/contracts.py` cover question create/revise/title patch, question and revision/reference pages, operation create/update/submit/read pages, and compact snapshot summaries. The shared projections in `src/forecast_anything/presentations.py` define versioned forecast, backtest and question presentations. API routes and MCP tools call the same projections. Existing tools, including `summarize_backtest`, remain available.

Question IDs are stable. A title change does not create a semantic revision; semantic revisions use optimistic revision checks and canonical idempotency hashes. References retain the question revision they describe. Operations persist the confirmed request and deterministic expected job ID before enqueueing through the existing `JobQueue`; their logical key namespace is separate from legacy API replay keys. A retry therefore recovers the same job after reconnect or an interrupted enqueue/link step. Reads stay compact, while detailed job results remain available through the existing job read.

Snapshot summaries and paged series metadata expose counts, coverage, units and revision counts without observation values. Presentation bounds include at most 64 forecast points and bounded quantile output. MCP results are checked after serialization against the existing 65,536-byte ceiling.

Generated contracts are committed in `contracts/v1/`, copied into the console API contract directory, and reflected in `apps/console/src/api/schema.generated.ts` and `apps/agent/src/schema.generated.ts`.

## Verification results

| Gate | Observed result |
| --- | --- |
| Full Python suite | 927 passed, 2 skipped. |
| Python style | `ruff check src tests` passed; `ruff format --check src tests` passed (114 files). |
| Contract generation | `scripts/export_contracts.py contracts/v1 --check`, console generated-type check, agent `contracts:check`, and copied OpenAPI/schema comparisons passed. |
| Console | 84 tests passed; typecheck passed; production Vite build passed. |
| Agent | 29 tests passed; typecheck passed. |
| Question/API concurrency | Concurrent same-key creates and semantic revision retries return the same identity; changed intent conflicts; stale revision updates fail; title-only updates preserve the semantic revision; state survives ledger restart and paging is deterministic. |
| Operation recovery | Concurrent submissions converge on one job; operation keys do not collide with legacy job keys. Fault-injection tests recover both before queue commit and after enqueue but before operation/job linking. A fresh MCP client can list, resume and read the same operation/job. |
| MCP presentations | API and MCP return matching shared forecast/backtest/question projections. Existing summary tools remain registered. |
| 320-row CSV | Real MCP stdio journey passes with exactly 320 synthetic rows. It reads the compact summary and every series page, checks that no raw observation values are returned, stays within the serialized 65,536-byte result limit, then forecasts from the stored snapshot. The test uses public API/MCP calls and does not inspect SQLite. |

The focused real-process MCP acceptance can be repeated with:

```sh
PYTHONPATH=src:tests/integration uv run --locked --extra dev --extra mcp pytest -q \
  tests/integration/test_questions_stdio.py \
  tests/integration/test_snapshot_summary_stdio.py
```

This starts local API, worker and MCP processes and therefore needs loopback socket access. No external provider call or private dataset is used by these fixtures.

## Reproduction

From a clean checkout of the phase 2 branch:

```sh
uv sync --locked --extra dev --extra mcp
PYTHONPATH=src:tests/integration uv run --locked --extra dev --extra mcp pytest -p no:cacheprovider -q
uv run --locked --extra dev --extra mcp ruff check src tests
uv run --locked --extra dev --extra mcp ruff format --check src tests
PYTHONPATH=src uv run --locked --extra dev --extra mcp python scripts/export_contracts.py contracts/v1 --check
```

To regenerate contracts after changing models or routes:

```sh
PYTHONPATH=src uv run --locked --extra dev --extra mcp python scripts/export_contracts.py contracts/v1
cp contracts/v1/openapi.json apps/console/src/api/openapi.json
cp contracts/v1/schemas.json apps/console/src/api/schemas.json
(cd apps/console && npm ci && npm run generate:types && npm run check:types && npm run typecheck && npm test -- --run && npm run build)
(cd apps/agent && npm ci --ignore-scripts && npm run contracts:generate && npm run contracts:check && npm run typecheck && npm test -- --run)
```

The Phase 2 test files are `tests/integration/test_questions_api.py`, `tests/integration/test_questions_stdio.py`, `tests/integration/test_operations_api.py`, and `tests/integration/test_snapshot_summary_stdio.py`, alongside `tests/unit/test_mcp_tools.py`, `tests/unit/test_contracts.py`, and `tests/unit/test_export_contracts.py`.

## Limits and authorization boundary

An operation resumes through the same source grants as the corresponding existing MCP submission. In particular, backtest resume rechecks the current source grant even when an operation already has a queued job. The attempted relaxation to let an already queued backtest resume without a current grant was rejected by automatic approval review because it would weaken source authorization; this phase keeps the stricter grant-preserving behavior. If a grant is revoked, restore the operator-approved source grant before calling `resume_operation`.

The work is the phase 2 implementation candidate for review. No phase 3 work, Desktop-specific manual acceptance, live model call, or external service deployment is included.
