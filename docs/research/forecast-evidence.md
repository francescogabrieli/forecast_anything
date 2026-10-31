# Configured forecasts and frozen historical evidence

Local acceptance and independent review on 31 October 2026, following the [approved implementation plan](../superpowers/plans/2026-10-30-forecast-evidence.md). The increment is committed as `a9302c9` and pushed in [PR #13](https://github.com/francescogabrieli/forecast_anything/pull/13), stacked on the still-open frontend PR #12. No package, site or service has been published.

The 19-tool adapter submits configured forecasts and CSV backtests to the authenticated API and independent worker. The core computes results and persists immutable evidence. Generic backtests have no discovery attestation and do not qualify or activate watches. [Usage](../quickstart.md), [operating guide](../implementation/mcp.md), [remaining release gates](../first-release.md).

## Reproducible numerical fixture

The real SDK/stdin/stdout → API → worker journey uses 24 synthetic daily observations alternating 1 and 3. The selected `seasonal_naive` model explicitly uses period 2, horizon 2; the independent comparator uses period 1. Each complete two-target window therefore has selected errors `(0, 0)` and comparator errors `(2, 0)`, so MAE is 0 versus 1 and relative MAE is 0. These are manual calculation checks, not predictive-quality evidence.

The frozen 50/25/25 split selects the earliest two planned origins in each partition. Exploration retains an insufficient-history origin and one evaluated origin (two matched cells); selection and final each retain two evaluated origins (four matched cells each). The six planned origins remain in the report. A separate configured forecast uses horizon 3 and produces `[1, 3, 1]`, versus comparator `[3, 3, 3]`, on the three following UTC dates.

A supplied revision changes the first history cell from 1 to 9, published on day 10. The stored history for the early evaluated origin retains revision 1/value 1; later histories use revision 2/value 9. The tail pattern keeps the aggregate arithmetic simple. An event beyond capture, supplied as known early, remains in the internal archive but cannot extend the 24-day calendar or enter historical inputs.

The worker fixture pauses immediately after real persistence of origin 1. The test terminates that OS worker, replaces the CSV with invalid data, advances its controlled clock past the lease, and restarts both API and worker. Recovery uses the original archive, source vintage, capture time, plan, origin membership and child identities. The MCP process is disconnected during capture and partial execution. Reconnection retrieves exact persisted report/origin content and evaluation references, and original-body/key replay returns the same jobs and configured run. SQL counts verify no duplicate child runs/evaluations. The pause wraps the real persistence method in test support only; numerical providers, API, queue, storage and worker execution are production code.

A second real-process fixture delays publication of day 3 until day 4 and omits day 14. All six planned windows remain: unavailable historical revision yields `missing_history`; the target window containing day 14 yields `incomplete_actuals`; later incomplete histories remain excluded. Final status is `insufficient_evidence`, with no fabricated zero MAE or removed inconvenient origins.

## Installation, permissions and evidence boundaries

The same configured/recovery journey runs from a wheel installed in a fresh virtual environment outside the checkout, with locked optional SDK dependencies. Isolated imports prove the package/server/SDK resolve from that environment. It retains the original baseline installed-wheel journey and scans the wheel for credentials and weights. A separate baseline wheel-only release check runs the minimal CLI without the MCP extra. Missing-extra CLI behavior remains covered, and MCP-dependent test modules explicitly skip when the optional SDK is unavailable.

A newly connected MCP process without a source-ID grant can use the stored configured snapshot but cannot submit source-reading backtests. Allowed reconnection can replay the original backtest. Pending report/pages return `not_found`; reads use the job state and bounded pagination. Per-origin run, history snapshot and single-run evaluation identities remain inspectable through public tools. Internal plan/archive reads in the test are local SQL verification, not new public tools.

Scope remains one CSV source/series/unit on fixed UTC hourly/daily grids, supplied availability/revisions, no imputation/scenarios/multi-history scoring, bounded archive/calendar and bounded tool output. Configured forecasts also support validated stored HTTP vintages without source I/O. Timestral remains separately opt-in; this acceptance uses only seasonal-naive, no paid inference or weight downloads.

## Verification

| Check | Result |
| --- | --- |
| Full Python suite after final review fixes | 819 passed, 1 skipped, 38.65 seconds |
| Focused final-fix Python suite | 465 passed, 30.41 seconds |
| Checkout and installed-wheel MCP process tests | 6 passed, 16.36 seconds |
| Console component suite | 82 passed |
| Agent unit suite | 29 passed |
| Existing browser journeys, real API and worker | 2 passed, 8.3 seconds |
| Ruff, format, generated core/console contracts, console/agent generated types and typechecks | Passed |
| Console build; Python wheel and source-distribution build | Passed |
| Installed baseline release check, outside checkout | Passed; no embedded credentials or weights |
| Agent `eve build` | Blocked: local Docker daemon unavailable, including after sandbox escalation |

The single skip is the guarded real Timestral check. Node emitted its existing `NO_COLOR`/`FORCE_COLOR` warning during browser runs.

## Final review and remaining release work

The independent whole-change review's three Important findings were fixed and re-reviewed: extreme finite metric calculations preserve representable means and give explicit results for unrepresentable scores/ratios; HTTP/SSE/MCP/job status redact private provider diagnostics; and concurrent identical submissions return the accepted original job. A valid but extremely large origin-page offset beyond SQLite's signed 64-bit range remains a deferred minor edge.

The complete first-release journey remains open: managed installed service setup/status/stop/recovery; one actual desktop assistant host; recurring-question selection and lifecycle; assistant summaries/reports tied to stored evidence; a public site and guided onboarding; clean-install checks on declared platforms and approved release destinations. Generic report-to-discovery policy integration also remains future work. External usability and general forecasting quality are unvalidated.
