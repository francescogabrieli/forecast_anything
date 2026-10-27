# Capability matrix

This matrix describes the code in the release-candidate checkout. It is not a claim of production readiness, a published service, or acceptance of optional model providers. The [roadmap](roadmap.md) includes future work; the [quickstart](quickstart.md) identifies supported installation paths.

| Area | Implemented | Boundary or pending acceptance |
| --- | --- | --- |
| Source connectors | Explicitly mapped local CSV and bounded HTTP JSON GET | No generic database, spreadsheet, arbitrary API, pagination or streaming connector. HTTP secrets require an injected resolver. |
| Source interpretation | Sanitized sample of at most 100 rows, field types, proposed roles, unresolved semantics | Suggestions do not become executable mappings automatically. Availability time, identity, revision, unit, cadence, timezone, Gregorian calendar and missing sentinels must be explicit. |
| Temporal snapshots | Availability-aware freeze, revision handling, immutable snapshot identity | No inference of original publication dates; declared availability assumptions remain assumptions. |
| Future Graph | Typed acyclic graph validation, explicit provider/operator registries and representation negotiation | No implicit resampling, calendar alignment, unit conversion or stochastic coupling. |
| Baseline provider | Seasonal repetition with explicit positive period; point results on fixed UTC hourly/daily grids | Rejects missing history and known-future inputs; no imputation, quantiles, joint paths or calibrated probabilities. |
| Timestral adapter | Optional pinned library integration; point and marginal-quantile output | Not registered by default. Opt-in registration requires `FORECAST_ANYTHING_TIMESTRAL_ENABLED=1` plus pinned code, checkpoint and weight revisions; enabling it does not load weights. Real CPU fp32 parity and one owner-authorized local benchmark passed; weight license remains applicable to each user's own deployment. No joint paths. |
| Sum and balance | `sum_aligned` and `cumulative_balance` preserve compatible point/joint-path representations | Identical ordered series, timestamps and units required; balance inputs are per-step quantities. Marginal quantiles are not added or converted to paths. |
| Window event | `any_exceed` computes a strict threshold event over complete joint paths | Requires shared sample identity/count. Returns an empirical probability without calibration or confidence-interval claims; point-only inputs cannot supply it. |
| Residual trajectories | Experimental shared-origin sampling of complete residual panels through `ResidualPanelSampler` | Preserves temporal/cross-series sample identity and availability boundaries. The frozen experiment passed no domain's positive lower Brier-skill bound; no calibrated probability acceptance. See [experiment](research/joint-paths.md). |
| Evaluation | Recorded forecast/actual comparisons and split/evidence contracts | Assumed outcomes cannot count as observed evidence; API scoring with multiple history-source bindings remains unsupported. Benchmark fixtures do not establish general predictive superiority. |
| Discovery | Deterministic `expected_deviation`, `forecast_change` and `declared_limit` templates; provisional candidates and evidence-gated watches | Ambiguity is retained; forecasts alone do not promote candidates. Unknown agent templates stay non-executable. |
| Ledger and jobs | Local SQLite immutable runs/evaluations, durable cursors, leased job queue and recovery | One worker per workspace; local disk required. No multi-host coordination or distributed database claim. |
| API | Bearer authentication, typed job submission, immutable reads, source profiles, replayable SSE and scenarios | Local workspace trust model, not tenant isolation. `/health` is public; optional agent operations use a separate token. |
| Console | Guided source interpretation, explicit provisional first forecast and source refresh, graph/run views, discovery/event feed and scenario comparison | Renders recorded representations; it does not invent bands for point results. External usability testing is on hold by owner decision on 2026-10-27 and remains unvalidated. |
| Agent | Optional Eve bridge, persistent core tool budgets, Postgres metadata/session state and egress controls | A bounded GPT-6 Luna smoke on 2026-10-26 produced one `inspect_source` tool call against synthetic local data and confirmed the persisted core operation ID. This validates the basic live provider path only, not model quality, full autonomous discovery, or production readiness. Paid calls require configured credentials and explicit approval. |

## Demonstrations and evidence

The minimal CLI example uses synthetic observations and the actual seasonal-naive provider. It runs without a language model or downloaded weights. Deterministic template discovery also runs without an LLM; calling this an autonomous live-model demonstration would overstate it.

The browser E2E fixture starts the real API and a worker with a fixed clock, synthetic CSV sources and seasonal-naive provider. Two journeys cover source activation, explicit first forecast and refresh, two-source evaluation, revision notification, graph keyboard interaction, a disrupted/reconnected event stream and an immutable scenario comparison. Its fixed local token is test-only. It neither measures model quality nor validates a paid provider. The five-person usability study is on hold; these automated journeys do not establish external usability acceptance.

The agent tests use scripted responses. The Docker restart check interrupts a real Eve turn after a budgeted core operation and resumes the same session; the isolated fixture simulates expiry of Graphile Worker's four-hour stale-job lock. A separate bounded live GPT-6 Luna smoke sent one 3,132-byte request (maximum 128 output tokens), received a function call for `inspect_source` (518 input and 23 output tokens), and confirmed its persisted operation ID in the local core. It used only synthetic data and does not evaluate model quality or production readiness.

The real Timestral test is guarded and normally skipped. An owner-authorized CPU fp32 parity run and local cross-domain benchmark were completed separately; a skipped routine test, adapter unit test or dependency install does not reproduce those results. See [Timestral status](implementation/timestral.md), [the pinned benchmark evidence](research/timestral-benchmark/report.json), [agent decisions](decisions/agent-runtime.md), [operator semantics](implementation/operators.md) and [API contracts](implementation/api.md) for the detailed boundaries.

## Extension contracts

`ForecastProvider` declares `capabilities() -> Capabilities` and `forecast(request: ForecastRequest) -> ForecastResult`. Runtime registration is explicit. The result identifies the actual provider/revision and carries its available numerical representations and assumptions.

`Operator` declares `contract() -> OperatorContract` and `apply(inputs: dict[str, NodeValue], config: dict) -> ForecastResult`. Representation negotiation describes guarantees, not a representation that an input might happen to return. Paths must preserve the same sampled-world identity across inputs.

`SourceSpec` identifies a `csv` or `http_json` source, private location, optional private `secret_ref`, explicit mapping and positive refresh interval. See the [connector guide](connectors.md); adding a source kind requires a deliberate contract change rather than a parallel example-only format.
