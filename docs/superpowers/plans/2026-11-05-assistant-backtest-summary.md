# Assistant Backtest Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give MCP assistants a concise, evidence-linked backtest summary and final-origin chart data.

**Architecture:** Add a deterministic presentation projection in the MCP adapter. It reads the existing report and paginated origin records from the loopback API, optionally reads one watch, and returns a bounded typed summary without changing the core API or ledger.

**Tech Stack:** Python, Pydantic, MCP adapter, existing loopback API.

**Spec:** [2026-11-05-assistant-backtest-summary-design.md](../specs/2026-11-05-assistant-backtest-summary-design.md)

## Global Constraints

- `summarize_backtest` is read-only and performs no source reads or provider inference.
- Values, scores, and reason codes come only from the immutable report, persisted origins, and current watch.
- A watch decision is linked only when its `backtest_id` equals the requested report ID.
- `relative_mae` below 1 means lower model MAE than baseline on the reported matched cells; it does not establish future accuracy or statistical significance.
- The full MCP response remains subject to the 64 KiB result limit.
- No API contract changes or new dependencies.
- No commit or push.

## Review Focus

- Pending/missing reports: preserve the API's safe `not_found` behavior and do not return an empty successful summary.
- More than one origins page: collect all final outcomes, sorted by ordinal, while respecting the 50-row page limit.
- Zero baseline or no matched cells: preserve `relative_mae_reason` and report comparison as unavailable.
- Generic report plus `watch_id`: show current watch state but mark it unlinked unless its decision names this report.
- Large/long identifiers: rely on the existing complete-result size guard and avoid duplicating raw report/origin payloads.

---

### Task 1: Typed presentation projection

**Files:**
- Create: `src/forecast_anything/mcp_adapter/summaries.py`

**Interfaces:**
- Consumes: `BacktestReport`, `OriginOutcome`, and optional `WatchView` values validated from API responses.
- Produces: `BacktestSummary` and `summarize_backtest_records(report, origins, watch=None) -> BacktestSummary`.

- [x] Define summary contracts for report metadata, the three stored partition scores, final-origin chart points, explicit metric meaning, assumptions, and optional watch status/linkage.
- [x] Derive `final_comparison` from the stored final model/baseline MAE; preserve unavailable reasons and never infer significance.
- [x] Sort final chart points by origin ordinal and retain status, scores, evaluation ID, and failure/exclusion reason as recorded.

### Task 2: MCP read path

**Files:**
- Modify: `src/forecast_anything/mcp_adapter/arguments.py`
- Modify: `src/forecast_anything/mcp_adapter/server.py`

**Interfaces:**
- Consumes: `BacktestSummary`, `BacktestReport`, `OriginPage`, and optional `WatchView`.
- Produces: MCP tool `summarize_backtest` with required `backtest_id` and optional `watch_id`.

- [x] Add strict tool arguments and a read-only tool description explaining its stored evidence, MAE ratio, and forecast limits.
- [x] Fetch the report and all origin pages through the existing loopback API; fetch a watch only when requested.
- [x] Route the validated records through the projection and return the standard bounded success/error envelope.

### Task 3: Assistant guidance

**Files:**
- Modify: `docs/quickstart.md`
- Modify: `docs/implementation/mcp.md`

- [x] Document a submit → poll → summarize sequence and explain how to inspect point forecasts, evaluation evidence, watch linkage, and chart points.
- [x] State that `relative_mae < 1` compares the stored matched cells only and does not claim general accuracy.

### Task 4: Verification

- [x] Run Python static checks, formatting, `git diff --check`, and MCP schema/type checks without changing generated API contracts.
- [x] In an isolated temporary workspace, read a completed backtest through the new MCP tool and confirm it matches the persisted report, origins, and optional watch linkage.

Manual verification on 5 November 2026 used temporary SQLite/CSV state: the MCP SDK call returned a summary whose report ID and final points matched the persisted report/origin rows; a separate typed MCP call confirmed that watch reasons and operational status are shown only when the decision references the requested backtest. Ruff, formatting, contract export check, console type snapshot/typecheck, and `git diff --check` all passed. A fresh wheel/sdist build succeeded; the installed wheel imported `mcp_adapter.summaries` from its isolated target and exposed the new tool. No automated test suite was run.
