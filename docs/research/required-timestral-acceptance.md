# Required local Timestral acceptance — 5 November 2026

Owner-approved product direction: local Mistral Timestral is mandatory for primary forecasting. Earlier baseline-only acceptance is historical. This record distinguishes genuine model runs from deterministic library/model-double tests and artifact-only CI inspection.

## Required product behavior

The installed CLI builds a product runtime with `required_provider="timestral"`, pinned Timestral-28M and a separate seasonal comparator. New configured forecasts/backtests cannot select a baseline primary. Raw graphs resolve or explicitly declare their terminal primary output; every forecasting ancestor must use the required model. Disconnected Timestral nodes and mixing a seasonal forecast into the primary calculation are rejected. Generic library runtimes remain explicitly injectable for research and deterministic tests.

Primary output identity is saved on new runs and inherited by scenarios. Optional fields are omitted on legacy records/requests, preserving prior replay keys and evidence. Historical baseline runs/reports remain readable. Queued baseline-primary work fails terminally with `required_provider_migration`; legacy recurring watches pause with a visible migration explanation, and cannot resume into operational state. New product watches cannot be created from legacy baseline candidates.

New discovery epochs include the required provider and runtime provider revision; the library proposal helper preserves the exact legacy baseline epoch and gives Timestral a separate epoch. Candidate-bound plans freeze model contracts; the runner rejects changed provider revisions and never substitutes a baseline. Final windows remain single-use and at least 30 evaluated non-overlapping final origins with positive measured skill are required for qualification.

## Setup and readiness

Normal installation includes the pinned Timestral/PyTorch dependencies. `forecast-anything model status` inspects code provenance and cached artifact availability without importing Torch, loading weights or using the network. `cached` is not `loaded`; `ready` describes an instance loaded in the inspecting process, not a different worker process. Authenticated capabilities expose the required provider and model status separately from API/worker liveness.

`forecast-anything model prepare` explicitly downloads missing pinned artifacts and verifies CPU loading. Inference uses `local_files_only=True`; missing/corrupt/unloadable models produce errors rather than fallback or implicit downloads. Model code/weights retain their separate licenses. The owner authorized local execution; this is not a blanket downstream license grant or a Mistral API-key integration.

## Genuine local CLI/API/worker/MCP journey

Reproducer: `scripts/check_timestral_mcp.py`, after explicit model preparation, with an unused private `--workspace` and `--report` path. The script starts the actual production `up` command (independent API and worker), connects through official SDK stdio MCP processes, and uses the real clock. Only hand-authored CSV values are synthetic; no model, queue or policy is mocked. Machine-readable facts: [required-timestral-live-evidence.json](required-timestral-live-evidence.json).

- Registered 360 daily synthetic alternating observations with explicit UTC/availability semantics.
- Discovery produced a Timestral primary candidate and separate seasonal reference.
- A configured forecast and candidate forecast recorded the exact checkpoint/code/weight revisions. The configured run records primary `model`; candidate runs use `question`.
- A candidate-bound backtest evaluated 30 final origins. Model MAE was **0.01022263765335083**, reference MAE **2**, relative MAE **0.005111318826675415**. The core recorded `qualified_final_backtest_evidence` and activated the watch; the test does not force activation or replace the provider.
- Original-key replay returned the same job. The MCP process disconnected while the independent worker continued.
- Fourteen latest synthetic observations were increased by 10. At the real watch deadline, without a manual refresh tool call, the worker refreshed inputs, invalidated old evidence and created a provisional successor.
- A new MCP process reread the unchanged historical report. Stored point forecasts for 6 November changed **1.0119681358337402 → 11.06694507598877**, delta **10.05497694015503**; marginal quantile changes were also recorded. The summary states observed input/output changes, not causal effects.

These are numerical and lifecycle acceptance checks on a deliberately easy synthetic pattern. They establish no general forecasting superiority, calibration or production readiness.

## Genuine console and installed artifact

The guarded Playwright `timestral.spec.ts` launches separate production services, maps a fresh synthetic CSV through the actual console, clicks the first-forecast action and verifies the persisted primary output, Timestral revision, baseline reference and finite forecast. The screenshot shows the actual model result; no exact baseline arithmetic is relabeled as model output. The two older browser journeys retain their explicit deterministic library providers.

Real parity and installed-model checks were executed with explicit local weights approval: **6 passed**. The installed release check installs a built wheel in a fresh environment outside the checkout, verifies model status, explicitly prepares/loads the cached pinned model and runs the genuine Timestral minimal example. It checks provenance, finite shape and marginal output, not an exact hard-coded baseline value. The wheel inspection rejects bundled weights and credentials.

## Verification boundaries

- First full SDK-enabled suite before final review fixes: 895 passed, 2 real-model guards skipped. Final results are recorded below.
- Real model browser run: 3 passed (one genuine Timestral journey plus two library fixtures), 10.5 seconds.
- Model doubles test UI/provider boundaries only. The console accepts the provider named by its core candidate and rejects substituted results; product policy remains enforced in the backend, not by a UI allowlist.
- CI's `--artifact-only` release inspection is explicit: it installs/inspects artifacts, marks model validation not executed and leaves all model-smoke flags false. It is not genuine model acceptance and does not silently download or execute weights in ordinary CI.
- Docker build/other platforms, public site publication, native assistant graph rendering and login/reboot service installation remain separate release tasks.

## Final verification and configured local service

- Full SDK-enabled Python suite with explicitly approved real weights: **902 passed**, 66.68 seconds.
- Console: **84 passed**, typecheck and production build passed. Agent: **29 passed**, typecheck and generated contracts passed.
- Final Playwright run: **3 passed**, 10.8 seconds, including the genuine Timestral journey.
- Ruff lint/format and diff whitespace checks passed. Built wheel installed outside checkout: model preparation and real minimal inference passed; no weights or credentials bundled.
- Independently reviewed provider/discovery/policy and corrected regression findings before final verification.
- Updated the existing single launchd runtime and MCP executable to the retained feature worktree after a consistent private SQLite backup. Existing token and source permissions were retained.
- Fresh official MCP SDK process confirmed mandatory Timestral, successful real deployed run `7a78c0f340a53d3152fd1a0ecbb52fa2436be8dee6c58b05437d9b55d431cd81`, primary `model`, separate seasonal comparator. The synthetic source is `required-timestral`.
- Historical backtest `8a2f888fe105f38a43c5e80389ba262bfa697d47df13f4c62da4b3d0becdd6c1` remains completed. Sampled legacy watch is paused/stale with `required_provider_migration`.
- The already running desktop MCP process retains its old response schema; capabilities/watch reads require a Codex restart to load the updated configured adapter. Historical backtest reads already work through the current desktop process.
- launchd remains session-managed; installation for future login/reboot is outside this change. Docker builds were not executed because no Docker daemon was available. Site data/copy was updated locally in the original checkout, separately from this feature PR, without publishing.
