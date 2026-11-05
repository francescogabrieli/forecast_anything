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

- [ ] Write failing tests for default registration, rejected disable/mismatched pins, preparation/readiness and no fallback.
- [ ] Run targeted tests red; implement minimal pinned configuration/setup and lazy safe provider checks.
- [ ] Make normal install include the pinned model dependency; retain compatible extra alias for existing docs, update lock and container default.
- [ ] Verify provider/CLI tests and wheel contents; commit only owned files after coordination.

### Task 2: Provider-aware discovery

**Ownership:** discovery worker owns `discovery/candidates.py`, `discovery/policy.py` only if necessary for reconstruction, and focused discovery tests. Main implementer wires API/worker call sites.

**Interfaces:** `compile_proposal(..., epoch_id, forecast_provider="seasonal_naive")`; `graph_support` accepts trusted built-in Timestral capabilities without loading weights. `validate_candidate` reconstructs its recorded primary provider. Default on pure library helpers remains baseline for legacy/test compatibility; product calls pass runtime.required_provider.

- [ ] Write failing tests for Timestral forecast plus seasonal reference and legacy identity stability.
- [ ] Compile new provider-aware graph; include changed graph in candidate identity and reject unknown provider spoofing.
- [ ] Verify reconstructed Timestral and old candidates; do not weaken final-evidence qualification safeguards.

### Task 3: Required primary provider policy and migration

**Ownership:** main implementer owns new `forecast_policy.py`, contracts, runtime, API service/routes, backtesting service, worker, MCP forecast arguments and tests.

**Interfaces:** `Runtime(..., required_provider: str|None=None)`; `validate_primary_provider(graph, required_provider, primary_node_id=None) -> str`. Optional `primary_node_id` on run request omitted when None to retain legacy identity. Runtime.run and persisted payload carry it. Configured graphs resolve model; discovery graphs resolve question/forecast; ambiguous raw graph requires explicit target. Explicit target must be terminal and Timestral must be in its ancestry.

- [ ] Write policy tests for unrelated/unused Timestral node, ambiguous output, baseline primary, valid transform ancestry and generic library compatibility.
- [ ] Enforce configured/backtest selections at new submissions and worker execution; preserve accepted-key reads before applying new policy.
- [ ] Stop baseline-only queued jobs with terminal `required_provider_migration`; pause legacy recurring execution with recorded reason before scheduling. Historical reads/evaluation remain possible.
- [ ] Wire all product discovery compilation to required provider; ensure stale candidate/revision lineage is not bypassed.
- [ ] Expose model readiness separately from process liveness, with bounded safe errors.
- [ ] Verify targeted and full tests; regenerate core/console/agent contracts.

### Task 4: Real model acceptance, docs and integration

**Ownership:** main implementer owns genuine-model fixtures/evidence and docs, preserving pre-existing site source while updating model claims.

- [ ] Check installed code revision and cached pinned weights; explicitly prepare Timestral and run the real parity check.
- [ ] Exercise real product forecast, persisted provider provenance, reconnect/replay, genuine candidate-bound backtest and watch/update summary. Record losing/provisional qualification honestly.
- [ ] Build installed artifact with model dependencies and exercise supported setup/run path outside checkout.
- [ ] Update quickstart, capabilities, model guide, release gate, examples and site copy to mandatory Timestral; label historical baseline acceptance.
- [ ] Verify full suites/static checks/builds and independent review, deploy the configured single local worker, commit/push and open dedicated PR.

## Execution notes

Provider/discovery changes may proceed in parallel because their owned files and interfaces are distinct. They are not alone in the codebase and must not revert other edits. Main integration must wait for the agreed interfaces and review delivered changes. Reviewers are read-only unless assigned a specific owned fix.
