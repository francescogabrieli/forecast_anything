# Forecast Evidence Implementation Plan

> **For agentic workers:** use superpowers:subagent-driven-development sequentially, with task-scoped and final independent reviews. During implementation the owner asked for no commits or pushes; on 31 October 2026, after the independent final review and fix review, the owner authorized committing and pushing this verified increment. No public release or deployment is authorized.

**Goal:** deliver supported configurable forecasts and durable, availability-correct multi-origin comparisons through the existing core/API/MCP.

**Architecture:** extract normalized raw revisions before freeze; persist a frozen plan before inference; reuse Runtime/evaluate_run with a fixed model/baseline graph. The leased worker owns orchestration, stable child keys and immutable reports. MCP submits and reads bounded core contracts.

**Tech Stack:** existing Python/Pydantic/SQLite/FastAPI, optional MCP SDK; no new dependency or framework.

**Spec:** [forecast evidence design](../specs/2026-10-30-forecast-evidence-design.md), technical translation of approved MCP-first release step 2. Product criteria and this concrete plan were approved by the owner in chat on 30 October 2026.

## Global Constraints

- No public deployment, paid inference or model downloads. Commit and push are authorized only after final independent review and verification; public release remains out of scope.
- Preserve existing uncommitted MCP work and tests; use working-tree snapshots, including untracked files, for review.
- The core alone computes forecasts and scores. Baseline remains default; Timestral is opt-in under existing conditions.
- Backtests use one registered CSV source/series/unit on a regular UTC hourly/daily grid; configured forecasts may reuse existing validated CSV/HTTP snapshots without source I/O. No scenario, known-future input, imputation or multi-history scoring.
- Freeze source vintage, configurations, complete calendar and planned origin membership before any provider call.
- History must satisfy event_time <= nominal origin and available_at <= issuance time; issuance is nominal origin plus declared offset, strictly before the next target.
- Preserve supplied revisions; never reconstruct old vintages by refreezing a latest-only snapshot or guess availability dates.
- Existing 50/25/25 splits, horizon-sized strides and earliest N origins per partition; no automatic model selection or watch qualification.
- Bound horizon 1–366, baseline period 1–10000, origins per partition 1–50 (default10), raw archive <=100000 rows; keep missing interior calendar cells.
- Child emission keys ignore parent attempt; every progress/report write is fenced by the parent lease. No exactly-once physical inference claim.
- Aggregate matched cells only, preserve failure/exclusion denominators, and label insufficient evidence and zero-baseline ratios explicitly.
- Preserve source allowlists, sanitized errors, 1MiB upstream and 64KiB full MCP output bounds; report reads are bounded/paginated.

## Review Focus

1. Late revision or known-in-advance future row contaminates history/calendar: Task2 manual-value tests.
2. Missing interior timestamps silently move partitions/targets: Task2 full-grid exclusion tests.
3. Parent restart/new attempt rereads changed file or duplicates earlier runs: Task3 lease recovery test and Task5 real process journey.
4. Provider failure removes inconvenient origins or mismatches baseline: Task2 fixed-membership and weighted-score tests.
5. New source-reading tool bypasses operator permissions or exposes private locations: Task4 protocol tests and Task5 rejection journey.

## File map and interfaces

- `sources/profiling.py`: extract `read_observations(spec, *, secret_resolver=None, max_rows=None) -> tuple[Observation,...]`; retain ingest_source outputs exactly by freezing that reader’s results with existing assumptions.
- `contracts.py`: strict `ForecastSelection(provider, options, horizon, baseline_period)` and `BacktestSettings(max_origins_per_partition, origin_offset_seconds)` in Task1; typed job subclasses and JobRequest union in Task3.
- `backtesting/contracts.py`: `ObservationArchive`, `PlannedOrigin`, `BacktestPlan`, `OriginOutcome`, `PartitionScore`, `BacktestReport`, `OriginPage` (no private archive in public response).
- `backtesting/store.py`: `BacktestStore(ledger)` with immutable put/get_plan, put/get_origin, list_origins, put/get_report; mutation methods accept `lease_guard`.
- `migrations/008_backtests.sql`, `store.py:MIGRATIONS`: immutable plan/origin/report tables, preserving old ledgers.
- `backtesting/planning.py`: trusted graph construction and frozen plan preparation.
- `backtesting/runner.py`: execute/recover the plan and compute persisted reports.
- `backtesting/service.py`: core API submission validation, identity reuse and source-vintage binding.
- `worker.py`, `api/service.py`, `api/routes.py`: thin delegation and authenticated typed reads.
- `mcp_adapter/server.py`, `client.py`: four tools and fixed backtest read routes.
- Generated contracts in `contracts/v1`, `apps/console/src/api`, `apps/agent/src/schema.generated.ts`.
- Focused tests under `tests/unit/test_backtest_*.py`, `tests/integration/test_backtest_*.py`; new MCP/process and installed-artifact assertions; docs.

## Task 1 — Revision reader, strict contracts and immutable storage

**Own:** profiling extraction, core selection/settings contracts, backtesting contracts/store/package marker, migration008 and Ledger migration list; focused unit/store tests; generated schema/client changes needed for the new public contracts.

**Interfaces:** immutable plan contains backtest_id, content-addressed archive (normalized revision rows, capture time, source ID/revision), selection/settings, provider_contracts (dict of provider ID to frozen Capabilities), frequency, complete split calendar, planned origins, actuals snapshot identity, assumptions and protocol version. Origin outcomes include ordinal/partition/nominal+issuance time/target bounds/status/reason and optional run/evaluation references, never full forecast arrays. Report includes immutable identity, archive/plan references and per-partition counts/weighted scores. Public OriginPage uses offset/limit/next_offset.

- [x] Write failing reader tests retaining two revisions and bounded max_rows, comparing ordinary ingest_source snapshots byte-for-byte with prior behavior.
- [x] Write failing contracts/storage tests: invalid bounds, content identity conflicts, stable canonical serialization, duplicate writes, invalid/missing references, fenced writes and migration of an existing database.
- [x] Run focused tests and record expected RED.
- [x] Extract normalization once; do not duplicate parsing. Implement strict contracts and BacktestStore using Ledger transactions/lease guards. Archive JSON remains internal, without `exclude=True` destroying persistence.
- [x] Register migration008 and immutable/no-update/delete storage semantics. Ensure internal hashes/identities validate on read/write and typed errors omit source paths.
- [x] Regenerate core/console schemas and TypeScript clients; run focused tests, Ruff, generated checks and the Python suite once. Document any transitional failures precisely; do not hide them.
- [x] Leave changes unstaged and produce Task1 report for review.

## Task 2 — Frozen planning, trusted graphs and numerical runner

**Own:** planning.py, runner.py, a narrow typed Ledger.run_events reader over existing persisted run events, optional graph/snapshot lease forwarding in Runtime/Ledger, and focused numerical/recovery unit tests. Consume Task1 contracts/storage; no API/MCP edits.

**Interfaces:** `build_forecast_graph(source_id, snapshot, selection, frequency, *, graph_id) -> GraphSpec`; fixed nodes source/baseline/model, explicit parameters, unique metadata. `prepare_backtest(backtest_id, source_revision, observations, selection, settings, captured_at, *, provider_contracts) -> BacktestPlan` (pure, no inference). `execute_backtest(runtime, store, plan, *, lease_guard) -> BacktestReport` reuses existing origin outcomes, runs and evaluations. Stable child key: backtest identity plus planned ordinal, independent of attempt.

- [x] Write failing tests: late revision exact forecast values; future event available early excluded from history and calendar; complete grid retains a missing cell and refuses >100000 calendar instants before materialization; publication offset changes available history without moving targets; off-grid, multi-series/unit and invalid offsets rejected.
- [x] Write failing tests for frozen partitions/configuration before first provider call, earliest-N deterministic membership, provider failure retained in denominator, same-cell baseline matching, zero-baseline reason, count-weighted manual MAE and all-final-origins-insufficient status.
- [x] Write restart tests: resume partial immutable outcomes, existing child run before outcome publication, parent lease loss, provider revision changes on restart/actual result, repeated execution without duplicate runs/evaluations, source data never reread by runner. Use controlled providers, not real weights.
- [x] Run RED; implement pure planning and numerical orchestration with existing build_splits/freeze/Runtime/evaluate_run and same-source actuals. Nominal grid bounds use only rows visible and occurred by capture; missing cells never disappear.
- [x] Validate emitted calendars exactly, persist child runs/evaluations/outcomes with guard, and return existing immutable completed report on recovery. Do not classify lease loss as an origin exclusion or silently fallback providers.
- [x] Run focused tests, Ruff and the suite once; leave unstaged and report for review.

## Task 3 — Durable job submission, API and worker integration

**Own:** job DTOs/union in contracts.py, backtesting/service.py, thin API/service/routes and worker dispatch, API/worker tests and generated artifacts.

**Interfaces:** `ConfiguredRunJobRequest(kind='configured_run', key, source_id, snapshot_id, selection: ForecastSelection)`; `BacktestJobRequest(kind='backtest', key, source_id, selection: ForecastSelection, settings: BacktestSettings)`.

Configured submissions resolve the unique catalog vintage named by snapshot assumptions, build the deterministic graph and pass existing run/scenario/lineage validation. They perform no source file I/O. Backtest submissions bind current registered CSV revision into the durable payload; first worker execution captures raw observations and stores plan/actuals before inference. Existing get_job polls state. Completed report reads: GET `/v1/backtests/{backtest_id}`; origins: GET `/v1/backtests/{backtest_id}/origins?offset=0&limit=25` (1–50). Reads never mutate.

- [x] Write failing authenticated API tests for valid jobs, missing provider, invalid bounds, source revision mismatch, ambiguous snapshot lineage, assumed input rejection, pending report absence, immutable report reads and bounded origin pages.
- [x] Test identical backtest retries return the original job even after catalog/file changes; different body under the same key conflicts. Compare the original request to stored durable payload before fresh source/catalog work.
- [x] Test real leased worker capture-before-inference, kill/reclaim after partial origins, source changes after archive capture, stable child identities across attempts and recoverable report-before-job-ack.
- [x] Run RED; implement thin delegation. Do not enlarge existing runtime/worker with a second numerical loop or bypass existing validation/evidence rules.
- [x] Regenerate API/console schemas and both generated TypeScript clients. Run API/worker tests, Ruff, contract checks and full suite; leave unstaged and report.

## Task 4 — MCP tools and protocol boundaries

**Own:** server/client fixed routes and tool definitions, protocol unit tests and MCP guide/capability descriptions. Consume Task3 API; no core calculations.

**Interfaces:** `submit_configured_forecast(request: ConfiguredRunJobRequest) -> JobView`, `submit_backtest(request: BacktestJobRequest) -> JobView`, `get_backtest(backtest_id) -> BacktestReport`, `list_backtest_origins(backtest_id, offset=0, limit=25) -> OriginPage`. Use existing success/error envelopes and real SDK calls; submit adapters inject/validate the fixed job kind rather than expose arbitrary job execution.

- [x] Write failing protocol discovery/schema/delegation tests, source allowlist rejection before submit_backtest, stable keys, honest mutating/open-world annotations, pending/failed report handling, oversized results, ID encoding and sanitized field/value errors.
- [x] Run RED; implement four typed tools and only the two required fixed read route shapes. No private raw-archive endpoint or arbitrary HTTP request tool.
- [x] Run tool tests and CLI compatibility, Ruff and full suite once; update precise tool count/scope in guide and capability matrix. Leave unstaged and report.

## Task 5 — Release-path evidence and documentation

**Own:** real-process backtest/configured forecast integration test and installed-wheel extension; first-release readiness documentation and generated-client validation. No new product code except a separately reported concrete integration defect.

- [x] Write a failing SDK stdio → API → worker journey with a longer revision-bearing CSV, explicit selected baseline period vs comparator, multiple planned origins in each partition and manually checkable metrics.
- [x] Exercise disconnect/reconnect, interrupted worker after partial work, changed CSV after capture, stable report/run/evaluation identities, missing-target/revision exclusions, permissions and persisted per-origin evidence. Verify configured forecast horizon/options are honored separately from historical replay.
- [x] Extend the installed-wheel path outside checkout to run the supported public tools and inspect persisted report; ensure optional SDK skips remain explicit and baseline CLI still works without it.
- [x] Run focused acceptance tests, then full Python suite, Ruff/format, both generated API checks, console and agent typechecks/contracts checks, build and installed artifact verification. No paid calls or weights. Broaden testing only for concrete failures or touched behavior.
- [x] Update roadmap and usage/evidence docs with actual results and supported boundaries. Track remaining first-release blockers: managed installation, one desktop host, recurring-question lifecycle and assistant reports, public site, clean-install/release destinations.
- [x] Request independent whole-change review and fix material findings. The final review approved the three Important fixes; the Minor oversized-offset edge is recorded as deferred in the SDD ledger. Preserve evidence. The owner authorized committing and pushing the verified increment; no public release or deployment.

Task 4 and Task 5 evidence is recorded in `.superpowers/sdd/2026-10-30-forecast-evidence/task-4-report.md` and `task-5-report.md`. The build command was attempted: the Eve build remains blocked by the unavailable Docker daemon; it did not pass. The whole-change review ran; all three Important findings were fixed and independently re-reviewed. The Minor SQLite offset finding remains explicitly deferred.

## Self-review

Dependencies are sequential: frozen storage → runner → API/jobs → MCP → real installed journey. Task1 and3 share core contracts/generated files intentionally, with no concurrent implementers. Stable child keys and fixed membership cover recovery and selection bias; the complete-grid rule closes the builder check’s only material gap. Runtime single-history scoring remains binding. Installation and website are not silently added to this numerical increment.
