# Required Local Timestral Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for independent provider/discovery tasks, coordinated with the main implementer for product enforcement. Steps use checkbox syntax. The owner approved the design and explicitly instructed execution; proceed without another approval round.

**Goal:** Make pinned local Timestral mandatory for new product forecasts, preserving immutable legacy evidence and baseline comparisons.

**Architecture:** Generic library runtimes retain explicit provider injection for research/tests; product CLI runtimes declare `required_provider="timestral"`. A shared policy resolves primary output and verifies its provider ancestry at submission/execution. Model preparation and readiness are separate from metadata reads. Discovery receives an explicit forecast provider, preserving old candidate reconstruction.

**Tech Stack:** Python/Pydantic, Timestral/PyTorch CPU, FastAPI, SQLite, MCP, React contract snapshots.

**Spec:** `docs/superpowers/specs/2026-11-05-required-timestral-design.md` (approved by owner).

## Global Constraints

- Pinned Timestral-28M CPU fp32, no remote inference key or silent fallback.
- Baseline is reference only in the product; labeled deterministic library fixtures remain valid tests.
- No historical evidence rewrites or hidden requalification; fresh candidate/epoch and final-window safeguards remain.
- Existing site edits must be preserved; product publication remains separate.

## Review Focus

- Unused Timestral nodes cannot permit a baseline-primary graph.
- Replay of already accepted immutable work preserves original keys; pending legacy execution fails terminally.
- Model readiness never claims loaded/usable solely from API/worker liveness.
- Legacy candidate validation preserves original identities instead of reinterpreting provider.
- Model failures and negative backtest skill remain explicit; no forced watch activation.

### Task 1: Pinned product provider and setup

**Ownership:** provider worker owns `providers/timestral.py`, new `providers/configuration.py`, `cli.py`, dependency packaging/Compose, provider/CLI tests. Main implementer owns Runtime required-provider API and readiness endpoint; coordinate CLI constructor calls.

**Interfaces:** `configured_providers()` always registers pinned Timestral plus seasonal comparator; CLI-created `Runtime(..., required_provider="timestral")`. Model `check_model()` performs cache/provenance checks without downloading/importing Torch; `prepare_model()` explicitly prepares and loads pinned model. Add `model status` / `model prepare` CLI routes. CPU actual inference remains lazy.

- [x] Write failing tests for default registration, rejected disable/mismatched pins, preparation/readiness and no fallback.
- [x] Run targeted tests red; implement minimal pinned configuration/setup and lazy safe provider checks.
- [x] Make normal install include the pinned model dependency; retain compatible extra alias for existing docs, update lock and container default.
- [x] Verify provider/CLI tests and wheel contents; commit only owned files after coordination.

### Task 2: Provider-aware discovery

**Ownership:** discovery worker owns `discovery/candidates.py`, `discovery/policy.py` only if necessary for reconstruction, and focused discovery tests. Main implementer wires API/worker call sites.

**Interfaces:** `compile_proposal(..., epoch_id, forecast_provider="seasonal_naive")`; `graph_support` accepts trusted built-in Timestral capabilities without loading weights. `validate_candidate` reconstructs its recorded primary provider. Default on pure library helpers remains baseline for legacy/test compatibility; product calls pass runtime.required_provider.

- [x] Write failing tests for Timestral forecast plus seasonal reference and legacy identity stability.
- [x] Compile new provider-aware graph; include changed graph in candidate identity and reject unknown provider spoofing.
- [x] Verify reconstructed Timestral and old candidates; do not weaken final-evidence qualification safeguards.

### Task 3: Required primary provider policy and migration

**Ownership:** main implementer owns new `forecast_policy.py`, contracts, runtime, API service/routes, backtesting service, worker, MCP forecast arguments and tests.

**Interfaces:** `Runtime(..., required_provider: str|None=None)`; `validate_primary_provider(graph, required_provider, primary_node_id=None) -> str`. Optional `primary_node_id` on run request omitted when None to retain legacy identity. Runtime.run and persisted payload carry it. Configured graphs resolve model; discovery graphs resolve question/forecast; ambiguous raw graph requires explicit target. Explicit target must be terminal and Timestral must be in its ancestry.

- [x] Write policy tests for unrelated/unused Timestral node, ambiguous output, baseline primary, valid transform ancestry and generic library compatibility.
- [x] Enforce configured/backtest selections at new submissions and worker execution; preserve accepted-key reads before applying new policy.
- [x] Stop baseline-only queued jobs with terminal `required_provider_migration`; pause legacy recurring execution with recorded reason before scheduling. Historical reads/evaluation remain possible.
- [x] Wire all product discovery compilation to required provider; ensure stale candidate/revision lineage is not bypassed.
- [x] Expose model readiness separately from process liveness, with bounded safe errors.
- [x] Verify targeted and full tests; regenerate core/console/agent contracts.

### Task 4: Real model acceptance, docs and integration

**Ownership:** main implementer owns genuine-model fixtures/evidence and docs, preserving pre-existing site source while updating model claims.

- [x] Check installed code revision and cached pinned weights; explicitly prepare Timestral and run the real parity check.
- [x] Exercise real product forecast, persisted provider provenance, reconnect/replay, genuine candidate-bound backtest and watch/update summary. Record losing/provisional qualification honestly.
- [x] Build installed artifact with model dependencies and exercise supported setup/run path outside checkout.
- [x] Update quickstart, capabilities, model guide, release gate, examples and site copy to mandatory Timestral; label historical baseline acceptance.
- [x] Verify full suites/static checks/builds and independent review, deploy the configured single local worker, commit/push and open dedicated PR.

## Execution notes

Provider/discovery changes may proceed in parallel because their owned files and interfaces are distinct. They are not alone in the codebase and must not revert other edits. Main integration must wait for the agreed interfaces and review delivered changes. Reviewers are read-only unless assigned a specific owned fix.

## Execution ledger

Owner confirmed design and execution. Worktree: `.local/worktrees/required-timestral`, branch `codex/required-timestral-runtime`.

- Provider/setup task implemented; targeted model/setup/CLI and real installed release checks passed. Review found tilde cache path mismatch; regression red/green fixed it.
- Discovery implemented; legacy IDs preserved. Review found provider-independent helper epoch; regression red/green fixed it.
- Main policy/migration implemented, including mixed baseline ancestry rejection, terminal queued migration, paused legacy watches and new epoch context. Review found scenario primary loss and console baseline-only assumptions; red/green regressions fixed both.
- Genuine model MCP lifecycle and real-model console journey passed. Final suites/contracts/docs/deployment remain in progress.

Ruling: public example runner now uses genuine Timestral and a separate seasonal comparator, while checked-in seasonal graph fixtures remain labeled historical references — normal examples must not bypass mandatory product policy — exact old baseline outputs are retained only as reference data.

Ruling: normal CI installs and inspects artifacts with explicit `--artifact-only` reporting; local real-model gates execute separately with approval/prepared cache — cache-free CI must not pretend model acceptance or silently fetch weights — release model acceptance still requires the genuine installed check.

Final verification: 902 Python, 84 console, 29 agent and 3 browser tests passed. Real installed artifact and configured local service verified. See required-timestral-acceptance.md for scope and desktop adapter reload requirement. Dedicated PR publication follows; no merge or site publication authorized.
