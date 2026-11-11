# Core implementation — 25 October 2026

Branch: `feat/future-graph-core`. Base: `b7b6bed`. Integration pending.

## Implemented

- Pydantic contracts reject naive timestamps, nonfinite values and incompatible output dimensions; operational extras are forbidden.
- `freeze` selects only available revisions, normalizes absolute instants to UTC and hashes canonical snapshot content.
- `compile_graph` checks DAG structure, explicit source metadata, dependency semantics and trusted provider/operator capabilities before inference.
- SQLite stores immutable snapshots, graph revisions and run records. Terminal runs and durable cursor-based events commit atomically.
- Runtime executes registered providers/operators, retains provenance and failures, and returns existing runs on sequential retries.
- CSV connector and installed `forecast-anything run/show` commands execute the minimal example without Torch or an LLM.

## API additions made during integration

`ForecastConfig.options` and `ForecastRequest.options` are optional dictionaries, default `{}`. Providers validate their supported options. Baseline `options.period` overrides its constructor default and is preserved in assumptions.

`Ledger.get_run_by_key(key: str) -> RunRecord | None` permits retry lookup before inference.

`graph.parse_node_config` reuses registered public source/forecast/operator schemas. Source config declares `source_id`, `series_ids`, `units`, and `frequency`. Forecast config declares provider, history, horizon, frequency and per-input relation_type; known_future is optional. Operator parameters may contain explicit complete `bindings` from role to upstream node. Runtime passes role-keyed inputs and remaining parameters to `Operator.apply`, retaining the original graph.

## Verification

All six tasks used RED/GREEN tests and independent reviews. Review fixes covered nested nonfinite opaque values, provider/operator DST-fold result timestamps, and malformed CSV headers. Final review fixed capability/result-field vocabulary divergence. Current full-suite evidence: `uv run pytest -q` — 134 tests passed. Regression coverage exercises canonical names, legacy aliases, and joint-sample alignment failures.

An installed wheel was imported from site-packages outside the source checkout. The actual CLI run/show/retry completed, returned seasonal_naive `[[20,30,20]]`, and persisted four events. The runtime imported without ML/LLM modules. The wheel check preceded the final representation fix; the full suite and independent fix review cover that change.

## Representation capabilities

Registered capabilities and operator requirements use `point`, `marginal_quantiles`, and `joint_paths`. They map explicitly to `ForecastResult.point`, `.quantiles`, and `.paths`; result field names remain unchanged. Historical registration aliases `quantiles` and `paths` normalize to the canonical capability names. Registration models expose canonical names in serialized output and schema, and compiler/runtime revalidate registrations to cover mutable models and `model_copy` adapters.

Marginal quantiles never imply joint paths. Every joint-path operator input must provide paths; inputs must share timestamps, sample group ID, and sample count. Canonical and alias registrations follow the same checks. Generic transforms still propagate only their required capability.

## Current capability limits

- CLI: one explicitly bound CSV source, seasonal_naive only; no CLI builtin operators yet.
- Library: registered provider/operator protocols and multiple explicitly bound snapshots. Generic transform capability propagation is conservative until plan 02.
- Hour/day integer UTC calendars only; no implicit resampling, unit conversion or missing-value imputation.
- Baseline emits points only. Timestral, event probabilities and scientific evidence evaluation are not implemented in this milestone.
- SQLite WAL requires local disk. Concurrent first invocations may duplicate inference; one durable result publishes. Durable execution leases are plan A4.
- Code license and public name remain decisions before public release; private repository remains private.

## Rulings made during execution

- Task-brief script only recognizes numeric task headings; extract C1–C6 verbatim into numbered briefs with the shared contract preamble — preserve approved requirements — costs only local tooling adaptation.
- JSON schema v1 is exported through standard Pydantic model_json_schema; do not invent mandatory wire fields absent from approved type table — compatibility — future versioning may require an envelope.
- Keep source Node.config opaque until C3 schema validation; contracts reject extra top-level operational fields — config extensibility remains intentional — C3 must enforce executable semantics.
- C3 source config declares source_id, series_ids, units and frequency; forecast explicitly binds history/known_future, provider and horizon; operator parameters stay inside registered config — eliminate implicit semantic inference — costs more explicit configuration before agent mapping exists.
- Executable relation types are accounting/physical/statistical; candidate and unsupported causal relations are rejected — preserve approved graph semantics — future causal models require an explicit extension.
- Legacy transforms conservatively propagate their registered required representation. M2 adds explicit accepted representations and preserving/fixed output semantics; see [typed composition and events](operators.md). Compilation exposes only guarantees common to every input.
- Add Ledger.get_run_by_key(key) -> RunRecord | None alongside planned API — runtime must retrieve an issued result before repeating inference on retry — minimal public helper; compatibility cost is one additional method.
- Add optional options={} to ForecastConfig and ForecastRequest; runtime passes it unchanged and baseline validates period — honor C6 node-owned period without baseline-specific runtime logic — additive wire schema field, future providers must reject unsupported options.
- Runtime removes parameters.bindings before Operator.apply, maps explicit complete one-to-one roles to upstream nodes, otherwise keeps node-ID keys; original graph remains persisted — bridge generic graph and operator parameter contracts — future shared-input role aliases require extension.
- Baseline calendar advances in fixed UTC steps after the aligned observed grid; runtime requires snapshot.as_of equal run origin and declared/actual source metadata agreement — no implicit resampling or fabricated alignment — stale histories remain distinguishable from future observations and need later freshness policy.


## Evaluation scoring versions

New evaluations use NumPy scoring (`evaluation=v2`). Observed values, point forecasts and quantile matrices must be finite and aligned to the same series and target dates. Scoring uses scaled floating-point arithmetic when a direct difference or sum would overflow. A score outside the representable range is reported as `numerical_score_unrepresentable`.

The evaluation record includes its scoring version in its assumptions. New backtests pin the scorer when accepted and carry the version into the stored plan and report. Older jobs and plans resume with the original scorer, and existing records retain their scores and IDs. To score the same run and actuals again under the new version, submit a new evaluation key.
