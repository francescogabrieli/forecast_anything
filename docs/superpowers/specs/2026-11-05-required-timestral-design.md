# Required local Timestral forecasting

## Owner direction

On 5 November 2026 the owner required a forecasting model, specifically Mistral Timestral, and explicitly selected **local Timestral as mandatory**. A seasonal repetition baseline is a comparator, not the product's forecasting engine. No Mistral inference API key or remote service is required for this mode.

## Current implementation

The pinned CPU adapter already exists and records model/code provenance, point forecasts and marginal quantiles. Real parity and a local three-domain benchmark have previous evidence. However, CLI registration is opt-in, deterministic discovery emits period-2 seasonal-naive forecasts against a period-1 baseline, and most end-to-end acceptance uses baseline fixtures. This is not sufficient evidence of the newly required product behavior. Existing release acceptance remains valid only for the old baseline scope.

## Approach

Use the existing pinned local Timestral integration as the mandatory product provider. Keep the generic core provider interface and deterministic baseline fixtures for numerical/composition tests. Do not build a hosted inference service. Merely changing a default while silently falling back to seasonal-naive would violate the owner's requirement.

Builder choice: retain `mistralai/Timestral-28M`, its current pinned weights revision and pinned official code revision from `integrations/models.lock.json`. CPU fp32 remains the initial supported execution mode. Larger checkpoints or accelerated backends are separate choices.

## Product behavior

- Normal installation/setup provisions the Timestral dependency and explicitly prepares/verifies the pinned weights. Keep heavyweight imports and downloads out of metadata reads.
- New user forecasts, configured forecasts and executable discovery candidates use Timestral as their main numerical provider. Seasonal-naive remains available for declared reference comparisons and labeled internal fixtures, not as a selectable or silent replacement for primary product forecasts.
- Apply the requirement consistently at product submission boundaries, including explicit graph submissions, so bypassing a UI default cannot produce a new baseline-only product forecast. Preserve the generic library extension interface for tests and research.
- Missing dependency, weights, wrong revisions or model load/inference failure produce clear setup/job errors. A healthy API process must not be presented as proof that the required model is ready.
- Read-only MCP, status and immutable evidence inspection remain usable to diagnose setup and inspect existing results.
- Setup documents local compute, model cache/download, licensing boundaries and the fact that no Mistral API key is needed. The existing `WEIGHTS_APPROVED` flag guards parity tests, not runtime loading. Setup must clearly disclose the weights license and local preparation; do not describe a nonexistent runtime consent guard or claim all downstream uses are authorized.

## Watch qualification and evidence

- Discovery must compile genuine Timestral forecast nodes against a separately declared seasonal baseline; supported representation/unit/calendar checks remain enforced.
- Candidate-bound backtesting must replay the exact Timestral candidate with immutable model revisions. It must not substitute a numerical baseline to accelerate acceptance.
- Retain the fresh final-window policy, minimum 30 independent evaluated final origins and positive measured skill requirement. Timestral being mandatory does not automatically qualify a watch or imply superiority.
- The `timestral_acceptance_pending` reason exists in legacy `assess_candidate`; the candidate-bound backtest policy does not have that blanket block. Preserve the latter's evidence safeguards and document the supported qualification route. Any broader legacy-policy acceptance requires separate recorded evidence.
- Marginal quantiles remain marginal; no joint sample paths, calibrated event probabilities or general forecasting-quality claims are introduced.

## Existing workspaces

- Do not rewrite historical runs, model identities, graphs, evaluations, reports or watch decisions.
- Existing baseline results remain readable and evaluable under their recorded provenance; label them as legacy/baseline evidence.
- A legacy baseline candidate must not be silently rebound to Timestral. Replacing it creates a new candidate/graph/epoch with new qualification evidence, preserving predecessor lineage where supported.
- Pending baseline-primary jobs receive a terminal, actionable required-provider migration error before numerical execution; do not retry them indefinitely. Legacy recurring watches stop producing baseline-primary runs and expose a migration state, retaining evidence and lineage.
- The local supervised service must use the model-enabled environment and pinned configuration. Test its stop/restart path without introducing a second worker for the same ledger.

## Validation

1. Offline unit and contract tests: mandatory provider selection, missing-model errors, no fallback, preserved comparator, policy lineage and legacy read compatibility. Model doubles only establish boundary behavior and are labeled as such.
2. Real local Timestral smoke with pinned weights: forecast through the supported product route, get_run provenance, model-versus-baseline output and repeat/reconnect without changing the stored result.
3. Real Timestral candidate-bound backtest and report/qualification outcome. A provisional or losing result is valid evidence; never force activation to declare the path complete.
4. Watch refresh/change summary through MCP using genuine model runs and stored evidence; preserve version/epoch changes and current applicability.
5. Installed artifact/setup verification, console/API/MCP contract checks and updated quickstart/site copy. Baseline-only synthetic E2E tests stay useful as test harnesses, but cannot be reported as acceptance of required Timestral.
6. Recheck launchd workspace after loading the model-enabled runtime. Reading an old baseline report is not the acceptance test for a new Timestral forecast.

## Delivery and limits

Prepare implementation on a branch separate from the pending console/MCP PRs, preserving local site edits. The owner has authorized commits, pushes and PRs. Product publishing and unsupported platform claims remain separate. The earlier checklist must gain a required-Timestral acceptance gate; it is not complete merely because baseline tests passed.

This design requires owner approval before the implementation plan under the applicable brainstorming workflow.

## Builder decisions after design review

A read-only builder review found no further owner decision required. For raw graphs, add or resolve an explicit primary output at the product submission boundary. Generated configured/candidate requests supply their primary output automatically; unambiguous conventional `model`, `forecast` or `question` outputs may be resolved for compatibility, while ambiguous raw graphs require explicit selection. The selected output must depend on a Timestral forecast node; an unrelated or unused Timestral node cannot satisfy the requirement. Keep provider and output identity in the persisted request/plan, and retain strict request-key replay semantics for historical accepted work.

The active development environment already contains Timestral and PyTorch, and the model lock records previously cached weights plus owner-authorized local evaluation. Verify actual pinned provenance/cache before relying on this; it is not an installed-artifact or downstream licensing guarantee.
