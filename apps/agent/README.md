# Optional discovery agent

This package is the isolated Eve adapter for the core discovery job. The Python core and deterministic forecasting paths do not depend on this service. It exposes only the authenticated `POST /forecast/discover` and `GET /forecast/discover/:sessionId` bridge to the worker. The standard Eve session API denies callers; the default home route is disabled.

## Runtime and compatibility

- Node 26.0.0 and npm 11.12.1 were used for this evaluation.
- Eve is pinned at `0.83.0`. The Postgres Workflow World is pinned at `5.0.5`; its dependency on `@workflow/world@5.0.5` exactly matches Eve's resolved `@workflow/world@5.0.5`. The bundled Eve docs still mention an older beta line; the installed package metadata and lockfile are the compatibility evidence.
- Eve supports self hosting, direct AI SDK providers, and `@workflow/world-postgres` for durable sessions. This package configures the direct Mistral provider through `MISTRAL_MODEL_ID` (default `mistral-large-latest`) and `MISTRAL_API_KEY`. No provider call is made by tests or build.
- `FORECAST_AGENT_DATABASE_URL` (or `WORKFLOW_POSTGRES_URL`) stores bridge session metadata in `forecast_agent.discovery_sessions`, separate from the Workflow World tables. Configure the Workflow World Postgres connection according to its package documentation. A real Postgres restart test still requires a running daemon.
- `FORECAST_AGENT_BRIDGE_TOKEN` authenticates the Python worker to the two bridge routes. `FORECAST_AGENT_CORE_URL` and the distinct `FORECAST_AGENT_CORE_TOKEN` authenticate tools to **only** `/v1/agent/operations`. Never give the agent the workspace token or source credentials.

`POST` parks a deterministic `discovery/<job_id>` Eve session and persists its session ID. The Python worker checkpoints the ID before its first `GET`. Polling sends the first turn with a stable Eve idempotency key. Every actual tool call sends Eve's `callId` to the core, which reserves the persistent A2 budget and issues the operation ID before executing. Model prose is ignored; only core validated tool results become candidates. `expected_deviation`, `forecast_change`, and `declared_limit` are the executable registry. Unknown template ideas can be saved as **non-executable** candidates only.

The tool allowlist contains `inspect_source`, `propose_candidates`, and `explain_run`. `defaultTools: false` excludes optional shell, file, and web tools. No MCP connections, skills, or subagents are installed. The Docker sandbox uses `deny-all` networking. Production network policy for the **agent service process** must also restrict outbound traffic to the configured core and selected provider endpoint; Docker's sandbox policy does not constrain authored tools or model calls, which run in the service process.

## Checks

Run `npm ci --ignore-scripts`, `npm run contracts:check`, `npm run typecheck`, and `npm test -- --run`. `npm run build` prewarms the deny-all Docker sandbox and needs a running Docker daemon. `npx eve build --skip-sandbox-prewarm` checks compilation without Docker but its output is not deployable. No paid Mistral API smoke has been run; that remains a separate synthetic-only, authorized check. Timestral weights are not downloaded.
