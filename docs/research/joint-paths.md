# Experimental joint residual trajectories

Status: **experimental/provisional**, evaluated on the frozen M4 baseline artifacts on 2026-10-25. No domain passes the predeclared positive lower 95% Brier-skill bound. This completes the research experiment, not acceptance of calibrated joint forecast probabilities. Timestral license/real-parity acceptance and model comparison remain pending; no weights were downloaded or run.

## Method and attribution

`ResidualPanelSampler.sample(base, panels, as_of, draws, seed)` samples a historical shared origin uniformly with replacement for each draw. Its entire rectangular **series × horizon** forecast-error panel (`actual − issued point`) is added to the current issued point matrix. The same sampled origin supplies every series and every horizon cell in a draw. Marginal quantiles are not combined and no cells are independently reconstructed.

The derived forecast identifies `residual_panel_sampler@1`, retains `base_provider=seasonal_naive@1` in assumptions, and always labels itself experimental/provisional. The empirical experiment uses only M4's original issued `seasonal_naive@1` forecasts and that provider's own panels. The benchmark's three datasets each contain one preselected series: they test temporal dependence; cross-series evidence here is synthetic.

The method assumes historical residual panels transfer to a new forecast origin. Neither stationarity nor calibration follows from preserving their dependence. Residuals are unweighted and unscaled; no clipping, smoothing, tuning, missing-value fill or final-panel update occurs. Samples may be physically implausible (for example negative counts); no untested physical constraints are imposed.

The sampler requires a point forecast, a regular future UTC grid, unique series, and finite complete panels matching the exact series order and horizon. It rejects duplicate origins, shifted grid phases, provider mismatches, incomplete matrices and targets that differ from the forecast cadence. Each panel must mature no earlier than its last target; only `available_at <= as_of` panels are eligible. If historical target timestamps/provider metadata are supplied, they are checked. The five-field fixture interface remains supported, with those metadata responsibilities on the caller. Empty or entirely unmatured support raises `insufficient_joint_support`, never synthetic joint information.

Origins are sorted before a seeded `random.Random` draw stream, so input order does not affect results and longer runs preserve earlier draw prefixes. `sample_group_id` binds the method, base forecast/provenance, eligible panel content, as-of instant, seed and draw count. Assumptions record a support digest and sampled-origin-index digest. The experiment's independent control has its own identity, `independent_residual_control@1`, samples each cell separately from the same empirical support, and explicitly declares destroyed dependence.

## Frozen protocol

```sh
uv run python experiments/joint_paths.py --seed 0 --draws 1000
```

The default source is `.local/benchmark`; output is `.local/joint_paths/report.json`. Optional `--source` and `--output` support offline fixtures. Output cannot be placed inside M4 inputs. The script opens the completed SQLite ledger using immutable read-only mode, rejects a nonempty live WAL, and verifies input hashes before and after evaluation. It never invokes data preparation or changes M4 artifacts.

M3 `TemporalSplit` is reconstructed from the saved bounds and **exact frozen calendar**, then `origins_for(partition, calendar)` supplies every split. Saved origin lists must agree. The script reuses M4's issued base forecasts, snapshot/run/evaluation references and actuals snapshots, rather than rebuilding a changed calendar or reissuing model forecasts. `origins.csv` identifies evaluated complete-history/complete-target windows. Horizons equal strides, so final target windows do not overlap.

For each dataset, before fetching its final actuals, define one event through M2's registered `any_exceed` operator: **any selected series exceeds the 75th percentile of complete exploration-window maxima at any forecast timestamp**, with strict `gt` comparison and NumPy's linear quantile rule. The same operator scores path probabilities and the single realized world; event formulas are not duplicated. The historical-frequency reference is the event rate over completed exploration/selection windows available before the first frozen final origin. The threshold, reference and sampling support never incorporate final outcomes. Later final observations may already be in M4-issued point-forecast histories, as ordinary rolling-origin context; they never become M5 residual panels or reference events.

Brier scores use M3 `event_metrics`. Brier skill is `1 − method Brier / historical-frequency Brier` on the same final origins. Its interval uses 2,000 paired-origin bootstrap resamples, seed 0, percentile endpoints 2.5%/97.5%, and a fixed historical-frequency forecast. The bootstrap does not refit the event/reference. Undefined reference scores or bootstrap denominators fail the evidence gate. Five fixed probability bins `[0,.2), [.2,.4), [.4,.6), [.6,.8), [.8,1]` report mean probability, observed frequency and count; ECE is the count-weighted absolute gap.

Predeclared operational promotion thresholds are **at least 30 non-overlapping final origins, 10 events, 10 non-events and a strictly positive lower 95% Brier-skill bound**. These are proposed operational criteria, not guarantees. There is no pooled-domain promotion, synthetic promotion, holdout-based threshold adjustment or method selection. Any substantive method change after this test requires a new holdout.

## Artifact and data lineage

All panels are `seasonal_naive@1`; each JSONL row retains dataset, split, historical run, issued/actual snapshot, evaluation, manifest and source-download identities. The report fingerprints that exact file and M4 ledger, and records source metadata, per-dataset split counts, availability basis and each evaluated final prediction's run/snapshot/sample-group identities. No provider mixing occurs.

Manifest SHA-256: `8db5e3ab0d79f1b99b9b61e881f7cc5cdd5f8e21505381e0d4b45301c9a0fd72`.

| M4 input | SHA-256 |
| --- | --- |
| `frozen_calendar.json` | `44acf739e87a389edfb5597911f00d1f3888b2ae00a41e333e1c6c7dc386af0a` |
| `ledger.sqlite` | `2feb23521594342c0b3983431b2b07f8839cc4abfb2366aa81eb89b5d1c8241c` |
| `origins.csv` | `6b954e96d6732e517c53ef86615679616f2d4e2703e7e76574cb3958ee80480a` |
| `report.json` | `d673b56df09384dc2b88ab2b17ff44d816688a99700f5ae37639c2568b02aca5` |
| `residuals.baseline.jsonl` | `8b5441f84482842a40fb2c602e630920b5ead23aa30315cc8c7b293577492691` |

| Domain | Exploration panels | Selection panels | Final panels | Frozen final candidates | Scored final origins |
| --- | ---: | ---: | ---: | ---: | ---: |
| retail | 67 | 37 | 0 | 37 | 37 |
| energy | 455 | 219 | 0 | 360 | 230 |
| activity | 256 | 130 | 0 | 130 | 130 |

The total is **1,164 completed exploration/selection panels and zero final panels**. Energy retains M4's 523 incomplete hours as missing evidence: 130 frozen final candidate windows fail complete history/target support and are excluded without filling. Energy observations are hourly mean **kW**, not kWh. Retail is all positive, non-cancelled item quantities across all countries; activity is fixed English Wikipedia all-access/user daily totals.

Historical publication vintages are unavailable. `assumed_available_at=period_end_UTC` and `availability_basis=assumed_not_observed` describe assumed availability, not observed release-time certification. UCI source timezones are interpreted as UTC; Wikimedia buckets use UTC. Source rights/checksums and preparation recipes remain in `benchmarks/manifest.yaml` and M4 preparation metadata: UCI Retail II and Household Power are CC BY 4.0; Wikimedia Analytics is CC0 1.0.

## Synthetic known-process evidence

Each case uses two equal-mass historical worlds and 200 balanced enumerations of their realized outcomes, with zero base point forecasts and `any_exceed(threshold=0, comparator=gt)`. Positive dependence has both cells +1 or both −1; negative dependence has opposite signs. The two cells are either two series at one horizon or two horizons of one series. Thus true event probabilities are .5 and 1, respectively, while independent-cell sampling would imply .75 for both. The synthetic historical-frequency reference is .5 or 1, exactly the frequency of events in the two historical worlds.

These enumerated diagnostics isolate the dependence error and are not independent real holdout evidence. Costs are one generated 1,000-draw forecast per method/case, reused across the 200 descriptive outcome windows.

| Case (same results for series and horizon variants) | Method | Event probability | Brier | Brier skill vs frequency | 95% interval | ECE |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| positive | panel | 0.497 | 0.250009 | -3.599999999992498e-05 | [-0.001716, 0.001644] | 0.003000 |
| positive | independent | 0.757 | 0.316049 | -0.2641960000000001 | [-0.408116, -0.120276] | 0.257000 |
| negative | panel | 1.000 | 0.000000 | undefined | undefined | 0.000000 |
| negative | independent | 0.751 | 0.062001 | undefined | undefined | 0.249000 |

Panels retain the expected ordering **positive .497 < independent approximately .75 < negative 1**. The positive panel Brier is close to the optimal historical-frequency .25, with only finite Monte Carlo discrepancy. For negative dependence all 200 outcomes are events: the historical-frequency reference has zero Brier, so skill/interval are undefined and the 10-non-event gate fails. This failure is explicit; it is not repaired by changing the synthetic process after evaluation. Joint synthetic evidence alone never promotes the method.

## Frozen benchmark evidence

| Domain | Threshold (native unit) | Historical windows | Historical frequency | Final events / non-events |
| --- | ---: | ---: | ---: | --- |
| retail | 34961.50000000 | 104 | 0.19230769 | 12 / 25 |
| energy | 3.75503333 | 674 | 0.20771513 | 21 / 209 |
| activity | 276979040.25000000 | 386 | 0.18652850 | 14 / 116 |

| Domain | Method | Brier | Reference Brier | Brier skill | 95% skill interval | ECE | Sampling + event seconds |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| retail | panel | 0.26800011 | 0.23656645 | -0.13287455 | [-0.93761895, 0.31287955] | 0.19481081 | 0.079 |
| retail | independent | 0.27201441 | 0.23656645 | -0.14984355 | [-1.02536181, 0.33051172] | 0.20813514 | 0.091 |
| energy | panel | 0.17639613 | 0.09651933 | -0.82757295 | [-1.35833772, -0.45016759] | 0.24041304 | 3.329 |
| energy | independent | 0.21018446 | 0.09651933 | -1.17764100 | [-1.84662429, -0.70558358] | 0.30120000 | 3.947 |
| activity | panel | 0.07378870 | 0.10230982 | 0.27877206 | [-0.05063656, 0.53505757] | 0.05116154 | 0.524 |
| activity | independent | 0.08138725 | 0.10230982 | 0.20450210 | [-0.20645731, 0.48274418] | 0.08616923 | 0.614 |

All domains meet count minimums. **All fail the strictly positive lower bootstrap skill bound**, leaving every domain and the overall method experimental/provisional. Retail and energy have negative skill against historical frequency. Energy's interval is wholly negative, and its panel probabilities substantially overpredict event frequency. Activity has positive average skill but its interval crosses zero. Panels have lower observed Brier than the independent control in all three datasets; this is descriptive and is not a separate validated superiority claim.

Calibration for the panel method (full control bins also appear in the JSON report):

| Domain | Probability bin | Count | Mean forecast probability | Observed event frequency |
| --- | --- | ---: | ---: | ---: |
| retail | [0.0, 0.2) | 5 | 0.162000 | 0.000000 |
| retail | [0.2, 0.4) | 17 | 0.290941 | 0.352941 |
| retail | [0.4, 0.6) | 4 | 0.489750 | 0.500000 |
| retail | [0.6, 0.8) | 5 | 0.781800 | 0.400000 |
| retail | [0.8, 1.0] | 6 | 0.899000 | 0.333333 |
| energy | [0.0, 0.2) | 70 | 0.127971 | 0.042857 |
| energy | [0.2, 0.4) | 102 | 0.286657 | 0.068627 |
| energy | [0.4, 0.6) | 31 | 0.485129 | 0.258065 |
| energy | [0.6, 0.8) | 9 | 0.707222 | 0.111111 |
| energy | [0.8, 1.0] | 18 | 0.927444 | 0.111111 |
| activity | [0.0, 0.2) | 107 | 0.051850 | 0.056075 |
| activity | [0.2, 0.4) | 6 | 0.251833 | 0.166667 |
| activity | [0.4, 0.6) | 5 | 0.502200 | 0.000000 |
| activity | [0.6, 0.8) | 3 | 0.654333 | 0.000000 |
| activity | [0.8, 1.0] | 9 | 0.912667 | 0.777778 |

Total recorded runtime: **8.877 s**, including ledger loading, synthetic cases, sampling, operator application and bootstrap summaries. Base forecasts were reused, with zero additional provider inference calls and zero network/model-weight cost. Each method makes 397 empirical path-generation calls (37 + 230 + 130) and four synthetic calls. Path cells per empirical origin are 5,000 retail, 24,000 energy and 7,000 activity; peak storage includes one origin's Python/Pydantic paths, so cell counts are not a byte-accurate memory measurement. Timing is local and environment-dependent.

## Verification and limitations

Focused tests cover unmatured exclusion; empty support; matrix/provider/calendar mismatches; duplicate origins; shared-origin series/horizon dependence; seed, input-order and draw-prefix identity; independent-control ordering/provenance; score/bootstrap gates; final-only frozen origins; immutable M4 inputs; final-panel/provider contamination; and final-actual perturbation invariance. Changing final fixture actuals changes scored outcomes while leaving event definitions, references, sample identities and forecast probabilities exactly unchanged.

The full regular suite and lint/format checks pass, with the existing real Timestral parity test skipped pending its separate gate. Standard `uv build` produces wheel and sdist. The local sandbox initially could not resolve PyPI for isolated build dependencies; the same standard command subsequently passed with scoped build-only network access. An additional offline cached-dependency/no-build-isolation build also succeeded. No M1–M4 source or data changes were made.

Residual transfer across changing levels, volatility, seasonality and source regimes remains unvalidated. Non-overlapping windows avoid target reuse but do not guarantee independent origins; the simple paired IID bootstrap may understate serial uncertainty. Exploration-based event choices and intervals are per dataset; no multiple-testing correction or broad event-family claim is made. The synthetic cases have only two support panels and the real benchmark has only one series per domain. Probability estimates retain Monte Carlo error at 1,000 draws. Actual release-vintage uncertainty, missing observations, small positive-event counts and the baseline's forecast biases remain limitations.

No event, residual transformation, support weighting or promotion threshold was tuned after the frozen final results. Post-run validation/provenance corrections were replayed with exactly identical thresholds, sample IDs, probabilities and outcomes. Future substantive changes require new frozen holdout evidence.
