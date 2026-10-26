# Synthetic activity example

From the repository root after installing the regular Python environment:

```sh
mkdir -p .local
uv run python scripts/run_example.py activity --db .local/activity.db
```

The shared loader reads `graph.json`, the six-column `observations.csv` contract,
and `assumptions.json`. It freezes a snapshot at **2026-10-21 00:00 UTC** and
uses the same `Runtime`, `Ledger`, and `SeasonalNaiveProvider` as the retail and
energy examples. No external service, key or model weights are needed.
Repeating the command against the same database returns the saved run ID.

The forecast is **120, 180, 150 views**, at the daily right endpoints
22–24 October 2026. These point estimates repeat the last three daily totals.
Both the synthetic-data label and the calendar assumptions appear in the
returned forecast's `assumptions`.

All six observations are hand-authored synthetic view totals. They are not
Wikimedia observations or unique-user counts. Daily timestamps are fixed UTC
bucket ends and immediate availability is assumed. The three-day period is
illustrative, and no news, campaign, bot classification or causal mechanism is
modelled. No uncertainty bands or spike probabilities are estimated; the
joint-path experiment has not established calibrated probabilities. These
fixtures are separate from the real-data recipes and frozen evidence in
`benchmarks/`.
