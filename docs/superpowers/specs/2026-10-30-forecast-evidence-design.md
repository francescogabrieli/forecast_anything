# Configurable forecasting and historical evidence

Date: 30 October 2026. Technical design for roadmap step 2 under the owner-approved MCP-first release direction. This document proposes implementation details, not claims of implemented functionality. No commits, staging, pushes or publication are authorized.

## Product outcome

From their assistant a person can choose an installed numerical provider and supported horizon, issue a real forecast, and request a reproducible historical comparison against a seasonal baseline. The result identifies the source vintage, assumptions, planned origins, exclusions, actual providers, immutable runs/evaluations and aggregate scores. The core computes everything; MCP is an adapter.

This closes the next evidence gap after the verified MCP vertical slice. Installation lifecycle, desktop-host validation, recurring-question tools, assistant reports and the public site remain separate release blockers. A passing backtest does not alone make the whole release ready.

## Approaches and recommendation

The agreed product direction is MCP-first. For this increment:

- Wrapping the existing benchmark script is smaller but carries fixture-specific data preparation, assumption and provider setup; it lacks product persistence and recoverable jobs.
- Replaying a latest-only Snapshot is tempting but scientifically unsafe: earlier revisions may have been discarded.
- Recommended: a bounded core backtest job with an immutable normalized revision archive, frozen origin plan and durable per-origin results. Reuse Runtime, temporal splits and evaluation rather than creating another numerical engine.

## Initial supported boundary

Backtests initially use one registered CSV history source and one numerical series/unit on the existing regular fixed UTC hourly/daily grid. Configured forecasts may reuse an already stored and uniquely validated CSV or HTTP snapshot vintage without source I/O; no new HTTP registration or archive support is introduced. No scenarios, known-future covariates, implicit imputation/alignment or multi-history scoring. Providers must be explicitly installed and registered; Timestral remains opt-in under existing conditions. Tests use baseline and controlled providers, without downloading weights or making paid calls.

Requests carry an explicit selected provider/options, horizon 1–366, baseline period 1–10000, at most 1–50 origins per partition (default 10), and non-negative origin_offset_seconds (default zero, strictly less than one source interval). The offset is declared, never inferred from future outcomes: nominal context end plus this offset is the issuance time, and the next target must remain later than issuance.

## Trusted configurable forecast

A new configured_run job request names source_id, immutable snapshot_id, provider, options, horizon, baseline_period and key. A trusted builder derives frequency from the unique catalog revision represented in snapshot assumptions and derives series/unit from the stored observations. It builds a deterministic graph with source, baseline and model nodes. Existing validate_run and provenance/scenario checks still apply before enqueue.

No source file is reread here. Request retries reconstruct the same graph from the same stored vintage, even after the source catalog changes. Requested and actual providers remain distinguishable. Failed or unsupported configurations do not silently fall back to another model.

## Immutable revision archive

Extract the existing normalization stage from ingest_source as a reusable raw reader while preserving existing ingestion outputs. Backtest ingestion stops after 100001 rows and refuses archives exceeding 100000 rows. It preserves all supplied revisions visible at capture time, not just the latest observation per event.

At its first worker execution, a backtest verifies the source catalog revision bound at submission, reads the registered CSV once and persists a content-addressed normalized archive and frozen plan before any provider invocation. It records capture time, source revision, declared availability semantics, configuration, installed provider capabilities/revisions, split calendar and origin membership. It contains no source locations or secrets in public responses.

This preserves revisions supplied by the source; it cannot recreate historical versions already removed upstream. Missing historical information produces exclusions/insufficient evidence, and the report states this limitation. Availability dates are never guessed to improve coverage.

## Origins, targets and partitions

Construct a complete frequency-derived UTC grid from the earliest to latest event times of archive rows satisfying both event_time <= capture_time and available_at <= capture_time. Reject off-grid timestamps. Refuse a calendar longer than 100000 instants before materializing it; a small sparse source must not allocate an unbounded grid. Preserve missing interior cells in the calendar; they cause exclusions or insufficient evidence, never shifted targets or changed split boundaries. Known-in-advance future events cannot extend the bounds.

Use existing build_splits: 50% exploration, 25% selection, 25% final, stride equal to horizon and complete non-overlapping target windows. Each partition deterministically takes its earliest N planned origins; N is fixed in the request, before inference. No automatic winner selection or tuning in this increment. All partitions are labelled; the final holdout is never used to select options.

For each nominal origin t, issue at t + origin_offset_seconds. History requires both event_time <= t and available_at <= issue time. Freeze revisions at that issuance instant. Require the last history event to equal t, and require a complete finite regular history grid; otherwise record an exclusion. Planned targets must match both emitted forecasts exactly. Do not shift targets after seeing missing data or failures.

Freeze observed actuals from the same archive at capture time and retain source_revision lineage. Future/unavailable rows and assumed scenario outcomes cannot become observed evidence. Existing evaluate_run supplies immutable numerical scores. Each graph uses fixed node names baseline and model, ensuring the explicit seasonal baseline is selected consistently even when the selected model is also seasonal_naive.

## Durable computation and report

The existing leased worker executes the parent job. It verifies that current provider contracts and actual returned provider identities/revisions match those frozen in the plan; a changed registration fails explicitly instead of mixing numerical vintages across a resumed report. Child emission keys depend on backtest identity and planned origin, never on parent attempt. Store each origin outcome immutably with the parent lease guard. A reclaimed job reuses the archive, plan, existing child runs, evaluations and outcomes; it does not reread a changed file or duplicate published emissions. This is durable logical idempotence, not a promise of exactly-once physical inference.

Per-origin outcomes distinguish evaluated, excluded, failed and insufficient_evidence with stable reason codes and optional run/evaluation references. Provider failure remains visible, including the planned denominator. Lease loss is never converted into a data exclusion.

Aggregate count-weighted model/baseline MAE on identical successfully evaluated target cells only, separately for each partition. Retain planned/matched/excluded/failed/insufficient counts; relative MAE is null with an explicit reason when no matched cells or baseline MAE is zero. A report with no valid final comparison is insufficient_evidence. Reports do not activate watches or certify general predictive quality.

Persist the completed report immutably. Public reads return a small summary and paginated origin references; the private raw archive is not returned by the report endpoint. Existing get_run/get_evaluation/get_snapshot expose issued evidence through their normal workspace boundary.

## API, MCP and security

Extend the existing typed job union with configured_run and backtest. Bind source revision on first backtest submission. On an identical retry, return the original job before rereading catalog/source state; different content under the same key conflicts. API authentication and error sanitation remain unchanged.

Add GET /v1/backtests/{id} for completed summaries and GET /v1/backtests/{id}/origins with offset and bounded limit for immutable origin outcomes. Pending jobs are polled through existing get_job; absent reports are not fabricated.

MCP adds submit_configured_forecast, submit_backtest, get_backtest and list_backtest_origins. submit_backtest is source-I/O and must enforce the operator source-ID allowlist; a known source ID alone does not authorize reading its CSV. Both submission tools are mutating; source-I/O is labelled honestly. Preserve 1 MiB HTTP bounds and 64 KiB complete tool-result bounds.

Regenerate checked-in API/console contracts and generated TypeScript clients; verify existing console/agent typing. Keep the optional SDK and no-LLM baseline path intact. No localhost dashboard becomes a prerequisite.

## Acceptance

- A late revision changes only origins where it was available; a known-in-advance future event never enters history.
- Declared issuance offsets support within-interval publication delays without using later information.
- Splits, planned target windows and configurations are persisted before the first numerical call.
- A killed/reclaimed worker resumes the same report using stable child identities even after the source changes or disappears.
- A real SDK client submits and reads the workflow through stdio/API/worker and reconnects to the same stored results.
- A selected baseline period different from the comparator produces manually checkable multi-origin scores; zero-error comparators and provider failures remain honest.
- Configured live forecasts retain source vintage and reject unsupported provider/horizon/assumptions rather than falling back.
- Source permissions, sanitized errors, bounded pages, installed-wheel execution and existing journeys continue to pass.

Technical decisions here are builder proposals for review. The owner’s release direction and no-commit/no-push constraint remain binding.

Builder check: completed; the only material gap was the split calendar, resolved explicitly above as a complete UTC grid retaining missing cells.
