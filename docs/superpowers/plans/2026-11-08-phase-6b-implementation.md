# Phase 6B Continuity and Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep saved questions current through background source updates and expose durable, recoverable notifications through the API, MCP, and contextual views.

**Architecture:** SQLite remains the durable authority for watch transitions, question references, the inbox, webhook subscriptions, and the outbox. The existing worker and job queue perform refresh, qualification, and delivery work; API and MCP add typed controls and bounded reads over the same ledger.

**Tech Stack:** Python 3.12, SQLite, FastAPI, official MCP SDK, React/Vite, pytest.

**Spec:** `docs/research/phase-6a-continuity-contract.md`; phase outline: `docs/superpowers/plans/2026-11-08-phase-6-continuity-and-updates.md`.

## Global Constraints

- A new qualification requires 30 independent final origins; `BacktestSettings.max_origins_per_partition` remains capped at 50.
- Requalification uses at most one automatic backtest job per question per 24-hour window and a 300-second execution limit.
- Polling (`next_due_at`), forecast horizon freshness, evidence applicability, and requalification deadlines remain separate state.
- Historical `available_at` changes invalidate the candidate and evidence; event IDs include event kind and a stable transition ID.
- Webhooks are opt-in, use a durable outbox, send `X-Forecast-Event-Id`, and stop after three total attempts with 30- and 120-second delays.
- Pause and mute have distinct effects; source subscriptions are independent from MCP source grants.
- Existing snapshots, runs, reports, evaluations, and decisions remain immutable.

## Review Focus

- A change to a historical `available_at` value must not pass append classification; cover in Task 2.
- Replayed worker execution after a crash must retain one event and the same webhook event ID; cover in Tasks 1 and 4.
- Pausing one question must not stop polling or runs for another question sharing the same source; cover in Task 3.
- Muting after an event is queued must preserve the inbox event and suppress its pending delivery; cover in Task 4.
- Revoking the worker source subscription must stop later jobs without consulting MCP client grants; cover in Task 3.

---

### Task 1: Durable question controls, inbox, and event identity

**Files:**
- Modify: `src/forecast_anything/contracts.py`
- Modify: `src/forecast_anything/migrations/013_continuity_and_inbox.sql`
- Modify: `src/forecast_anything/question_storage.py`
- Modify: `src/forecast_anything/store.py`
- Test: `tests/integration/test_questions_api.py`
- Test: `tests/unit/test_question_storage.py`

**Interfaces:**
- Consumes: stable question IDs, semantic revisions, references, and SQLite transaction helpers.
- Produces: deterministic `record_inbox_event(...)`, bounded inbox reads, and persisted question mute/priority controls.

- [x] **Step 1: Write failing storage/API tests** for deterministic event IDs including event kind and transition ID, idempotent event insertion, pagination ordered by question priority, and mute/priority persistence.
- [x] **Step 2: Run the focused tests and confirm the expected missing behavior.**
- [x] **Step 3: Implement the contracts, migration, and transactional storage methods.**
- [x] **Step 4: Run the focused tests and verify the event and control behavior.**

### Task 2: Snapshot classification and provisional requalification

**Files:**
- Modify: `src/forecast_anything/contracts.py`
- Modify: `src/forecast_anything/watches.py`
- Modify: `src/forecast_anything/worker.py`
- Modify: `src/forecast_anything/backtesting/planning.py`
- Modify: `src/forecast_anything/backtesting/service.py`
- Test: `tests/unit/test_watches.py`
- Test: `tests/unit/test_continuity.py`
- Test: `tests/integration/test_worker.py`

**Interfaces:**
- Consumes: immutable snapshots, source mappings, the shared queue, existing backtest policy, and question-to-watch references.
- Produces: deterministic unchanged/append/rectification classification, same-question run references, a provisional state, and budgeted automatic requalification.

- [x] **Step 1: Write failing tests** for unchanged snapshots, valid append, historical availability mutation, late rows, corrections, expired forecast horizons, insufficient final origins, budget cooldown, and loss of qualification.
- [x] **Step 2: Run the focused tests and confirm failures are caused by missing continuity behavior.**
- [x] **Step 3: Implement classification, lifecycle transitions, run linking, and backtest scheduling with 30 final origins and a frozen origin floor.**
- [x] **Step 4: Run focused unit and worker integration tests.**

### Task 3: Pause, priority, and shared source subscriptions

**Files:**
- Modify: `src/forecast_anything/contracts.py`
- Modify: `src/forecast_anything/question_storage.py`
- Modify: `src/forecast_anything/worker.py`
- Modify: `src/forecast_anything/jobs.py`
- Modify: `src/forecast_anything/api/routes.py`
- Modify: `src/forecast_anything/api/service.py`
- Test: `tests/integration/test_questions_api.py`
- Test: `tests/integration/test_worker.py`

**Interfaces:**
- Consumes: Task 1 question controls, Task 2 watch transitions, and the existing durable queue.
- Produces: explicit pause/resume controls, persisted source worker subscriptions, priority-aware scheduling, and revocation propagation.

- [x] **Step 1: Write failing API/worker tests** for pending and running work, chained jobs, two questions on one source, source revocation, and priority ordering.
- [x] **Step 2: Run the focused tests and confirm the expected control failures.**
- [x] **Step 3: Implement pause/resume suppression, source subscription operations, and deterministic queue priority updates.**
- [x] **Step 4: Run focused API and worker integration tests.**

### Task 4: Opt-in webhook outbox and retry recovery

**Files:**
- Modify: `src/forecast_anything/contracts.py`
- Modify: `src/forecast_anything/jobs.py`
- Modify: `src/forecast_anything/worker.py`
- Modify: `src/forecast_anything/question_storage.py`
- Modify: `src/forecast_anything/api/routes.py`
- Modify: `src/forecast_anything/api/service.py`
- Test: `tests/integration/test_webhooks.py`

**Interfaces:**
- Consumes: durable inbox events and the shared leased queue.
- Produces: operator-managed webhook subscriptions, minimal signed/idempotent payloads, and durable delivery state with bounded retries.

- [x] **Step 1: Write failing tests** for successful delivery, same-ID retry after crash, mute suppression, 30/120-second delays, and final `delivery_failed` with inbox retention.
- [x] **Step 2: Run the focused tests and confirm they fail on missing delivery behavior.**
- [x] **Step 3: Implement transactional outbox enqueueing and worker delivery handling.**
- [x] **Step 4: Run the focused webhook tests.**

### Task 5: API, MCP, and contextual view exposure

**Files:**
- Modify: `src/forecast_anything/api/routes.py`
- Modify: `src/forecast_anything/api/service.py`
- Modify: `src/forecast_anything/mcp_adapter/arguments.py`
- Modify: `src/forecast_anything/mcp_adapter/server.py`
- Modify: `src/forecast_anything/presentations.py`
- Modify: `apps/console/src/features/context/ContextView.tsx`
- Test: `tests/unit/test_mcp_tools.py`
- Test: `apps/console/src/features/context/ContextView.test.tsx`

**Interfaces:**
- Consumes: Tasks 1-4 typed API contracts and durable ledger methods.
- Produces: bounded inbox/source-subscription/webhook tools, question controls, and visible update history in the contextual question view.

- [x] **Step 1: Write failing MCP and view tests** for inbox reads, subscription controls, webhook configuration, and rendering muted/provisional/failed-delivery events.
- [x] **Step 2: Run the focused tests and confirm the expected missing behavior.**
- [x] **Step 3: Implement the typed routes/tools and question timeline.**
- [x] **Step 4: Regenerate console API types from the OpenAPI contract and run focused tests.**

### Task 6: Acceptance and final verification

**Files:**
- Modify: `docs/superpowers/plans/2026-11-08-phase-6-continuity-and-updates.md`
- Modify: `docs/research/phase-6a-continuity-contract.md` only if an accepted implementation correction requires an explicit addendum.
- Test: `tests/unit/test_continuity.py`
- Test: `tests/integration/test_worker.py`
- Test: `tests/integration/test_webhooks.py`

**Interfaces:**
- Consumes: completed Tasks 1-5 and pinned local Timestral runtime.
- Produces: reproducible deterministic and end-to-end acceptance evidence, plus a separate report of Timestral and Desktop observations.

- [x] **Step 1: Run deterministic contract scenarios, including append, corrections, insufficient origins, budget exhaustion, qualification loss, shared sources, retry, and crash recovery.**
- [x] **Step 2: Run the closed-assistant synthetic-source to local webhook recovery flow.**
- [x] **Step 3: Attempt real local Timestral inference and record either successful provenance or the explicit provider failure.**
- [x] **Step 4: Run the required Python/console suites and inspect generated contracts.**
- [ ] **Step 5: Review the complete diff from the approved 6A SHA and prepare the final checkpoint report without pushing.**

## Acceptance notes for review

- The 300-second requalification budget is enforced before and after each origin. An individual provider call cannot be interrupted by this Python deadline check, so one slow or hung call can exceed the nominal job budget. The accepted 6A contract calls this a hard timeout; this remains a contract gap for review.
- The closed-assistant acceptance used a separate MCP stdio process, worker process, synthetic CSV, and local HTTP webhook receiver. The same question ID and its new run reference were recovered after reconnect.
- The real Timestral parity test passed separately; it is not included in the offline full-suite count.
- Codex Desktop itself could not be inspected through the UI tool; no Desktop rendering observation is claimed.
