# Discovery runtime and state

## Context

Forecast Anything runs its primary workflow through MCP. The API and worker store forecasts, jobs and questions in one local SQLite ledger. Deterministic discovery templates run inside the core. The experimental Eve integration used a separate service, Postgres Workflow World and a Postgres bridge schema for session recovery.

## Decision

Exclude the Eve service and its Postgres configuration from the supported repository and release workflow. Preserve the experiment locally for future extraction. Keep the existing authenticated Python bridge available for separately operated integrations and preserve stored workspace records.

## Consequences

The supported setup has one database to operate and back up. The build and CI cover the core, MCP, console and site. External bridges operate their own service and storage. The worker connects using `FORECAST_ANYTHING_AGENT_URL` and `FORECAST_ANYTHING_AGENT_BRIDGE_TOKEN`. The core authenticates calls from the bridge with `FORECAST_ANYTHING_AGENT_CORE_TOKEN`. The core remains responsible for source access, tool budgets, candidate validation and qualification.

The archived Eve integration used Postgres for its workflow and bridge state. Consolidating that state into SQLite would require replacing or adapting both persistence paths and revalidating leases and restart recovery. Revisit that work if autonomous discovery becomes a supported product workflow.
