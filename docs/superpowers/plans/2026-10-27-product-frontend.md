# Product frontend implementation plan

> **For agentic workers:** use superpowers:subagent-driven-development with disjoint file ownership; integrate and review the entire result before delivery.

**Goal:** replace the technical console with the approved TasteSkill product home and guided workspaces while preserving real forecasting, evidence and graph behavior.

**Architecture:** retain React/TypeScript/Vite, the authenticated API client and existing runtime. Add source/recent-run reads, accessible URL navigation and a product shell; turn mapping JSON into guided controls; render actual persisted forecasts/evaluations with technical material progressively disclosed.

**Tech Stack:** existing React 19, TypeScript, Vite, Vitest and Playwright; local IBM Plex Sans; CSS and SVG.

**Spec:** `docs/superpowers/specs/2026-10-27-product-frontend-design.md` (approved).

## Global constraints

- Every visible action uses the real API or performs a clear local navigation/edit operation.
- Preserve API authentication, in-memory-only tokens, source semantics, immutable evidence and point-in-time behavior.
- Do not invent forecast performance, activity counts, data, confidence bands or autonomous-discovery success.
- No framework migration, external hosted platform or mandatory cloud account.
- First forecast remains a single series, one future interval and seasonal-naive; upload and interactive multi-origin backtesting are subsequent milestones.
- TasteSkill Framed sheet, seed 260034763; production browser inspection at 1440/768/390 and visual critique.

## Review focus

1. Delayed responses after workspace/source replacement cannot leak old data into the new view (tasks 1 and 4).
2. Source lists/history errors and event histories beyond 1,000 events do not masquerade as empty workspaces (tasks 1 and 4).
3. Guided controls preserve explicit constants/columns, unresolved roles and advanced mapping extensions without silently changing semantics (task 2).
4. Missing observations, point-only forecasts and failed evaluation reads cannot create false chart continuity or performance claims (task 3).
5. URL back/forward, keyboard focus and narrow screens preserve the current workspace and working actions (task 4).

## Task 1: trustworthy home data reads

**Files:** `apps/console/src/api/client.ts`, new `apps/console/src/api/client.test.ts`.

**Interfaces:** `ApiClient.getSources(): Promise<SourceView[]>`; `ApiClient.getRecentRuns(limit?: number): Promise<RunRecord[]>`, default 4. Consume existing `getEvents(after,1000)` and `getRun(id)`.

- [x] Test through mocked HTTP fetch: source read uses bearer auth; paginated events with >1,000 entries find newest distinct completed runs; a failed later page rejects instead of returning partial/empty history. Non-advancing full page fails explicitly.
- [x] Run focused tests RED.
- [x] Add wrappers and complete cursor pagination; order unique run IDs by newest completed event and load requested run records. Bound visible recent list without truncating event discovery.
- [x] Run focused tests GREEN and typecheck.

## Task 2: guided source mapping

**Files:** `ConnectSource.tsx`, `ConnectSource.test.tsx`, new source mapping component/tests under `apps/console/src/features/sources/`.

**Interfaces:** retain existing `ConnectSource` props and activation/draft callbacks. Mapping form consumes parsed `SourceSpec.mapping` and emits a complete mapping; raw JSON editor remains inside named advanced details.

- [x] Test a source can be previewed and activated after filling labeled mapping controls without editing JSON; edits invalidate profile/first forecast; advanced constants and unknown keys survive unrelated edits; malformed advanced JSON is editable and blocks activation.
- [x] Run focused tests RED.
- [x] Implement labeled column/constant controls for temporal/value/series/unit/revision roles, cadence/timezone/calendar/missing markers and HTTP records path. Preserve server profile proposal, async draft guards and existing API contract.
- [x] Run source component tests GREEN. No app-shell or global CSS edits in this task.

## Task 3: evidence-led results

**Files:** `RunDetails.tsx`, `RunDetails.test.tsx`, new `ForecastChart.tsx` and tests; optional scoped results CSS.

**Interfaces:** retain `RunDetails` props. Chart consumes `ForecastResult`, run origin and matching snapshot observations; emit accessible SVG plus text/table alternative. No API/backend changes.

- [x] Tests cover point forecast chart with named axes/units/origin, missing values split paths, no invented bands, recorded MAE displayed, and unevaluated copy when no evaluation exists.
- [x] Run focused tests RED.
- [x] Put actual forecast value/date/unit and chart first; retain existing tables/provenance links in accessible details and show recorded metric values. Preserve experimental/stale states and snapshot anchors.
- [x] Run result component tests GREEN. Keep existing headings/actions required by real E2E discoverable.

## Task 4: product shell, home and integration

**Files:** `App.tsx`, new home/navigation components/tests, `styles.css`, `index.html`, local fonts/license, optional view selection in `ObservatoryBoard.tsx`, console E2E spec and contributor docs.

**Interfaces:** home consumes task 1 methods plus explicit `refreshSource` and renders `FirstForecast` from returned registration. Navigation destinations: Home, Fonti, Osservatorio and Workspace; graph/results/scenarios remain in the observatory. Support URL hash back/forward; workspace tokens stay only in memory.

- [x] Tests RED for new navigation, empty/error home, returning-source refresh, cancellation on client change and mobile menu focus.
- [x] Build Framed sheet shell with real product mark; workspace settings hold API/token setup. Render task 2/3 components without recreating their data logic. Preserve live observatory subscriptions across navigation or cancel/reload safely.
- [x] Load licensed IBM Plex Sans locally. TasteSkill app-screen rules govern layout, type, color and states. No placeholder data or fake controls.
- [x] Adapt the two real API/worker E2E journeys to navigate the product, and verify back/forward and narrow viewport. Do not weaken existing assertions on persisted results, evaluation, notification or scenarios.
- [x] Run full console tests, typecheck, generated types and production build; run actual browser E2E. Run TasteSkill production inspector and open every final screenshot; critique/fix up to three rounds.
- [x] Independent review, address important findings with regressions, then commit/push and update the PR. Record delivered scope and remaining upload/backtesting milestones.
