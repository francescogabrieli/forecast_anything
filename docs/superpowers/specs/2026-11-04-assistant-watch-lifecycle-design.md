# Assistant watch lifecycle design

## Intent

Let an assistant save and manage recurring forecasting questions through the same local MCP connection that registers sources and submits forecasts. The assistant must be able to retrieve the current watch state, inspect its durable transition history, and compare two recorded runs with a plain explanation of the observed differences.

## Existing behavior

The core already creates evidence-aware watches, records append-only watch history, schedules source refreshes for due watches, and can summarize two comparable runs. Authenticated API routes can create/list/update watches, but the MCP catalog does not expose them. Watch history and change summaries also lack API read routes. The worker, ledger and eligibility policy remain the owners of scheduling and lifecycle state.

## Goals

- Expose `create_watch`, `list_watches`, `get_watch`, and `update_watch` through MCP.
- Expose bounded `get_watch_history` pages from the ledger's append-only watch history.
- Expose `summarize_watch_change` for two persisted runs attached to the selected watch's graph lineage.
- Preserve explicit next-due timestamps, watch IDs, pagination, and eligibility state; do not let a tool assert a watch is qualified or operational.
- Mark watch creation as a mutation with an open-world hint because the independent worker may later refresh an operator-registered source.
- Keep results bounded by the API client's upstream limit and MCP's existing 64 KiB full-result limit.

## Non-goals

- Changing the discovery policy, evidence thresholds, or automatic scheduling algorithm.
- Making forecasts alone qualify or activate a watch.
- Adding proactive notifications, a cloud scheduler, new source permissions, or new database migrations.
- Claiming that an observed change is caused by a particular input; the existing summary explicitly limits itself to observed forecast differences and snapshot identities.

## Behavior

- `create_watch(candidate_id, next_due_at)` reads the candidate's source IDs and requires each to be in the MCP process's operator allowlist before delegating to the existing core create route. Candidate eligibility and initial lifecycle are decided by the core.
- `list_watches(offset, limit)` returns a deterministic page of current watches.
- `get_watch(watch_id)` reads one current watch.
- `update_watch(watch_id, muted?, priority?)` requires at least one explicit non-null control and delegates to the existing core patch route. It cannot change lifecycle or evidence.
- `get_watch_history(watch_id, offset, limit)` reads transition records in append order and returns `next_offset` when more history exists.
- `summarize_watch_change(watch_id, previous_run_id, current_run_id)` reads the persisted watch/runs and calls the existing comparison function. Incomparable runs remain an explicit domain error. The explanation says changes are observed, not causal.

## Constraints

- Keep all writes behind `Observatory`/`Ledger` validation and existing API auth.
- Use strict typed MCP argument/result schemas, no arbitrary identifiers or source paths in errors.
- Do not expand MCP source-I/O permissions; all scheduled source refresh remains owned by the core worker and its registered source configuration. Creating a watch requires explicit grants for all candidate sources because a due watch may schedule source reads.
- Keep the direct Codex desktop UI acceptance separate from Codex CLI MCP smoke evidence.
