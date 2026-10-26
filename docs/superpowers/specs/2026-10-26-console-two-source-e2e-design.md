# Console two-source E2E design

## Intent

Complete the remaining U2 acceptance flow with the existing Playwright test. Show that the observatory can connect two deterministic source fixtures, inspect an evaluated candidate and its notification, reflect a source update in the affected graph, recover the event stream after a disconnect, and compare a hypothetical scenario while preserving the base run.

## Goals

- Exercise the real FastAPI service, ledger, worker, and console UI with the declared `SeasonalNaiveProvider` deterministic provider.
- Keep all model calls local and deterministic; no API key, network provider, or external dataset is required.
- Verify persisted evaluation records and the run-completion notification in the rendered console, along with source lineage and changed graph nodes.
- Preserve the existing keyboard, narrow viewport, contrast/state-label, replay deduplication, and scenario assertions.
- Keep base-run identity and stored results unchanged after scenario creation.

## Non-goals

- Add a user-facing evaluation workflow; the console currently reads evaluation evidence but does not submit evaluation jobs.
- Change forecast or evaluation scoring semantics, watch policy, or scenario semantics.
- Expand candidate generation to multi-source graphs; the existing compiler intentionally validates one source per candidate.
- Exercise Timestral, Eve, remote services, production deployment, or statistical model quality.

## Approaches

1. **Extend the existing console E2E (chosen):** seed or register two checked-in CSV fixtures in the existing deterministic API/worker harness, prepare a real run and evaluation through API contracts, and drive the observable actions through the browser. This reuses current setup and verifies the full integration boundary.
2. **Add a separate API-only integration flow:** easier to control source revisions and event payloads, but does not prove the UI displays evidence, notifications, and graph changes together.
3. **Change product UI to expose evaluation/source refresh controls:** expands user-facing behavior and scope beyond the unfinished U2 test acceptance; defer unless the flow reveals a required product gap.

## Constraints and decisions

- Continue `apps/console/tests/e2e/observatory.spec.ts` and `tests/e2e/serve_observatory.py`; add only the fixture data needed for two-source history/known-future or source-revision coverage.
- Use one historical source for evaluation actuals because the evaluation API requires an unambiguous forecast history source. A second source may be bound as known-future input where supported by the declared provider, or serve as the independently changed source if graph semantics require it.
- Trigger setup actions through authenticated API calls against the same real service/ledger; verify their user-visible consequences in the browser.
- Assert a stable source of truth for changed/affected nodes from persisted run/event data; do not infer the result from styling alone.
- Keep the existing deterministic test runtime and no external credentials.
- Root-cause investigation found that evaluations are stored separately from immutable `RunRecord.evidence_ids`, so add a read path keyed by `run_id` and have the console use it; do not mutate the base run to attach later evaluations.
- Watch history is persisted separately from the global run event stream. Treat the worker-generated `run_completed` event after source refresh as the visible notification, and refresh watch state when that event arrives; do not fabricate a test-only SSE event.
- Keep the candidate itself single-source under the existing compiler contract. Bind the second source as a known-future input in the deterministic base graph using a test-only provider wrapper, evaluate the run against the one history source, and exercise the watch refresh on its registered candidate source.
- The built-in `SeasonalNaiveProvider` rejects known-future inputs, so keep it for the candidate/watch refresh and use a narrowly scoped test-only deterministic wrapper only if required to consume both fixtures in the two-source base graph.

## Acceptance

The single E2E flow proves two source fixtures are bound to the base graph, an evaluation is persisted and visible in its run details, a worker-generated run-completion notification arrives after a source revision, the expected graph output nodes are identified as changed, the event stream reconnects/replays without duplicate visible events, and a scenario comparison leaves the base run ID and results unchanged. The candidate/watch remains single-source per the current compiler contract. The flow also retains keyboard navigation, narrow viewport, and accessible status/contrast checks.
