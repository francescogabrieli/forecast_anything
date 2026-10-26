# Optional agent runtime

## Decision

Keep Eve as an optional, isolated adapter in `apps/agent`. The Python core remains the authority for source access, candidate compilation, persistent budgets, evidence, and activation. The forecast engine and deterministic templates work without Eve. Eve proposes structured candidate ideas; model prose and numeric outputs are never evidence.

Use the direct OpenAI AI SDK provider and Responses API for orchestration. The model is selected with `OPENAI_MODEL_ID` and defaults to `gpt-6-luna`. `OPENAI_API_KEY` exists only in the Eve agent service environment and is never forwarded to the core or tools. Mistral is reserved for Timestral forecasting; no Mistral chat provider or key is used by this service. ChatGPT subscription billing does not cover OpenAI API calls.

## Evaluated versions and evidence

- Node.js 26.0.0 and npm 11.12.1 were used locally; CI targets Node 24.
- Eve `0.83.0`, `@workflow/world-postgres` `5.0.5`, and `@workflow/world` `5.0.5` are pinned in `apps/agent/package-lock.json`. The resolved Workflow package versions match exactly. The agent was built from the version-matched documentation shipped in `node_modules/eve/docs/`.
- Eve supports self-hosting; its Postgres Workflow World stores durable sessions independently from the Python SQLite ledger. Bridge metadata is stored under the separate Postgres schema `forecast_agent`.
- Sources: [Eve 0.83.0 release](https://github.com/vercel/eve/releases/tag/v0.83.0), [Eve self-hosting guide](https://eve.dev/docs/guides/deployment/self-hosting), [Eve Workflow world configuration](https://github.com/vercel/eve/blob/main/docs/agent-config.md), [Workflow Postgres world](https://github.com/vercel/workflow/tree/main/packages/world-postgres), [OpenAI GPT-6 Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna), [AI SDK OpenAI provider](https://ai-sdk.dev/providers/ai-sdk-providers/openai).

## Trust boundaries

- The Python worker uses `FORECAST_ANYTHING_AGENT_URL` and `FORECAST_ANYTHING_AGENT_BRIDGE_TOKEN` for the bridge. Eve tools use a separate `FORECAST_AGENT_CORE_URL` and `FORECAST_AGENT_CORE_TOKEN`; the workspace token and source credentials are never sent to Eve or the model.
- All three tools (`inspect_source`, `propose_candidates`, `explain_run`) call the authenticated core operation endpoint. The core reserves a durable, per-call budget using Eve's stable call ID before executing an operation and validates the result against frozen epoch lineage.
- `defaultTools: false` disables optional shell, file, and web tools. No MCP connections, skills, or subagents are configured. The Docker sandbox uses `deny-all` networking.
- The authored core client accepts only HTTPS for a remote core URL; HTTP is permitted only on loopback. Its fetch wrapper restricts requests to the configured core origin and rejects redirects. The direct OpenAI SDK is constructed with its supported custom fetch hook, restricted to `https://api.openai.com`, with redirects rejected. These are enforced application controls for those two fetch paths.
- Authored tools and model calls run in the agent service process, outside the sandbox. `apps/agent/compose.agent-egress.yaml` places that process on an internal Docker network without a direct outbound route. Only a dedicated proxy also joins the outbound network; it permits TLS CONNECT to `api.openai.com:443` and denies other destinations. Node 24.5+ sends fetch traffic through that proxy. The self-hosted core and Workflow Postgres must join the internal network. A Docker integration check verifies allowed OpenAI connectivity, denied Mistral/arbitrary HTTPS, and blocked direct sockets. The Postgres connection is fixed by operator environment, never model input.
- The standard Eve session API is configured to reject unauthenticated callers; the unused home route is disabled. The discovery routes require their own bearer token.
- The bridge parks the Eve session at deterministic address `discovery/<job_id>`, persists its ID, and sends the first turn only after the core worker checkpoints that ID. Polling retries reuse a stable delivery idempotency key. Tool results are accepted only from validated `propose_candidates` action results; model prose is ignored.
- Candidate ideas with an unknown template are retained as non-executable. Only the three registered A2 templates can compile to executable graphs. New executable question types require a reviewed registry extension, and any activation still requires fresh actuals-backed evaluation.

## Verification and limits

The package tests use controlled responses and make no paid provider calls. `npm run typecheck`, generated-contract checks, and `npm test -- --run` pass. `npm run build` prewarms the Docker sandbox. Docker integration checks cover service-level egress and a real scripted Eve turn interrupted after a budgeted core operation; after Eve and Postgres restart, the same session resumes, the operation ID is reused, a candidate is proposed once, and budget usage is unchanged. The isolated restart fixture simulates expiry of Graphile Worker's four-hour stale-job lock rather than waiting four hours. Deterministic tests cover duplicate and concurrent job starts, parked-session reuse, stable first-turn delivery, token separation, tool-result validation, and persisted metadata behavior. A paid provider inference smoke is not part of CI.

Historical note: the synthetic provider check used one tool-calling request with `ministral-3b-latest`, a 32-token output cap, and no retries. It invoked the local core's `inspectSource` operation for one synthetic source and returned its sanitized profile and persistent operation ID. This predates the approved provider decision and does not validate the selected OpenAI provider.

Live GPT smoke, 2026-10-26: after explicit approval of the bounded request and estimated cost, `gpt-6-luna` sent one 3,132-byte request with a 128-token output cap. It returned an `inspect_source` function call (518 input tokens, 23 output tokens); the local core persisted the operation ID in an Eve-backed session and the worker exited successfully. The fixture used synthetic data only. Automated checks remain scripted and make no paid calls. This confirms the basic provider-to-core tool path, not model quality or production readiness. No Timestral weights were used.

Eve is a preview framework and may change. Keep it behind the bridge and re-evaluate package compatibility, persisted-session restart behavior, and sandbox controls before a production rollout.
