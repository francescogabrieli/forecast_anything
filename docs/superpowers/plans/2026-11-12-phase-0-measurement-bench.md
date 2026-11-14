# Fase 0 — Banco di misura Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Produce a reproducible rolling-origin leaderboard for the available benchmark reference providers while freezing split definitions, reserving final outcomes, and recording uncertainty and CPU costs.

**Architecture:** Keep `Runtime`, `Ledger`, `evaluate_run`, the seasonal-naive provider, the gated Timestral provider, and `evaluation.splits` as the execution core. Add benchmark-only metrics/statistics and a repeat-run CLI that consumes a repository-pinned split definition, scores development/validation, and never reads holdout values.

**Tech Stack:** Python 3.12+, existing Pydantic/NumPy environment, pytest, Ruff, stdlib `resource`, CSV/JSON.

**Spec:** `/Users/francescogabrieli/Downloads/forecast-anything-piano-accuratezza.pdf`, Fase 0 only.

## Global Constraints

- Use M5 for retail and a subset of M4, GIFT-Eval, or fev-bench; cover one or two non-retail domains.
- Reuse calendar/origin freezing, pinball loss, coverage, seasonal-naive, Timestral 28M, and the existing evaluation core; add ETS, Theta, and AutoARIMA reference providers.
- Freeze development, validation, and holdout splits and record split hashes in the repository.
- Reserve holdout for a single final evaluation; this phase scores development and validation only.
- Add MASE, sMAPE, and CRPS or weighted quantile loss; add bootstrap confidence intervals and Diebold–Mariano tests.
- Distinguish historical, synthetic, and replay evidence; record CPU latency and memory.
- Leave all changes in the working tree and do not commit.

## Scope Rulings

- M4 Daily D1–D3 supplement Online Retail II, energy, and Wikimedia; their official source revision and hashes are pinned. The six M5 CSVs are supplied from the organizers’ Drive folder in ignored `.local/data/m5/` and pinned to `source-checksums.json`. The recipe verifies all six, uses only `calendar.csv` and `sales_train_validation.csv`, and aggregates every item-store row into one daily retail series.
- Deterministic CPU-only ETS(A,N,N), nonseasonal Theta, and restricted AutoARIMA(p,d,0) references use pinned variants and a common AIC response window. Timestral 28M and 123M have pinned executable routes and separate local approval gates. The 123M checkpoint is cached locally under its pinned revision; the owner's personal-use authorization is recorded in the model lock.
- Historical final windows for Online Retail II, energy, and Wikimedia were consumed by the joint-paths experiment. Keep those old windows excluded; freeze fresh M5 retail, energy, and web-traffic windows, reserve M4 Macro windows, and do not score any final holdout during Phase 0.
- The 507 M4 Daily D1–D3 final candidates are Macro (242 + 242 + 23). Fresh final windows are also frozen for M5 retail, reactive-power energy, and web traffic; all were checked against historical target timestamps by series. All final candidates remain reserved and unscored. The 123M weights were authorized and evaluated locally in two repetitions.
- The current checkout is a regular, detached repository with existing user changes. Work in place because the request specifically asks to leave the result in this working tree; do not create a separate worktree or commit.

## Review Focus

1. Holdout target values must not enter origins, metrics, residuals, or repeat stability projections; test reserved rows contain no score and no final run is invoked.
2. Rolling windows overlap; test uncertainty calculations use paired origins and dependence-aware blocks/lags.
3. Missing or incomplete windows must remain excluded and must not shift origin assignments; preserve the existing complete-window tests.
4. MASE is undefined for zero seasonal scale; test a constant series reports a reason rather than NaN/Infinity.
5. Point-only forecasts have no quantile score; test WQL remains undefined while core MAE/pinball/coverage behavior is preserved.

---

### Task 1: Benchmark metrics and paired-origin statistics

**Files:**
- Create: `benchmarks/scoring.py`
- Create: `tests/unit/test_benchmark_scoring.py`

**Interfaces:**
- Consumes: core `ForecastResult`, `forecast_metrics`, and observed/forecast values.
- Produces: `score_origin(...)` for MASE/sMAPE/WQL and paired bootstrap skill/Diebold–Mariano helpers.

- [x] Add failing tests for MASE, sMAPE, weighted quantile loss, zero seasonal scale, deterministic moving-block bootstrap, and overlapping-origin DM lag.
- [x] Implement those helpers with finite JSON-safe outputs and explicit undefined reasons.
- [x] Run the focused tests and the existing evaluation tests.

### Task 2: Freeze mobile splits and reserve holdout

**Files:**
- Modify: `src/forecast_anything/evaluation/splits.py`
- Modify: `benchmarks/manifest.yaml`
- Modify: `benchmarks/run.py`
- Create: `src/forecast_anything/providers/classical.py`
- Create: `benchmarks/frozen_splits.py`
- Create: `tests/unit/test_frozen_benchmark_splits.py`
- Create: `tests/unit/test_statistical_providers.py`
- Modify: `tests/integration/test_benchmark_contract.py`

**Interfaces:**
- Consumes: Task 1 origin scoring helpers and `TemporalSplit`.
- Produces: a frozen split JSON with calendar/origin SHA-256 hashes; `run_suite(..., score_splits=("exploration", "selection"))` leaves final origins reserved and unscored by default.

- [x] Add failing tests for stride-one origins, split digest validation, default holdout reservation, and explicit preservation of exclusion reasons.
- [x] Add optional stride to `build_splits`, defaulting to horizon for existing callers; set mobile stride to one in the phase-zero manifest.
- [x] Generate `benchmarks/splits/phase0.json` from prepared calendars; exclude historical final windows already used by joint-paths and validate it before running inference.
- [x] Record per-origin core/benchmark metrics, latency, source class, and CPU process memory while leaving final actual values untouched.
- [x] Add deterministic CPU ETS, Theta, and AutoARIMA references and score them against seasonal-naive.
- [x] Run benchmark contract and split tests.

### Task 3: Repeated leaderboard, reference table, and docs

**Files:**
- Create: `benchmarks/leaderboard.py`
- Modify: `benchmarks/README.md`
- Modify: `tests/integration/test_benchmark_contract.py`
- Modify: `tests/integration/test_benchmark_leaderboard.py`

**Interfaces:**
- Consumes: frozen split JSON and run reports from Task 2.
- Produces: `leaderboard.csv`, `reference_models.csv`, and `stability.json` from two isolated development/validation runs.

- [x] Add failing tests for metric-only stability comparison, holdout exclusion, leaderboard rows, and reference-provider pending states.
- [x] Implement a two-run CLI that writes separate run directories and compares score/statistic projections while treating timing as observational; add executable routes for Timestral 28M and 123M with separate approval gates.
- [x] Add a single-command reproduction recipe and document current dataset/model gaps without changing scope past Phase 0.
- [x] Run the full Python test suite (attempted; see ledger for sandbox-limited failures), focused Phase 0 tests, Ruff checks, and the real benchmark twice on development/validation for all available reference providers.
- [x] Inspect the working-tree diff and leave all changes uncommitted.

### Acceptance status update

Phase 0 is **complete for development and validation**. Two independent repetitions have matching score projections, including the separately gated Timestral 123M, and all real final windows remain reserved with zero forecasts, scores, residuals, or metrics. Fresh target windows are frozen for M5 retail, M4 Macro D1–D3, UCI reactive-power energy, and English Wikipedia traffic; the historical timestamp guard rejects any reuse. M5 is integrated from the organizers' Drive bundle under the user's accepted non-commercial local use of the Kaggle rules; its six raw CSVs remain under ignored `.local/` and are not redistributed. The later one-time final evaluation remains intentionally unrun.
