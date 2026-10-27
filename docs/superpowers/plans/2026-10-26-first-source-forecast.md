# First forecast after connecting a source

> **For agentic workers:** use superpowers:executing-plans for this single integrated task. Steps use checkbox syntax.

**Goal:** Let a user obtain and inspect one provisional baseline forecast after activating a supported source.

**Architecture:** Reuse the source registration's discovery job, its stored snapshot and a trusted executable `expected_deviation` candidate. An explicit, idempotent source refresh creates a new discovery epoch when the original snapshot is stale. Submit the trusted candidate's graph through the existing run-job API only after an explicit user action, then show its issued value and open the persisted run in the observatory. Keep source lineage, issue time, and errors visible; do not create a watch or claim validation.

**Tech stack:** React, TypeScript, existing FastAPI contracts, Vitest and Playwright.

**Spec:** `docs/superpowers/specs/2026-10-24-forecast-anything-design.md`.

## Constraints and review focus

- Use only a snapshot produced by the source's own discovery job and the corresponding executable single-source candidate; never synthesize inputs or reuse another source's candidate.
- A missing snapshot, unfinished/failed job, unsupported candidate, failed run, stale component, or invalid/past target must not produce a success state.
- A refresh uses a client key and a new epoch; a repeated key reuses the request, and changed source configuration with the same key is rejected.
- The user explicitly starts the run; preserve provisional status and the provider's actual identity, timestamp and assumptions.
- Keep the existing app's palette and type; use the Taste app-screen rules, meaningful controls and accessible status/error states.

## Task 1: source activation to issued forecast

**Files:** `src/forecast_anything/contracts.py`, `src/forecast_anything/api/{routes,service}.py`, exported API contracts, `tests/integration/test_api.py`, `apps/console/src/api/client.ts`, `apps/console/src/App.tsx`, `apps/console/src/features/sources/ConnectSource.tsx`, new `apps/console/src/features/sources/FirstForecast.tsx`, `apps/console/src/features/observatory/{ObservatoryBoard,RunDetails}.tsx`, `apps/console/src/styles.css`, corresponding tests and `tests/e2e/observatory.spec.ts`.

- [x] **1. Tests:** exercise completed discovery → explicit run submission → persisted run; cover missing/mismatched data, unsupported candidates, failed jobs, late responses from replaced sources and refresh after data changes outside the inspection sample.
- [x] **2. Verify red:** the focused component and API refresh tests failed before implementation.
- [x] **3. Implement:** expose source refresh, candidate and run calls; carry the actual registration into a cancellable first-forecast panel, validate the snapshot and target, and route the completed run to the existing detail view.
- [x] **4. Verify:** component and console tests, typecheck/build, and a real synthetic browser journey from source activation through persisted forecast; inspect desktop, tablet and phone with Taste.
- [x] **5. Record limits:** one candidate, one-step baseline forecast, point output, no automatic activation or external model call.

## Consolidation on 2026-10-27

Resumed the existing implementation for review and delivery with the owner's authorization to commit, push and open a PR. Independent review found two retry defects: mutable source samples caused refresh-key conflicts, and ambiguous run responses led to duplicate emissions. Regression tests failed before the fixes and passed afterward. Refresh retries now return the original job/profile even after data changes or source unavailability, while changed configuration still conflicts. Run retries preserve their key until a confirmed terminal job failure or a replacement discovery context.

The browser suite also exposed a clock regression in the study harness. `FA_USABILITY=1` now opts into the session's current date; automated E2E keeps the historical fixed clock. Both browser journeys passed after the fix.

Fresh validation: Python **501 passed, 1 skipped**; console **35 passed**; real API/worker Playwright **2 passed**; console typecheck/build/generated types, Ruff and both exported contract checks passed. The five-person observed usability study remains outstanding.
