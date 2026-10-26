# Complete roadmap step 3: A6 Eve agent

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task by task. On 2026-10-26 the user authorized committing and pushing this branch after verification. The bounded live GPT smoke was approved and completed on 2026-10-26.

**Goal:** Finish the remaining A6 work in roadmap step 3 and leave the autonomous observatory aligned with the approved provider architecture: GPT-6 Luna orchestrates Eve, while Mistral is used only for Timestral forecasting.

**Architecture:** A1–A5 and the core A6 gateway/durability are already implemented. Preserve those components; update only the existing Eve provider integration, its exact-origin network policy, coverage, and records. Eve remains self-hosted and durable; Python remains the authority for tools, budgets, evidence, promotion, and rejection.

**Tech Stack:** Python 3.12/3.14, Node 24, TypeScript, Eve 0.83.0, Vercel AI SDK, OpenAI Responses API, Docker Compose, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-24-forecast-anything-design.md`; provider choice: `docs/superpowers/specs/2026-10-26-openai-agent-model-design.md`; execution scope: `docs/superpowers/plans/2026-10-24-03-observatory-and-agents.md`, Task A6.

## Global Constraints

- Roadmap step 3 is the deliverable: an interruption preserves work, and a discovered question is promoted or rejected with evidence.
- A1–A5 are complete. Do not reimplement them.
- GPT-6 Luna is the configurable Eve orchestration model (`OPENAI_MODEL_ID`, default `gpt-6-luna`); Mistral is reserved for Timestral forecasting.
- Eve, the authenticated core bridge, the three declared tools, persistent operation budget, frozen-epoch validation, and durable Postgres sessions stay in place.
- Tests and CI use scripted responses; no paid provider calls in automated checks.
- Do not download Timestral weights or alter its license/parity gate.
- Run a live GPT smoke only after separate approval of the bounded request and cost estimate; this approval was received and the smoke completed on 2026-10-26.

## Review Focus

- Default and overridden model IDs are selected correctly without requiring an API key during tests.
- OpenAI calls use only `https://api.openai.com`; arbitrary provider destinations, Mistral chat calls, redirects, and direct outbound sockets stay blocked.
- A model-produced proposal cannot override the epoch, budget, schema, evidence, promotion policy, or core-issued operation ID.
- Restart preserves the same Eve session and core operation budget; duplicate calls remain idempotent.
- The approved bounded GPT smoke produced one live `inspect_source` tool call against a synthetic local core job and confirmed its persistent operation ID. Lack of credentials never causes CI to silently use another model.

## Current A6 Evidence (preserve; do not redo implementation)

- A1–A5 checklist items are complete in `.superpowers/sdd/2026-10-24-03-observatory-and-agents/progress.md`.
- A6 core gateway, schema validation, tool budget, restart behavior, policy and evidence tests are implemented. The existing suite covers accepted/rejected candidate evidence, budget limits, replay, bridge restart and core-issued operation IDs.
- Eve package, three-tool allowlist, generated contracts, durable session bridge, and Eve/Postgres restart check are implemented.
- The restart check now exercises an interrupted Eve turn: after persisting `inspectSource`, it restarts Eve/Postgres, resumes the same session, reuses the operation ID, submits a proposal, and verifies the same candidate and persistent budget. Its fixture advances Graphile Worker's stale lock beyond the four-hour expiry rather than waiting four hours.
- Existing complete offline verification is recorded in the A6 report. The old real Ministral smoke is historical only and does not validate the newly approved GPT provider.
- A bounded live GPT-6 Luna smoke completed on 2026-10-26: one 3,132-byte request, 128-token maximum output, 518 input tokens, 23 output tokens, and one persisted `inspectSource` operation against synthetic local data. It verified the basic provider-to-core tool path, not model quality or production readiness.

## Files

- Provider/model: `apps/agent/package.json`, `apps/agent/package-lock.json`, `apps/agent/agent/agent.ts`, `apps/agent/src/model-config.ts`, `apps/agent/tests/agent.test.ts`.
- Egress: `apps/agent/src/egress.ts`, `apps/agent/tests/egress.test.ts`, `apps/agent/egress-proxy/proxy.py`, `apps/agent/egress-probe/test.mjs`, `apps/agent/scripts/check-egress-policy.sh`.
- Runtime docs/decision: `apps/agent/README.md`, `docs/decisions/agent-runtime.md`, approved provider design doc.
- A6 status: `.superpowers/sdd/2026-10-24-03-observatory-and-agents/task-6-brief.md`, `.superpowers/sdd/2026-10-24-03-observatory-and-agents/progress.md`, `docs/roadmap.md` only if status text needs factual correction. Do not mark the commit step complete.
- Do not change Timestral provider implementation or its tests.

## Tasks

### Task 1: Align the existing Eve adapter with the approved GPT provider

- Add failing unit coverage for default `gpt-6-luna`, trimmed `OPENAI_MODEL_ID`, and blank fallback.
- Swap the agent-only `@ai-sdk/mistral` dependency for `@ai-sdk/openai` and update the npm lockfile.
- Configure `createOpenAI` with the exact-origin guarded fetch and `openai.responses(modelId)` in the existing Eve definition.
- Keep credentials confined to Eve's environment; do not add them to Compose logs, the core, tools, or Python configuration.
- Run the focused model tests, then agent typecheck, all agent tests, and Eve build.

### Task 2: Move service egress from Mistral chat to OpenAI

- Add failing egress coverage for allowed OpenAI requests, denied Mistral chat/arbitrary origins, denied redirects, and the core-origin separation.
- Change the app fetch allowlist, hardened proxy CONNECT destination, and Docker probe to `api.openai.com:443`.
- Run egress unit tests and `bash scripts/check-egress-policy.sh`; the test must confirm the OpenAI host is reachable through the proxy while arbitrary destinations and direct sockets fail.

### Task 3: Reconcile A6 records with the implemented roadmap and architecture

- Update the agent README and runtime decision record to describe OpenAI/GPT orchestration, `OPENAI_API_KEY` / `OPENAI_MODEL_ID`, the exact egress policy, self-hosted Eve/Postgres, and no paid CI calls.
- Keep the old Ministral request explicitly as superseded historical evidence; say it does not validate the selected GPT model. State that Mistral is used only for Timestral in the approved design.
- Update the A6 brief/progress status only from verified evidence: implementation and offline checks are complete, the implementation commits were pushed, and the separately approved bounded GPT smoke is complete. Keep model-quality and production-readiness claims outside the smoke result.
- Record the provider-specific live smoke as completed, keeping model-quality and production-readiness claims outside its scope.

### Task 4: Verify the complete roadmap step without paid calls

- Run agent install/audit, generated contracts, typecheck, all agent tests, Eve build, Docker egress, and Eve/Postgres interrupted-turn recovery checks.
- Run Python Ruff, format, contract drift, complete pytest suite, and package build; verify Python 3.12 and 3.14 when available.
- Confirm the existing coverage demonstrates the roadmap criterion: restart retains in-progress work; candidate promotion/rejection is derived from registered actuals-based evidence and cannot be forged by the model.
- Inspect the final diff and status; do not download Timestral weights. The GPT smoke was run separately after explicit user approval.
- Report any unavailable runtime checks and distinguish the verified tool-call path from model-quality and production-readiness claims.
