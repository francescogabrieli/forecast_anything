# Synthetic retail example with required local Timestral

Prepare the pinned local model, then run the product example:

```sh
uv sync --locked --extra dev
uv run --locked forecast-anything model prepare
mkdir -p .local
uv run --locked python scripts/run_example.py retail --db .local/retail.db
```

The public runner creates a distinct `_timestral` graph: Timestral is the primary forecast and the recorded seasonal graph is a separate reference. It retains the declared historical origin and availability assumptions, records actual model revisions and marginal quantiles, and replays the same immutable run for the same request. No remote Mistral key is needed; prepared local weights and their separate license are required.

The source observations are synthetic. Marginal quantiles are not calibrated joint-event probabilities and these small examples establish no general predictive quality. The checked-in `graph.json` and the former exact seasonal values are historical comparator fixtures, not the default product forecast.

## Historical baseline fixture notes

The following notes describe the earlier baseline example and its domain assumptions; its exact baseline values do not describe Timestral output.

# Synthetic retail example

From the repository root after installing the regular Python environment:

```sh
mkdir -p .local
uv run python scripts/run_example.py retail --db .local/retail.db
```

The shared loader reads `graph.json`, the six-column `observations.csv` contract,
and `assumptions.json`. It freezes a snapshot at **2026-10-21 00:00 UTC** and
uses the existing `Runtime`, `Ledger`, and `SeasonalNaiveProvider`, just like
the energy and activity examples. No external service, key or model weights
are needed. Repeating the command against the same database returns the saved
run ID.

The forecast is **12, 18, 15 items**, at the daily right endpoints
22–24 October 2026. These are point estimates obtained by repeating the last
three values. Both the synthetic-data label and the calendar assumptions appear
in the returned forecast's `assumptions`.

All six observations are hand-authored synthetic totals. Daily timestamps are
fixed UTC bucket ends and immediate availability is assumed. The three-day
period is an illustration, not validated retail seasonality. There is no
inventory balance, returns or delivery calendar here, so the forecast cannot
answer a stockout question. No uncertainty bands or event probabilities are
estimated; the joint-path experiment has not established calibrated probabilities.
These fixtures are separate from the real-data recipes and frozen evidence in
`benchmarks/`.
