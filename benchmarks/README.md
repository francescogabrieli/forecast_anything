# Cross-domain benchmark evidence

The pull request CPU gate uses a small synthetic series and an untrained,
seeded Timestral model. It measures regression against a frozen reference
and seasonal baseline. The **Forecast benchmarks** workflow runs the full
[public-data manifest](public-manifest.yaml) with the seasonal baseline on demand
and uploads its report,
origin outcomes and frozen calendar. Trained checkpoint comparisons use
the separate local procedure below.

## Phase 0 reproduction

From the repository root, freeze the prepared calendars before the first score, then run the leaderboard and its two-run stability check:

```sh
uv run --locked --extra dev --extra mcp python -m benchmarks.frozen_splits --manifest benchmarks/manifest.yaml --prepared .local/data --output benchmarks/splits/phase0.json
```

```sh
FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED=1 FORECAST_ANYTHING_TIMESTRAL_123M_WEIGHTS_APPROVED=1 uv run --locked --extra dev --extra mcp --extra timestral python -m benchmarks.leaderboard --manifest benchmarks/manifest.yaml --split-file benchmarks/splits/phase0.json --output .local/phase0 --repetitions 2 --providers baseline ets theta autoarima timestral timestral_123m
```

The split command prepares the pinned inputs and freezes calendar hashes, target-window boundaries, and origin assignments before provider evaluation. It compares every final target label with [`historical_targets.json`](splits/historical_targets.json), an exact timestamp-only union built from all available evaluated origin and score artifacts. The leaderboard command starts two isolated processes against that frozen file. It writes `leaderboard.csv`, `reference_models.csv`, and `stability.json` at `.local/phase0/`; detailed reports, per-origin scores, origins, performance records, residual panels and ledgers are under `.local/phase0/runs/<run-id>/run-01/` and `run-02/`. Intermediate repetition ledgers are kept as `ledger.sqlite.gz`; the last repetition keeps `ledger.sqlite` directly.

`exploration` is reported as **development**, `selection` as **validation**, and `final` as **holdout**. The default command scores only development and validation. The runner refuses a request to score `final`; its origin timestamps are recorded with status `reserved`, with no forecasts, actuals, residuals, or metrics. Use a new output directory for each independent reproduction if you want to retain earlier run artifacts.

**Phase 0 status: complete for development and validation.** Two independent repetitions produced identical score projections. Fresh final candidates are frozen and reserved across all four domains: 818 M5 retail origins; 507 M4 Daily Macro origins (D1–D3: 242 + 242 + 23); 13,033 UCI reactive-power energy origins; and 310 English Wikipedia traffic origins. The historical target archive rejects reused labels by series and exact timestamp. Online Retail II and active-power energy have zero eligible final origins because all available candidate targets were evaluated historically. The holdout has zero forecasts, score rows, residuals, or metrics and remains reserved for a later final evaluation. The M5 bundle is SHA-256 verified, retained only under ignored `.local/`, and is not redistributed. Timestral 123M was run locally under the owner’s personal-benchmark authorization; weights and data are not redistributed.

The completed run is `20261114T101651194683Z-f357f34d`. Its two score projections have SHA-256 `8df5c88b71278a85510d4313a51439fa0f3c5d5ca2953f5bfa281d072bede945`; the 123M per-origin score projection is `ba19c36cc7890f6bdbd24a41b78dac137a8ed0ef1b736d64903a5555ff6eaf64`. The output tables and run artifacts remain under ignored `.local/phase0/`.

Candidate origins use stride one and therefore have overlapping target horizons. The reserved final target-label ranges are M5 retail 2014-01-02 through 2016-04-25 UTC, M4 Macro series D1–D3 starting immediately after each series' historical score range, UCI Global_reactive_power from 2009-06-01 01:00 through 2010-11-27 00:00 UTC, and Wikipedia pageviews from 2026-01-02 through 2026-11-13 UTC. The previously benchmarked Global_active_power series has no eligible unseen final target window.

The leaderboard reuses core MAE, pinball loss, and interval coverage, and adds MASE, sMAPE, and weighted quantile loss where quantiles exist. ETS uses ETS(A,N,N) with alpha selected on a fixed one-step SSE grid; Theta averages the fitted linear trend and optimized simple exponential smoothing; AutoARIMA performs deterministic CSS/AIC order selection over ARIMA(p,d,0), p=0..3 and d=0..1. The ARIMA search fixes q=0 and all three statistical references are point-only. Their WQL is explicitly `quantiles_unavailable`. Paired bootstrap intervals and a Diebold–Mariano test with an overlap-aware HAC lag are written for matched model comparisons. The two-run stability check compares split assignments and score outputs, excluding latency and memory because they vary with runtime conditions. `performance.json` records CPU inference latency per dataset/provider/split, process peak RSS, and process CPU time.

The M4 subset is pinned to official repository commit `6c1067e5a57161249b17289a565178dc7a3fb3ca`; preparation appends each official 14-step test series to its training history, checks source hashes, and validates that D1–D3 are in the Macro category.

The user-supplied M5 bundle is from the organizers' Drive folder recorded in `.local/data/m5/source-checksums.json`, attributed to the [M5 methods repository](https://github.com/Mcompetitions/M5-methods). The project owner has accepted the applicable Kaggle competition rules for this non-commercial local benchmark. All six CSV files are size- and SHA-256-verified against the local register and manifest. Only `calendar.csv` and `sales_train_validation.csv` contribute observations: calendar row order maps to D_1 onward, then each day's unit counts are summed across all 30,490 item-store rows into one retail series. `sales_train_evaluation.csv`, both `sales_test_*.csv` files, and `sell_prices.csv` are verified but their values are not used. Originals stay in ignored `.local/data/m5/` and are not copied into Git; redistribution of the CSVs is outside this work.

The historical final windows and all available development/validation score artifacts were reconciled by exact target timestamp and series ID. The old benchmark's 397 final origins are included alongside 602,150 per-origin score rows from six previous Phase 0 repetitions; the cross-check found no score row without a matching evaluated origin. The resulting archive stores timestamps and source artifact hashes only. The 2009–2010 active-power target labels and 2023–2025 Wikipedia target labels were already scored, so neither range is reused for final evaluation. Energy holdout now uses the distinct `Global_reactive_power` series. Wikipedia uses the official user-agent series through 2026-11-12; its pinned response has 3,969 daily items and SHA-256 `28080da0e7f495d430bcc28e2d4d44654561560fe914c96cbf854c6fa8e2ca64`. The final targets remain reserved.

Timestral 28M uses the existing `FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED=1` gate and its pinned checkpoint. Timestral 123M has an executable provider route and separate `FORECAST_ANYTHING_TIMESTRAL_123M_WEIGHTS_APPROVED=1` gate. The LICENSE at pinned revision `5a147287addda85f6acd8da3fb8858fe9af7e8f7` is Modified MIT (SHA-256 `648194727930df730890e9f9affdbcc5c930d406d6829559b25ca3d5a973fc8c`); it restricts rights if the user's company or employer exceeded USD 20 million in global consolidated monthly revenue for the preceding month. On 2026-11-14 the owner authorized local Phase 0 use and confirmed this is a personal open-source project. The 123M weights are cached locally at the pinned revision, excluded from Git, and were evaluated in both repetitions. The authorization does not extend to checkpoint or data redistribution or other users and deployments.

The `.yaml` manifests deliberately use JSON syntax, a valid YAML subset, so the harness needs no YAML or spreadsheet dependency. The retail workbook is streamed with standard-library ZIP/XML readers. Raw downloads, prepared observations, quality files, SQLite emissions and numerical outputs stay under ignored `.local/` directories.

## Frozen choices and source rights

The public manifest fixes series, coverage, transformations, context, horizon and seasonal period before provider evaluation. Online Retail II uses positive non-cancelled daily quantities with a five-day horizon and seven-day seasonality. M5 uses daily total units across all item-store rows, a 28-day horizon, and seven-day seasonality. Energy retains hourly `Global_active_power` in **kW** for development/validation and separately benchmarks `Global_reactive_power` in **kW** for fresh final windows; neither is an integrated kWh series. Activity uses daily English Wikipedia project totals, `all-access` and `user`, from 2016 through 2026-11-12. M4 uses daily IDs D1–D3 in source-ID order, validates their Macro category, and uses the official 14-step horizon without score-based series filtering.

Online Retail II is attributed to UCI, DOI [10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D), under CC BY 4.0. Individual Household Electric Power Consumption is attributed to UCI, DOI [10.24432/C58K54](https://doi.org/10.24432/C58K54), under CC BY 4.0. Wikimedia Analytics API data is CC0 1.0; see its [access policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html). M4 files come from the [official Mcompetitions repository](https://github.com/Mcompetitions/M4-methods), pinned by immutable commit and file hashes; consult that repository for its data terms. Requests use an identifiable User-Agent and are serialized. Download URLs, source SHA-256 pins, source coverage and licenses live in `manifest.yaml`; preparation records checksums again, with the precise recipe and prepared-data digest, in `preparation.json`. A changed pinned download or prepared CSV fails validation. Download caches are bound to their source URL. Retain the original downloads: their hashes verify identity, but a remote source may eventually disappear or revise a historical response.

## Recipes and temporal meaning

All prepared observations use the existing six-column core CSV contract. Bucket timestamps are **right endpoints**: a transaction on 1 January belongs to the daily observation labelled 2 January 00:00. Data is assumed available at that endpoint. The original UCI timezones are not certified; interpreting their wall clocks as UTC is an explicit calendar assumption with no DST conversion. Wikimedia buckets already use UTC. No dataset includes historical release vintages; the replay does **not** certify real historical publication times. `assumptions.json` and each residual panel say `assumed_not_observed`.

Retail invoice identifiers beginning with C, and negative quantities, contribute only to the separate `retail.returns.csv`, as positive magnitudes. They are never netted into sales. Calendar days with no transactions are treated as zero trading activity under the declared complete-extract assumption. Zero quantities are ignored. Energy only emits a finite hourly mean when all 60 unique minute readings are present and valid; otherwise its value remains empty. `energy.quality.json` retains observed/valid/expected counts for every hour. Duplicate meter minutes and readings off the exact minute boundary are rejected. Pageview days absent from the response remain empty. No missing history or outcome is filled.

The labelled `synthetic_deliveries` scenario is illustrative. It has no observed realization binding and never contributes actuals, metrics or residuals. The three fixture CSVs contain generated synthetic examples, labelled separately from the public real observations.

## Runs, splits and residual evidence

`benchmarks/splits/phase0.json` pins each input calendar digest, target-window origin digests, explicit boundaries, horizon, effective stride, historical-target archive hash, and final target-label hashes. The archive in `benchmarks/splits/historical_targets.json` lists exact timestamps for every available previously evaluated target on each series, and records SHA-256 hashes of its source artifacts. Freeze fails if any final target timestamp reuses a historical scored label. Split membership applies to **target windows**: the origin immediately before a boundary can issue the first forecast in that partition. Mobile origins use stride one, so targets overlap. Paired `relative_mae`, bootstrap and Diebold–Mariano statistics use the same matched origins and the frozen effective stride. Previously evaluated Online Retail II and active-power energy finals remain empty. New M5, reactive-power energy, Wikipedia 2026, and M4 Macro final candidates are recorded as reserved rows with an empty input key and reason `holdout_reserved_for_final_evaluation`; no final scores are written.

The harness reuses the core `Runtime`, immutable `Ledger`, `freeze`, `evaluate_run`, and seasonal-naive provider. `ledger.sqlite` retains issued development/validation forecasts and evaluation records; graph JSON is exported too. `report.json` contains per-split scores and `origin_scores.csv` contains per-origin core and benchmark metrics. Aggregation weights by scored target cells. Empty or unsupported evidence remains undefined. `environment.json` records Python/platform, installed versions, Git revision and harness file hashes.

`residuals.baseline.jsonl` contains one complete, aligned issued window per line, in deterministic manifest/split/origin order. Every line includes:

- `origin`: ISO 8601 UTC issuance instant.
- `horizon`: integer number of target steps.
- `series_ids`: ordered series IDs (one preselected series per dataset in v1).
- `errors`: series × horizon, **actual minus the issued point forecast**.
- `available_at`: latest assumed availability of all target observations in the panel.

Additional lineage includes dataset, benchmark provider name, actual provider ID/revision, history and actuals snapshot IDs, run/evaluation IDs, split, target timestamps, manifest/download hashes, source kind and assumed availability rule. Panels belong only to `exploration` and `selection`; **holdout outcomes never enter residual panels**. Failed, short, missing-history or incomplete-target windows have no valid panel and their exclusions remain visible. An empty Timestral JSONL file provides no calibration evidence.

## Model gates and interpretation

Every run must request `baseline`; the CLI emits the structured `baseline_required` error on stderr with exit code 2 if it is omitted. Baseline operation does not load model weights. The 28M and 123M providers use separate explicit local approval gates. The command above supplies both gates for this owner-authorized local reproduction; the 123M weights are already cached at the pinned revision. The leaderboard does not establish event calibration or general model performance. The real holdout is never scored in Phase 0. Synthetic historical compatibility for joint-paths fixtures is available only through an explicit flag and is rejected for manifests containing real observations.

## Local checkpoint comparison

`compare_timestral.py` runs an independent sample of GIFT-Eval and requires
PyArrow 26.0.1 in the benchmark environment. The script records the pinned
[Salesforce/GiftEval revision](https://huggingface.co/datasets/Salesforce/GiftEval/tree/30841734ac5cfddbd0c3bad6d09d2b6b32becbb0),
file subdirectories, periods, horizons and development/holdout assignment.
Download `data-00000-of-00001.arrow` from each subdirectory at that revision and
save it as `<dataset>.arrow` in an ignored data directory. The runner verifies
each SHA-256 before loading model weights.

After preparing both checkpoints explicitly:

```sh
forecast-anything model prepare --timestral-model 28m
forecast-anything model prepare --timestral-model 123m
python -m benchmarks.compare_timestral --data .local/gift-eval --model 28m --output .local/gift-eval/28m.json
python -m benchmarks.compare_timestral --data .local/gift-eval --model 123m --output .local/gift-eval/123m.json
python -m benchmarks.compare_timestral --data .local/gift-eval --model 28m --recent-context 128 --output .local/gift-eval/28m-two-windows.json
```

The local CPU fp32 run used four threads and 223 paired, non-overlapping target
windows across seven datasets. The maximum input context was 512 steps. The
two-window candidate averaged the point forecasts from 128 and 512 steps
where both were available. Each model was scored on the same finite target
cells as the seasonal reference. Seasonal scaling used only the context
available at each origin. Lower MASE is better.

| Reserved dataset | Windows | Seasonal reference | 28M | 123M | 28M, two windows |
| --- | ---: | ---: | ---: | ---: | ---: |
| Jena weather | 48 | 0.8607 | 0.7177 | 0.6566 | 0.8504 |
| Saugeen daily flow | 4 | 1.9901 | 0.9566 | 0.9761 | 0.9570 |
| US daily births | 4 | 1.7884 | 1.2833 | 1.1603 | 1.3145 |
| Hourly solar | 48 | 0.7990 | 0.9454 | 1.0163 | 0.9266 |
| Mean across datasets | 104 | 1.3596 | 0.9758 | 0.9524 | 1.0121 |

The 123M reduced the reserved mean by 2.4% and improved two of four datasets.
Median inference took 12.0 ms for the 28M and 37.6 ms for the 123M. Peak
process RSS was 440 MiB and 1,166 MiB respectively. The 28M with two windows
increased the reserved mean by 3.7%, with 21.5 ms median inference. These
measurements describe a local sample and a custom protocol. Two reserved
datasets contain one series each. The experiment used public series and
did not independently establish their absence from checkpoint pretraining.
The product keeps the 28M as default and offers the 123M as an explicit choice.
