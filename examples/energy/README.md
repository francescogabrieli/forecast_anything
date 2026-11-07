# Synthetic energy example with required local Timestral

Prepare the pinned local model, then run the product example:

```sh
uv sync --locked --extra dev
uv run --locked forecast-anything model prepare
mkdir -p .local
uv run --locked python scripts/run_example.py energy --db .local/energy.db
```

The public runner creates a distinct `_timestral` graph: Timestral is the primary forecast and the recorded seasonal graph is a separate reference. It retains the declared historical origin and availability assumptions, records actual model revisions and marginal quantiles, and replays the same immutable run for the same request. No remote Mistral key is needed; prepared local weights and their separate license are required.

The source observations are synthetic. Marginal quantiles are not calibrated joint-event probabilities and these small examples establish no general predictive quality. The checked-in `graph.json` and the former exact seasonal values are historical comparator fixtures, not the default product forecast.

## Historical baseline fixture notes

The following notes describe the earlier baseline example and its domain assumptions; its exact baseline values do not describe Timestral output.

# Synthetic energy example

From the repository root after installing the regular Python environment:

```sh
mkdir -p .local
uv run python scripts/run_example.py energy --db .local/energy.db
```

The shared loader reads `graph.json`, the six-column `observations.csv` contract,
and `assumptions.json`. It freezes a snapshot at **2026-10-21 06:00 UTC** and
uses the same `Runtime`, `Ledger`, and `SeasonalNaiveProvider` as the retail and
activity examples. No external service, key or model weights are needed.
Repeating the command against the same database returns the saved run ID.

The forecast is **0.8, 1.2, 1.6 kW**, at 07:00, 08:00 and 09:00 UTC on
21 October 2026. These point estimates repeat the last three hourly means.
Both the synthetic-data label and the calendar assumptions appear in the
returned forecast's `assumptions`.

All six observations are hand-authored synthetic mean-power values in **kW**.
They are not integrated energy in kWh and were not calculated from meter
minutes. Hourly timestamps are fixed UTC bucket ends and immediate availability
is assumed; there is no local-time or DST calendar. The three-hour period is
illustrative, and the graph models no weather, tariff or physical capacity.
No uncertainty bands or capacity-exceedance probabilities are estimated; the
joint-path experiment has not established calibrated probabilities. These
fixtures are separate from the real-data recipes and frozen evidence in
`benchmarks/`.
