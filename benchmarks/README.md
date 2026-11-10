# Cross-domain benchmark evidence

Run from the repository root with the regular development environment:

```sh
uv run python -m benchmarks.prepare --manifest benchmarks/manifest.yaml --output .local/data
uv run python -m benchmarks.run --manifest benchmarks/manifest.yaml --output .local/benchmark
```

The `.yaml` manifests deliberately use JSON syntax, a valid YAML subset, so the harness needs no YAML or spreadsheet dependency. The official retail workbook is streamed with standard-library ZIP/XML readers. All raw downloads, prepared observations, quality files, SQLite emissions and numerical outputs stay under ignored `.local/` directories. A small generated fixture suite runs offline with the same interfaces.

## Frozen choices and source rights

The public manifest fixes series, coverage, transformations, context, horizon and seasonal period before provider evaluation. Initial quarter-length coverage was expanded, before any holdout outcomes or provider scores were inspected, to provide at least 30 final origins where completeness permits. Retail uses all item codes and countries, positive non-cancelled daily quantities over the complete documented interval, with a five-day forecast horizon and seven-day seasonality. Energy uses hourly mean `Global_active_power` in **kW**, over the documented source interval; it is not an integrated kWh series. Activity uses daily English Wikipedia project totals, `all-access` and `user`, during 2016–2025. These choices do not depend on final performance.

Online Retail II is attributed to UCI, DOI [10.24432/C5CG6D](https://doi.org/10.24432/C5CG6D), under CC BY 4.0. Individual Household Electric Power Consumption is attributed to UCI, DOI [10.24432/C58K54](https://doi.org/10.24432/C58K54), under CC BY 4.0. Wikimedia Analytics API data is CC0 1.0; see its [access policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html). Requests use an identifiable User-Agent and are serialized. Download URLs, actual archive/response SHA-256 pins, source coverage and licenses live in `manifest.yaml`; preparation records checksums again, with the precise recipe and prepared-data digest, in `preparation.json`. A changed pinned download or prepared CSV fails validation. Download caches are bound to their source URL. Retain the original downloads: their hashes verify identity, but a remote source may eventually disappear or revise a historical response.

## Recipes and temporal meaning

All prepared observations use the existing six-column core CSV contract. Bucket timestamps are **right endpoints**: a transaction on 1 January belongs to the daily observation labelled 2 January 00:00. Data is assumed available at that endpoint. The original UCI timezones are not certified; interpreting their wall clocks as UTC is an explicit calendar assumption with no DST conversion. Wikimedia buckets already use UTC. No dataset includes historical release vintages; the replay does **not** certify real historical publication times. `assumptions.json` and each residual panel say `assumed_not_observed`.

Retail invoice identifiers beginning with C, and negative quantities, contribute only to the separate `retail.returns.csv`, as positive magnitudes. They are never netted into sales. Calendar days with no transactions are treated as zero trading activity under the declared complete-extract assumption. Zero quantities are ignored. Energy only emits a finite hourly mean when all 60 unique minute readings are present and valid; otherwise its value remains empty. `energy.quality.json` retains observed/valid/expected counts for every hour. Duplicate meter minutes and readings off the exact minute boundary are rejected. Pageview days absent from the response remain empty. No missing history or outcome is filled.

The labelled `synthetic_deliveries` scenario is illustrative. It has no observed realization binding and never contributes actuals, metrics or residuals. The three fixture CSVs contain generated synthetic examples, labelled separately from the public real observations.

## Runs, splits and residual contract for M5

`frozen_calendar.json` persists the exact timestamps, boundaries, stride, horizon and origins from M3's `build_splits` and `origins_for`. Split membership applies to **target windows**: an origin at the preceding boundary can issue the first final forecast. Calendars and candidate origins for every dataset are persisted before inference. `origins.csv` records provider, split, origin, target endpoints and the snapshot input key, including excluded windows and reasons (`insufficient_history`, `missing_history`, `incomplete_targets`, or failed provider/evaluation). Non-overlapping target windows use stride equal to horizon. The fixed context length is the same for each prospective provider.

The harness uses the unchanged core `Runtime`, immutable `Ledger`, `freeze` and M3 `evaluate_run`. `ledger.sqlite` retains issued point forecasts and evaluation records; graph JSON is exported too. `report.json` indexes `datasets.retail`, `datasets.energy` and `datasets.activity`, then providers and per-split counts/MAE. Aggregation weights by the number of scored target cells. Empty/unsupported evidence remains undefined. `environment.json` records Python/platform, installed versions, Git revision and harness file hashes.

`residuals.baseline.jsonl` contains one complete, aligned issued window per line, in deterministic manifest/split/origin order. Every line includes M5's fields:

- `origin`: ISO 8601 UTC issuance instant.
- `horizon`: integer number of target steps.
- `series_ids`: ordered series IDs (one preselected series per dataset in v1).
- `errors`: series × horizon, **actual minus the issued point forecast**.
- `available_at`: latest assumed availability of all target observations in the panel.

Additional lineage includes dataset, benchmark provider name, actual provider ID/revision, history and actuals snapshot IDs, run/evaluation IDs, split, target timestamps, manifest/download hashes, source kind and assumed availability rule. M5 must filter panels to `available_at <= issuance origin` when calibrating a later forecast. Panels belong only to `exploration` and `selection`; **final outcomes never enter residual panels**. Failed, short, missing-history or incomplete-target windows have no valid panel and their exclusions remain visible. An empty Timestral JSONL file provides no calibration evidence.

## Pending model gate

Every run must request `baseline`; the API raises structured `baseline_required` before preparation if it is omitted, and the CLI emits the JSON error on stderr with exit code 2. Baseline operation does not import Timestral or fetch weights. Requesting `timestral` currently records `pending_license` and leaves its comparison undefined; this is an explicit non-executing gate. The report remains `pending_model_comparison`, even after a successful baseline run. Baseline-only evidence does not complete Plan 02 M4 or establish event calibration/general model performance. After the M1 license/parity gate is authorized, extending the harness to issue real model forecasts must preserve these frozen origins, context snapshots and inputs. Put model and baseline nodes in the same run to use M3's relative metric; separate runs require a matched origin/input join and unmatched comparisons must stay undefined. Do not change the frozen public choices based on this holdout's results.

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
