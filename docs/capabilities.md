# Capability matrix

This matrix describes the code in the release-candidate checkout. It is not a claim of production readiness, a published service, or general forecasting-quality acceptance. The [roadmap](roadmap.md) includes future work; the [quickstart](quickstart.md) identifies supported installation paths.

| Area | Implemented | Boundary or pending acceptance |
| --- | --- | --- |
| Source connectors | Explicitly mapped local CSV and bounded HTTP JSON GET | No generic database, spreadsheet, arbitrary API, pagination or streaming connector. HTTP secrets require an injected resolver. |
| Source interpretation | Sanitized sample of at most 100 rows, field types, proposed roles, unresolved semantics | Suggestions do not become executable mappings automatically. Availability time, identity, revision, unit, cadence, timezone, Gregorian calendar and missing sentinels must be explicit. |
| Temporal snapshots | Availability-aware freeze, revision handling, immutable snapshot identity | No inference of original publication dates; declared availability assumptions remain assumptions. |
| Future Graph | Typed acyclic graph validation, explicit provider/operator registries and representation negotiation | No implicit resampling, calendar alignment, unit conversion or stochastic coupling. |
| Baseline comparator | Product reference only; explicit library fixtures also support seasonal repetition with explicit positive period; point results on fixed UTC hourly/daily grids | Rejects missing history and known-future inputs; no imputation, quantiles, joint paths or calibrated probabilities. |
| Timestral engine | Default pinned local model; point and marginal-quantile output | Explicit `model prepare` provisions pinned code and verifies weights. No Mistral API key or silent fallback; metadata reads do not load Torch. Real CPU fp32 parity and a local comparison across three domains was completed; weight license remains applicable to each user's own deployment. No joint paths. |
| Sum and balance | `sum_aligned` and `cumulative_balance` preserve compatible point/joint-path representations | Identical ordered series, timestamps and units required; balance inputs are per-step quantities. Marginal quantiles are not added or converted to paths. |
| Window event | `any_exceed` computes a strict threshold event over complete joint paths | Requires shared sample identity/count. Returns an empirical probability without calibration or confidence-interval claims; point-only inputs cannot supply it. |
| Residual trajectories | Experimental shared-origin sampling of complete residual panels through `ResidualPanelSampler` | Preserves temporal/cross-series sample identity and availability boundaries. The frozen experiment passed no domain's positive lower Brier-skill bound; no calibrated probability acceptance. See [experiment](research/joint-paths.md). |
| Evaluation | Recorded forecast/actual comparisons and split/evidence contracts | Assumed outcomes cannot count as observed evidence; API scoring with multiple history-source bindings remains unsupported. Benchmark fixtures do not establish general predictive superiority. |
| Discovery | Deterministic `expected_deviation`, `forecast_change` and `declared_limit` templates, with pinned Timestral context for product epochs and candidates | Forecasts alone do not promote candidates. Unknown agent templates stay non-executable. |
| macOS setup | Installed CLI prepares a private workspace, loads Timestral, manages a per-workspace LaunchAgent and registers a Codex MCP entry | `doctor` and `get_diagnostics` report reachability, authentication, worker/model state, permissions and version. See [installation and maintenance](installation.md). |
| Ledger and jobs | Local SQLite immutable runs/evaluations, durable cursors, leased job queue and recovery | Local SQLite and one worker per workspace. Legacy runs and reports remain readable. Queued baseline-primary work fails with `required_provider_migration`; incompatible watches pause with the same reason. |
| API | Bearer authentication, typed job submission, immutable reads, source profiles, replayable SSE and scenarios | Local workspace trust model, not tenant isolation. `/health` is public; optional agent operations use a separate token. |
| MCP distribution | Local stdio adapter with typed tools for CSV registration/refresh, forecasts, bounded backtests, watches, durable questions and operations, compact snapshot reads, shared result presentations, immutable evidence and evaluation | Official Python `mcp==2.3.0` client covers protocol/schema/HTTP boundaries, real API/worker journeys, question/revision persistence, operation recovery after reconnect, and the 320-row CSV path. Earlier installed-wheel, CLI and Desktop evidence remains recorded separately. Source-ID grants remain required for source-reading operations; configured forecasts reuse stored vintages without source I/O. Numerical providers may use configured external resources. Full serialized tool results remain bounded to 64 KiB and upstream requests/responses to 1 MiB. MCP HTTP registration remains open. Generic backtests do not qualify watches; candidate-bound backtests use fresh final windows. See the [MCP guide](implementation/mcp.md). |
| Console | Guided source interpretation, explicit provisional first forecast and source refresh, graph/run views, discovery/event feed and scenario comparison | Renders recorded representations; it does not invent bands for point results. |
| Public site and release demo | Static site, installation path, assistant-first product overview and a checked-in synthetic CSV journey with a local Timestral forecast, historical baseline comparison, saved question and disconnected worker update | Local review artifacts only; no site is published. Synthetic backtest scores are arithmetic and persistence evidence, not forecast-accuracy acceptance. See [demo reproduction](release-demo.md). |

## Compatibility and acceptance matrix

| Surface | Observed behavior | Boundary |
| --- | --- | --- |
| Official Python MCP SDK `2.3.0` over stdio | Typed tool calls, real loopback API/worker, Timestral forecast and baseline comparison, durable reconnect and worker/webhook evidence | SDK execution proves the protocol and product path; it is not an MCP Apps rendering host. Synthetic inputs do not establish general accuracy. |
| Local browser | Chrome opened the exact saved-question route from the external wheel install; the public site was checked at 320, 390, 768 and 1440 px, with keyboard focus and a complete no-JavaScript fallback | Requires the local API/console or static preview process. A browser check does not prove assistant-host rendering. |
| MCP Apps reference host | Embedded run, question and report views and browser-link relay were observed in the official `basic-host` | That host test used a synthetic seasonal baseline; it does not imply Codex Desktop renders the same view. |
| Codex Desktop | Existing tool text, stored-result reads and reconnect are covered by earlier Desktop records | Embedded MCP Apps rendering remains to be verified in Codex Desktop. |
| Worker restart and inference interruption | The isolated supervisor test verified worker restart using simulated processes | Killing the operating-system process during one real in-flight Timestral inference remains unverified. A simulated restart is not evidence of that interruption. |

## Demonstrations and evidence

The current minimal CLI example uses synthetic observations and pinned local Timestral. It requires prepared weights. Earlier baseline CLI evidence and deterministic library fixtures remain historical examples of execution and persistence.

The site links to a [reproducible assistant journey](release-demo.md): synthetic CSV preview and confirmation, genuine pinned Timestral forecast, candidate-bound historical comparison, durable question/watch, appended observation and worker update while MCP is disconnected. The fixture, assumptions, exact command, output record and model/fixture provenance are checked in. It preserves provisional watch state and reason when present, and does not use synthetic scores as general accuracy evidence.

The MCP subprocess fixture uses the official SDK reference client and a real API plus an independent worker. An accepted forecast completes after MCP disconnects; the original key returns the same job/run after reconnection. Later observed outcomes refresh the original registered source and yield persisted single-run metrics. The configured/backtest journey compares a period-2 alternating series with a period-1 comparator: manual MAE 0 versus 1, two selected origins in each frozen partition, with one early insufficient-history exclusion. It terminates the worker after partial persistence, corrupts the CSV, restarts API/worker, and verifies unchanged archive/plan, child identities, paginated origins and report. A second process fixture retains missing-target and unavailable-history exclusions. An installed-wheel test repeats both baseline and configured/backtest recovery journeys outside the checkout with locked dependencies and the optional extra. These are fixed-clock synthetic tests, without an LLM, desktop assistant host or general predictive-quality claim.

MCP source profiling is mutating: the existing core route may enqueue durable template discovery, whose worker persists snapshots, epochs, candidates and graphs. Profiling has no caller-key replay guarantee. Profile/refresh of explicitly operator-allowed stored HTTP sources may cause core network access; both advertise an open world. The two new submission tools also advertise mutation and an open world: backtests capture an operator-allowed CSV source, while configured forecasts reuse a stored CSV or HTTP snapshot without source I/O; selected numerical providers may use configured external resources. Completed summary/origin reads are immutable and do not enqueue work. An unpublished report returns `not_found`; inspect pending/failed state through `get_job`. Backtesting initially supports one series/unit on fixed UTC hourly/daily grids and preserves only revisions supplied at capture, with explicit exclusions and insufficient evidence. These tests establish no predictive-quality claim. Generic backtest evaluations have no discovery attestation and cannot qualify or activate watches; candidate-bound Timestral backtests qualify only their frozen candidate with fresh final windows. MCP exposes no arbitrary network request tool, HTTP registration tool or private archive/plan reader.

The browser E2E fixture starts the real API and a worker with a fixed clock, synthetic CSV sources and seasonal-naive provider. Two journeys cover source activation, explicit first forecast and refresh, two-source evaluation, revision notification, graph keyboard interaction, a disrupted/reconnected event stream and an immutable scenario comparison. Its fixed local token is test-only. It neither measures model quality nor validates a paid provider.


The real Timestral parity, installed-model and browser checks are explicitly guarded; a separate genuine-model acceptance was executed. A CPU fp32 parity check and local cross-domain benchmark were completed separately; a skipped routine test, adapter unit test or dependency install does not reproduce those results. See [Timestral status](implementation/timestral.md), [the pinned benchmark evidence](research/timestral-benchmark/report.json), [runtime decision](decisions/agent-runtime.md), [operator semantics](implementation/operators.md) and [API contracts](implementation/api.md) for the detailed boundaries.

## Extension contracts

`ForecastProvider` declares `capabilities() -> Capabilities` and `forecast(request: ForecastRequest) -> ForecastResult`. Runtime registration is explicit. The result identifies the actual provider/revision and carries its available numerical representations and assumptions.

`Operator` declares `contract() -> OperatorContract` and `apply(inputs: dict[str, NodeValue], config: dict) -> ForecastResult`. Representation negotiation describes guarantees, not a representation that an input might happen to return. Paths must preserve the same sampled-world identity across inputs.

`SourceSpec` identifies a `csv` or `http_json` source, private location, optional private `secret_ref`, explicit mapping and positive refresh interval. See the [connector guide](connectors.md); adding a source kind requires a deliberate contract change rather than a parallel example-only format.

## Provider selection

Configured forecasts can choose the primary provider from comparable held-out backtests. The saved run records the decision and report IDs. See the [MCP guide](implementation/mcp.md#choose-a-provider-using-backtest-evidence).

## Default-model verification

| Boundary | Required provider check |
| --- | --- |
| CLI | The production runtime loads pinned Timestral and validates the primary forecast ancestry. Inference distinguishes `model_not_prepared`, `missing_model_dependency`, `model_code_revision_mismatch` and `model_load_failed`. See `model status` and `model prepare`. |
| API and MCP | Authenticated capabilities describe the required provider and inspected model status. Forecast/backtest requests go through the same core policy; the adapter delegates computation. |
| Discovery and watch | Product epochs and candidate graphs include the required model context. Incompatible historical watches are paused with an explicit reason. |
| Backtest and worker | Plans pin the model and comparator separately. The worker rechecks compatibility before work and preserves prior evidence. |

Verification with pinned Timestral covered SDK stdio, candidate-bound backtests, source refresh, browser reads and installation from a wheel. The Desktop baseline workflow separately covered text reports and reconnect after reopening Codex. Embedded Desktop rendering remains unverified.
