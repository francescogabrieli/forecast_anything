# Phase 4: browser contextual views

Base: `315b75e439a2ec9ecf268039f9bc4c6961d97e03` (contains phase 3 approved commit `a4713698bcf0418bd5a252cf2539e0b46efa5c79`). The phase 4 branch is `codex/phase-4-contextual-views`. Work remains local for review; no push or phase 5 work is implied.

## Behavior and contracts

Migration 012 assigns each ledger a durable random workspace identity. Authenticated `GET /v1/workspace` returns it. The read-only MCP tool `get_browser_link` takes `kind` (`run`, `question`, or `report`), the exact `resource_id`, and a loopback `browser_url` such as `http://127.0.0.1:4173`. It checks the requested record and returns a link of the form `/#/w/<workspace-id>/<kind>/<id>`. The URL has no token. Report links identify the stored report, not merely its backtest job; new authenticated report presentation and origin endpoints resolve that exact report ID. Question references to backtest jobs use a separate backtest route.

A fresh tab shows the connection form in place without changing the link. The browser verifies authentication, workspace identity and health before rendering. A token is retained in tab-scoped `sessionStorage` for reload and removed on failed restoration; it is not placed in URLs, browser history, server access paths, or MCP results. This is a browser-session mechanism, not an OS credential vault: scripts running in the console origin and browser extensions with access may read it. Closing the tab ends the session. A link for another workspace refuses to render until connected to that workspace. The workspace screen distinguishes API/authentication, worker state, model readiness and the model loaded by the worker. These diagnostics are the values observed during the most recent successful connection, not a live monitor.

Compact views omit the sidebar; `/full` opens the extended shell. Forecasts show primary points and baseline values only when series, timestamp and unit align; missing or incompatible values and truncation are explicit. Run provenance, model assumptions and Future Graph use existing contracts. Historical report views show partition scores, excluded origins, an accessible table corresponding to the error plot, and paged origin records. Question views expose revision-bound historical references. The advanced console lists and renames saved questions, retains source/watch and evidence management, reads the actual registered source mapping, and previews scenario changes before submission; the full JSON remains available in advanced options. A source with an operator-configured secret reference is read-only in this editor so the reference cannot be accidentally removed. The configuration endpoint is authenticated and is not exposed through the MCP adapter.

Completion events announce new results without changing the run being inspected. No MCP Apps rendering, public site, qualification policy changes or proactive notifications were added.

## Reproduction

Install the repository's Python development and MCP extras and the console and agent npm dependencies. From the repository root:

```sh
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest -q
.venv/bin/python scripts/export_contracts.py contracts/v1 --check
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
(cd apps/agent && npm run contracts:check && npm run typecheck && npm test -- --run)
(cd apps/console && npm run check:types && npm run typecheck && npm test -- --run && npm run build)
(cd apps/console && CI=1 npm run test:e2e)
```

The Playwright fixture starts independent temporary local ledgers and real FastAPI/worker processes on ports 8000 and 8001, plus a built console on 4173. It uses synthetic daily data and the deterministic seasonal-naive provider; it does not establish Timestral quality or a new real Timestral inference. Its test-only credential is `local-e2e-token` and never enters the generated links.

The browser tests connect from an empty session to the exact linked run, reload, submit a second real queued run while viewing the first, and verify the notice and unchanged selection. They also exercise a missing record, invalid credentials, saved question and report, back/forward navigation, mobile viewport and keyboard focus, the advanced scenario review and immutable original run. The separate workspace test checks mismatched identities and a delayed rejected connection after a later successful connection. The MCP SDK stdio integration test requests actual run and question links against a live API, confirms the workspace ID and checks that the token is absent. The report lookup and exact report ID are exercised through API integration and browser tests. These automated observations are distinct from a manually observed Codex Desktop run; no new Desktop/MCP Apps rendering claim is made.

## Evidence and limitations

- Full Python suite: 946 passed, 2 skipped; the subsequently extended MCP stdio test and source-configuration regression passed separately.
- Console: 94 tests passed, TypeScript typecheck, generated type check and production build passed.
- Agent: 29 tests passed, generated contract check and TypeScript typecheck passed.
- Playwright: four real API/worker flows passed; the optional Timestral browser test was skipped because the real-model fixture was not enabled. The separate two-workspace and delayed-response test also passed.
- Ruff, formatting, generated core contracts and diff whitespace checks passed.

The scenario preview reports changed observations by position and retains the full proposed snapshot for inspection; the core remains responsible for validating the submitted snapshot and scenario. Existing historical evidence is not requalified. Authentication and service diagnostics are rechecked on reload/reconnection; an already open page does not poll diagnostics continuously. Forecast and backtest figures represent recorded data, not proof of forecast accuracy.
