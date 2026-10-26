# OpenAI GPT for agent orchestration

## Intent

Use OpenAI GPT for the Eve discovery agent's language and tool orchestration. Mistral is reserved for the Timestral forecasting model; no Mistral chat model or API key is used by the agent. The Python core remains the authority for source access, budgets, candidate validation, and evidence.

## Goals

- Replace the agent's Mistral AI SDK adapter and `MISTRAL_*` configuration with the official OpenAI AI SDK provider and `OPENAI_API_KEY` / `OPENAI_MODEL_ID`.
- Keep Eve self-hosted, preserve the existing durable Postgres sessions and authenticated core bridge, and expose only the current three core tools.
- Use `gpt-6-luna` as the proposed initial model because OpenAI positions it for focused, high-volume tasks and documents function calling; keep the model ID configurable for later evaluation.
- Restrict agent-service egress to the configured OpenAI API endpoint and the internal core/database routes. CI continues to use controlled model responses and never calls a paid model.
- Run a synthetic live tool-call check only after the user approves its exact request and estimated cost.

## Non-goals

- Do not change or download Timestral weights, alter its license/parity gate, or route forecasts through a GPT model.
- Do not add multiple agents, automatic model fallback, or provider routing in this change.
- Do not move durable sessions or tool execution to a hosted OpenAI agent service.

## Approaches considered

1. **Direct OpenAI AI SDK provider inside Eve — recommended.** It fits the current Eve `LanguageModel` interface and keeps session persistence and tool execution self-hosted. Trade-offs: OpenAI API credentials and billing are required; egress configuration must target the OpenAI API.
2. **OpenAI hosted Agents API.** It offers managed orchestration, but would duplicate or replace Eve session behavior and move more state and control outside this repository.
3. **Provider-neutral adapter without a concrete provider.** It preserves future choice, but does not complete the user's chosen GPT direction or permit a real tool-call smoke yet.

The user selected a GPT model for orchestration. The direct OpenAI SDK integration is the implementation proposal. The model ID is `gpt-6-luna` (not “GPT-6 mini”); it is a configurable starting default, not a claim that it is the final best model for forecasting discovery. Use the Responses API explicitly for function calling. OpenAI currently lists standard rates of $0.10 per million input tokens and $0.50 per million output tokens for GPT-6 Luna.

## Constraints and security

- Store `OPENAI_API_KEY` only in the agent service environment; never pass it to the Python core, tools, logs, or source connectors.
- Use the OpenAI SDK's Responses API explicitly through the supported provider integration (`openai.responses(modelId)`) unless Eve's pinned version requires another documented compatible API surface.
- Preserve the existing exact-origin fetch wrapper and reject redirects. The hardened proxy must allow only the exact OpenAI API host and deny arbitrary egress.
- Keep provider calls out of unit tests and CI. The manual smoke uses synthetic-only data and bounded output, and runs only after separate user approval because API usage is billed separately from ChatGPT subscriptions.

## Verification

- Add tests for model selection/configuration and exact-origin egress using a scripted provider; no paid calls in CI.
- Run package typecheck, tests, contract drift check, Eve build, egress policy check, and Postgres/Eve restart check.
- Completed on 2026-10-26 after approval of the bounded request and cost estimate: one real GPT-6 Luna `inspect_source` tool call against a local synthetic core job; the core persisted its operation ID. The response used 518 input and 23 output tokens. Existing scripted/restart checks cover persistent budget behavior; this live smoke does not claim model quality or production readiness.

## Decision

Approved by the user on 2026-10-26: use `gpt-6-luna` as the configurable starting model via `OPENAI_MODEL_ID`. Mistral is reserved for Timestral forecasting. The separately approved bounded live smoke also completed on 2026-10-26; it verifies the basic tool-call path only.

## Sources

- [OpenAI GPT-6 Luna model](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [OpenAI models overview](https://developers.openai.com/api/docs/models)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [AI SDK OpenAI provider](https://ai-sdk.dev/providers/ai-sdk-providers/openai)
- [ChatGPT and API billing are separate](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform)
