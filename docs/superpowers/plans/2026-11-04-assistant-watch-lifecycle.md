# Assistant Watch Lifecycle Implementation Plan

> Inline execution using `superpowers:executing-plans`; no subagents.

**Goal:** Expose durable recurring-question watch management and change explanations through MCP.

**Architecture:** Reuse the existing core watch policy, schedule, history and comparison logic. Add authenticated API reads for a single watch, paginated watch history and run-change summaries. Extend MCP with six strict typed tools and preserve the existing response and source-access bounds.

**Spec:** `docs/superpowers/specs/2026-11-04-assistant-watch-lifecycle-design.md`; release gate: `docs/first-release.md`.

## Global Constraints

- The API, worker and ledger remain the only owners of watch lifecycle and scheduling.
- The assistant cannot create an eligibility decision or promote a candidate by submitting a forecast.
- Watch creation is explicitly mutating and may later cause core-owned reads of its registered sources.
- Watch creation must verify every candidate source against the operator's current MCP source-ID allowlist before mutation.
- Use bounded pages, the existing MCP 64 KiB result cap, and sanitized errors.
- Add and run focused tests for this feature as part of the requested completion work; do not run the full suite without need.

## Task 1: API and durable history reads

**Files:** contracts, store, API service and routes, focused tests.

- [x] Add typed watch-history page contracts and paginated ledger read.
- [x] Add get-watch, history-page and watch-change API operations.
- [x] Add API tests for history pagination, comparable run summaries and lineage errors.

## Task 2: MCP watch journey

**Files:** MCP arguments/server, focused tests, MCP docs and release evidence.

- [x] Add six strict watch tools and honest mutation/open-world annotations.
- [x] Add HTTP delegation for create/list/read/update/history/summary using only existing core semantics.
- [x] Add typed-wire tests for schemas, bounds, exact request bodies and safe errors.
- [x] Document a complete assistant sequence: discover candidate, save watch, retrieve state/history, compare recorded runs.

## Task 3: Verification

- [x] Run focused API and MCP unit tests, Ruff lint/format and `git diff --check`.
- [x] Review release-gate language; direct desktop UI acceptance remains a separate open item because the available automation could not access the Codex Desktop app.

Verification: 218 MCP unit tests, focused API/MCP tests, five real-stdio journeys, four local-service process tests, and the installed-wheel MCP/liveness/recovery journey passed. Codex CLI exercised the forecast and watch sequence against a real local API/worker. Direct Codex Desktop UI acceptance is still pending.
