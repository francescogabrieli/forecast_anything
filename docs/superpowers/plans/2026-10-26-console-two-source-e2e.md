# Console two-source E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Complete U2's remaining deterministic browser flow for two connected source fixtures, evaluation evidence, watch notification, source revision effects, event replay, and scenario immutability.

**Architecture:** Extend the existing Playwright scenario and its local FastAPI/worker harness. Add a run-scoped evaluation lookup to the API/client because evaluations persist separately from immutable runs, and refresh watch state when the stream reports a worker-generated run completion. Keep discovery candidates single-source per the existing compiler contract; the base run binds both fixtures, while its evaluation lineage resolves to the historical source.

**Tech Stack:** Python 3.12+, FastAPI, SQLite ledger, deterministic local forecast provider, Playwright, TypeScript/React console.

**Spec:** `docs/superpowers/specs/2026-10-26-console-two-source-e2e-design.md`

## Global Constraints

- “Use the real FastAPI service, ledger, worker, and console UI with the declared `SeasonalNaiveProvider` deterministic provider.”
- “Keep all model calls local and deterministic; no API key, network provider, or external dataset is required.”
- “Add no user-facing evaluation workflow.”
- “Keep the existing deterministic test runtime and no external credentials.”
- “Keep base-run identity and stored results unchanged after scenario creation.”

## Review Focus

1. An evaluation must use actuals from the forecast's single history source even when another source is bound — assert actuals lineage and visible evaluation evidence.
2. A revised source must produce a real worker/run event and the expected affected node IDs — assert server event payload and graph state in the browser.
3. Event replay after disconnect must neither lose nor duplicate visible events — retain cursor deduplication and count assertions.
4. A scenario must not mutate its parent run — compare the base run ID and serialized results before and after scenario creation.
5. Keyboard navigation, narrow viewport, and textual/accessibility cues for status and graph changes must remain usable — retain focused keyboard, viewport, role, and state-label checks.

---

### Task 1: Complete the observatory browser flow

**Files:**
- Modify: `src/forecast_anything/store.py` — list persisted evaluations for one run.
- Modify: `src/forecast_anything/api/routes.py` — expose the run-scoped evaluation read path.
- Modify: `apps/console/src/api/client.ts` — retrieve evaluations for a run.
- Modify: `apps/console/src/features/observatory/ObservatoryBoard.tsx` — load run evaluations and refresh watches when a completed-run event arrives.
- Test: `tests/integration/test_api.py` — verify evaluations are listed only for their run through the authenticated route.
- Test: `apps/console/src/api/client.test.ts` — verify the authenticated run-scoped evaluation lookup.
- Modify: `tests/e2e/serve_observatory.py` — seed two deterministic fixtures and the durable run/evaluation/watch lifecycle using the real local service and worker.
- Create: `tests/fixtures/console-e2e-actuals.csv` — later actual observations for the registered history source.
- Create: `tests/fixtures/console-e2e-activity.csv` — the second source fixture bound into the deterministic base graph.
- Modify: `scripts/export_contracts.py` generated artifact `apps/console/src/api/openapi.json` — record the new read endpoint contract.
- Modify: `scripts/export_contracts.py` generated artifact `contracts/v1/openapi.json` — keep the repository's canonical exported API contract in sync.
- Modify: `apps/console/tests/e2e/observatory.spec.ts` — drive the real console and assert the complete acceptance flow.

**Interfaces:**
- Consumes: existing authenticated `/v1/sources`, `/v1/jobs`, `/v1/runs`, `/v1/evaluations`, `/v1/events`, `/v1/watches`, and `/v1/scenarios` contracts; existing console API and labels.
- Produces: authenticated `GET /v1/runs/{run_id}/evaluations -> list[EvaluationRecord]`, ordered by evaluation ID and returning 404 for an unknown run; a browser-visible base run whose graph binds both fixtures and whose evaluation is separately persisted; a refreshed watch view and visible run-completion notification after the worker's source-revision path.

- [x] **Step 1: Extend failing tests first.** Add API route coverage for evaluations scoped to a run (including unknown-run 404), an API client test for the authenticated run-scoped request, and Playwright assertions for both source IDs in base graph/run lineage, visible evaluation evidence, the run-completion notification after a source revision, expected changed graph output nodes, no duplicate replayed events, and unchanged base run ID/results after scenario creation. Keep the existing mobile viewport, forced first SSE disconnect, watch toggle, and keyboard graph selection.
- [x] **Step 2: Run the E2E to confirm the new assertions fail against the current one-source seed.**

  Run: `npm run test:e2e -- --reporter=list` from `apps/console`.

  Expected: the new two-source/evaluation/revision assertions fail; the existing console server and one-source baseline setup still start successfully.
- [x] **Step 3: Expose evaluations already persisted for a run.** Add `Ledger.evaluations_for_run(run_id: str) -> tuple[EvaluationRecord, ...]` ordered by `evaluation_id`, authenticated `GET /v1/runs/{run_id}/evaluations`, the matching API client method, and load it in `ObservatoryBoard.openRun`. Validate the run exists before querying so an unknown run returns 404. Leave immutable `RunRecord.evidence_ids` untouched.
- [x] **Step 4: Refresh observable watch state from real run events.** On each `run_completed` SSE event, refresh the watch list and open the associated run; retain cursor-based event merging. The visible run-completion entry is the notification—do not create a test-only event or alter watch policy.
- [x] **Step 5: Add the two checked-in CSV fixtures and deterministic server setup.** Register both source specs through the local API and bind both source IDs into the base graph while retaining exactly one forecast history source. Keep the candidate/watch single-source; if the base graph must consume both fixtures, add a local test-only deterministic wrapper around `SeasonalNaiveProvider` that explicitly supports its known-future fixture. Run it through the real worker, ingest later history actuals, submit a real evaluation job, and create the real candidate watch. Change/revise the watch's registered source through the worker path and assert the resulting `run_completed` event and output-node IDs. Keep all setup on the same ledger/runtime and use local fixture files only.
- [x] **Step 6: Run focused checks, regenerate contracts, and verify the complete flow.**

  Run: `npm run test:e2e -- --reporter=list` from `apps/console`.

  Expected: 1 Playwright test passes with two fixtures, persisted evaluation evidence, revision notification, replay without duplicate UI events, keyboard operation, narrow viewport, and base-run immutability.

  Run: `npm run typecheck` from `apps/console`.

  Expected: TypeScript reports no errors.

  Run: `uv run pytest tests/integration/test_api.py -q` from repository root.

  Expected: API route suite passes, including run-scoped evaluation lookup.

  Run: `uv run python scripts/export_contracts.py contracts/v1` from repository root, then `npm run check:types` from `apps/console`.

  Expected: checked-in OpenAPI/types match the API contract.
- [x] **Step 7: Commit the completed U2 E2E.**

  ```bash
  git add src/forecast_anything/store.py src/forecast_anything/api/routes.py apps/console/src/api/client.ts apps/console/src/api/client.test.ts apps/console/src/features/observatory/ObservatoryBoard.tsx tests/integration/test_api.py apps/console/src/api/openapi.json contracts/v1/openapi.json apps/console/tests/e2e/observatory.spec.ts tests/e2e/serve_observatory.py tests/fixtures/console-e2e-actuals.csv tests/fixtures/console-e2e-activity.csv docs/superpowers/specs/2026-10-26-console-two-source-e2e-design.md docs/superpowers/plans/2026-10-26-console-two-source-e2e.md
  git commit -m "test: complete console observatory e2e"
  ```
