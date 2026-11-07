# MCP Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** connect a real MCP client to the existing local runtime, register a supported CSV, issue an immutable baseline forecast, read its graph/evidence and evaluate it against observed outcomes without a browser or paid inference.

**Architecture:** a Python stdio MCP server delegates to the existing authenticated loopback HTTP API. API and worker remain independently operated; the adapter never opens SQLite, implements a provider, starts a worker, or persists a parallel ledger. The initial client of reference is the official Python MCP SDK over a subprocess transport; desktop-host compatibility is not claimed until separately tested.

**Tech Stack:** Python 3.12+, Pydantic 2, httpx and the official `mcp` SDK stable v2 line (`mcp>=2,<3`, exact compatible releases resolved into `uv.lock` during implementation). Optional `mcp` package extra; no standalone FastMCP dependency. The official SDK documentation currently identifies v2 as stable; verify registry availability before dependency resolution and report a mismatch rather than silently substituting another SDK line.

**Spec:** [MCP-first product direction](../specs/2026-10-29-mcp-first-product-design.md), direction approved by the owner on 2026-10-29. This plan implements delivery step 1 and the existing single-run evaluation interface, not the subsequent multi-origin backtesting, public site or autonomy milestones.

**Delivery update (owner, 2026-10-30):** continue implementation locally without any further commits or pushes. Reviews use working-tree snapshots including untracked files. No new PR is created. Existing commits predate this instruction.

## Global Constraints

- The runtime remains the authority for source semantics, snapshots, graphs, computation, evidence, budgets and policy.
- The core and baseline work without LLM keys, model weights, Eve, Postgres or a mandatory cloud account.
- MCP does not supply a scheduler; accepted jobs live in the existing queue and survive a disconnected MCP client.
- First path is local: stdio, loopback API, one worker, SQLite on local disk. No public MCP endpoint or multi-tenant claim.
- Credentials and private source locations must not appear in tool results, error messages, logs or URLs.
- Mapping, availability, unit, cadence, timezone, revisions and assumptions stay explicit; no invented intervals, probabilities or automatic watch eligibility.
- Stable caller-supplied keys handle ambiguous submission responses; the adapter does not transparently retry mutating HTTP requests.
- Ordinary CLI/API installations do not import or require the optional MCP SDK.
- No paid provider call, public deployment, merge or registry publication is part of this plan.

## Review Focus

1. A timeout after core acceptance must not result in a new key or duplicate run: Task 1 tests lost responses, Task 3 verifies replay with the same key.
2. A model-controlled location must not grant arbitrary file/network access: Task 1 restricts new registrations to CSV under operator-configured roots, Task 2 applies the same checks to profile/refresh of existing sources.
3. Source data, validation errors, upstream HTML and connection exceptions must not leak secrets or private paths: Tasks 1 and 2 assert sanitized envelopes and stderr.
4. A large response or malicious identifier must not exhaust output or escape the intended API route: Tasks 1 and 2 test bounds and path-segment encoding.
5. Disconnecting an assistant must leave accepted work recoverable: Task 3 closes MCP after submission, lets the independent worker finish and reconnects to read the same emission.

## File map

- `src/forecast_anything/mcp_adapter/config.py`: validated process configuration and explicit source-root policy.
- `src/forecast_anything/mcp_adapter/client.py`: bounded authenticated loopback HTTP client and public error mapping.
- `src/forecast_anything/mcp_adapter/server.py`: typed MCP tool catalog and runtime delegation.
- `src/forecast_anything/mcp_adapter/__init__.py`: lightweight package marker; no SDK imports.
- `src/forecast_anything/cli.py`: lazy `mcp` subcommand dispatch only; existing modes retain behavior.
- `pyproject.toml`, `uv.lock`: optional SDK/httpx extra and reproducible resolution.
- `tests/unit/test_mcp_client.py`, `tests/unit/test_mcp_tools.py`: boundary and tool-contract tests.
- `tests/integration/test_mcp_stdio.py`: real SDK client, MCP subprocess, API and independent worker.
- `tests/integration/test_packaged_mcp.py`: installed-wheel stdio smoke outside checkout.
- `docs/implementation/mcp.md`: exact tool surface, configuration, setup and limits.
- `.github/workflows/ci.yml`: install/test the optional MCP extra in Python checks; run checks for stacked PRs too.
- `README.md`, `docs/quickstart.md`, `docs/capabilities.md`, `docs/roadmap.md`, `CONTRIBUTING.md`: current capability and verification updates.

## Task 1: Authenticated, bounded core adapter

**Files:** config/client modules, package marker, `tests/unit/test_mcp_client.py`, optional extra and lock.

**Interfaces:**

- `McpConfig.from_env() -> McpConfig`: `FORECAST_ANYTHING_MCP_API_URL` (default `http://127.0.0.1:8000`), required `FORECAST_ANYTHING_WORKSPACE_TOKEN`, `FORECAST_ANYTHING_MCP_CSV_ROOTS` (JSON array of absolute directory paths, default `[]`). Reject invalid config with a generic configuration code, not raw values.
- `CoreClient(config: McpConfig, *, transport: httpx.AsyncBaseTransport | None = None)` async context manager; `request(method: str, path: str, *, body: dict | None = None, params: dict | None = None) -> dict | list`.
- `CoreRequestError(code: str)` carries a stable safe public code; never stores raw bodies for rendering.
- `McpConfig.validate_csv(spec: SourceSpec) -> SourceSpec` accepts only CSV with no `secret_ref`, resolved existing files contained in a configured root, with symlink escape rejected. MCP and API must use the same local filesystem namespace; this is a local workspace boundary, not OS-level sandboxing.

- [x] Write failing tests for missing token, malformed roots, non-loopback host, userinfo/query/fragment/base path in API URL, root traversal/symlink escape, non-CSV kind and secret references. Permit only explicit `127.0.0.1` or `[::1]` loopback origins; no hostnames/DNS resolution or redirects.
- [x] Run `uv run --locked pytest tests/unit/test_mcp_client.py -q` and record failures before implementation.
- [x] Implement configuration and source guards. Add extra `mcp = ["mcp>=2,<3", "httpx>=0.27,<1"]`, resolve exact versions into the lock and use the optional extra when running MCP tests. Keep base dependencies unchanged.
- [x] Write failing HTTP tests using `httpx.MockTransport`: Authorization from configuration only, `trust_env=False`, `follow_redirects=False`, 15-second request timeout, 1 MiB maximum response bytes, 1 MiB maximum serialized request body, safe 401/404/409/422/network/invalid-response/too-large codes. Ignore raw upstream error bodies; never echo locations, headers or submitted data. One attempt per mutating request.
- [x] Implement bounded streaming reads, JSON validation and percent-encoded single identifiers (never concatenate unvalidated agent strings as URLs). All requests use fixed `/v1/...` routes; no generic request tool is exposed.
- [x] Run `uv run --locked --extra mcp pytest tests/unit/test_mcp_client.py -q` and Ruff for the touched modules; require all pass.
- [x] Commit the adapter with its tests and lock.

## Task 2: Typed stdio tools and CLI

**Files:** `server.py`, CLI lazy dispatch, `tests/unit/test_mcp_tools.py`.

**Interfaces:** `create_server(config: McpConfig) -> MCPServer`; `run_stdio() -> int` reads process config and serves stdio. Tool payload models reuse existing Pydantic contracts. SDK imports occur only in the MCP command/module. If the extra is missing, return exit 2 and a safe installation hint on stderr. Stdout is exclusively MCP protocol traffic.

Expose these fixed tools (names are part of this plan):

| Tool | Arguments | Delegation/result |
| --- | --- | --- |
| `get_capabilities` | none | GET capabilities; actual installed contracts |
| `list_sources` | `offset=0`, `limit=25` (1–100) | GET sources, stable source-ID sort, bounded page with next offset |
| `register_csv_source` | `spec: SourceSpec` | root/kind/secret guard, POST sources, sanitized SourceRegistration |
| `get_source_profile` | `source_id` | GET profile for an allowed source |
| `refresh_source` | `source_id`, `key` | POST refresh for an allowed source; preserve key |
| `get_job` | `job_id` | GET durable JobView |
| `get_candidate` | `candidate_id` | GET candidate, typed graph and support status |
| `submit_forecast` | `candidate_id`, `snapshot_ids`, `as_of`, `key` | Read executable candidate.graph; construct existing RunJobRequest, POST jobs; never alter graph or manufacture a snapshot |
| `get_run` | `run_id` | GET immutable RunRecord; no synthesized evidence |
| `get_graph` | `graph_id`, `version` (>0) | GET exact graph version |
| `get_snapshot` | `snapshot_id` | GET immutable snapshot within response bound |
| `list_run_evaluations` | `run_id` | GET recorded evaluations; empty is unevaluated, failure is an error |
| `get_evaluation` | `evaluation_id` | GET recorded EvaluationRecord |
| `submit_evaluation` | `run_id`, `actuals_snapshot_id`, `key` | Existing EvaluationJobRequest; no caller-supplied metrics or eligibility attestations |
| `get_events` | `after=0` (>=0), `limit=100` (1–1000) | GET durable events; return last cursor for continuation |

The tool layer returns a uniform typed envelope: success has `ok=true, data`; errors have `ok=false, code` and MCP error indication. Use the installed SDK's explicit CallToolResult mechanism if necessary so error status cannot be mistaken for a successful forecast. Schema-validation failures expose only field locations/types, never submitted values. Bound serialized tool output to 64 KiB; oversized results return `result_too_large` with no partial successful payload. Bounded reads may refuse a very large workspace rather than pretend full pagination over upstream data that could not be loaded. Document that limitation.

Existing source operations need an operator boundary too: add an explicit `FORECAST_ANYTHING_MCP_SOURCE_IDS` JSON string-array allowlist (default `[]`) for profile/refresh of pre-registered sources. Sources successfully registered through this process are also allowed for that process; after restart an operator must include their IDs in the allowlist. Listing sources exposes only API-safe metadata. Do not resolve registered locations through a new API endpoint. Client knowledge of a source ID alone must not grant permission to refresh a previously configured network/private source. Config validation belongs in Task 1's module with tests here.

- [x] Write failing tests for tool discovery, JSON input/output schemas, read-only vs mutating annotations and protocol stdout discipline.
- [x] Write failing cases for source allowlist enforcement, unsupported/non-executable candidate, explicit snapshot bindings/as-of, unchanged idempotency keys, no invented evaluation fields, encoded identifiers, output bounds and sanitized errors including validation failure.
- [x] Run the focused tests and record the expected failures.
- [x] Implement catalog and lazy CLI subcommand `forecast-anything mcp`; use official SDK v2 stdio transport, async client lifecycle and typed schemas. Declare no network access through MCP beyond the configured loopback API.
- [x] Run focused unit tests plus `tests/integration/test_cli.py`; verify the baseline CLI still works with the SDK import intentionally unavailable.
- [x] Leave the tool layer and tests uncommitted for working-tree review, per owner instruction.

## Task 3: Real protocol journey, installable artifact and documentation

**Files:** integration tests and MCP documentation; existing top-level docs listed in file map. Keep the public site/frontend unchanged.

**Interfaces:** official SDK `Client` connected with `StdioServerParameters` to `forecast-anything mcp`. The Python SDK client is the protocol reference, not an assertion that a desktop assistant was tested. Fixtures launch loopback API and worker in separate processes with a temporary local ledger, root and fixed synthetic CSV dates.

- [x] Write a failing stdio journey: initialize/negotiate, discover tools, register explicit CSV mapping under an allowed root, poll discovery job, obtain candidate and snapshot IDs, inspect snapshot origin, submit a one-step baseline forecast with a stable key.
- [x] Extend it to close MCP after acceptance, wait for the independent worker, reconnect with the explicit source allowlist, read job/run/graph/snapshot, repeat the original submission and assert same job/run and immutable result. Include a lost-response test at the HTTP boundary in Task 1 and replay here.
- [x] Extend the same registered history CSV with availability-aware observed outcomes, refresh that source with a new stable key and read the new actuals snapshot, submit evaluation and read persisted metrics. Preserve its catalog identity: an unrelated actuals source cannot authorize scoring. Assert assumptions cannot count as observed outcomes and unsupported multi-history scoring stays rejected. This tests single-run evaluation, not multi-origin backtesting.
- [x] Exercise protocol errors: unauthorized API, forbidden CSV, bad IDs, output limits and invalid mapping; assert no token, private location or raw source instruction appears in tool errors or stderr. Source content remains untrusted data, never an operational command.
- [x] Run `uv run --locked --extra dev --extra mcp pytest tests/integration/test_mcp_stdio.py -q`; require process timeouts and teardown so failures do not leave services running.
- [x] Add installed-wheel smoke outside checkout: build wheel, install its MCP extra using locked/pinned artifact dependencies, run official client tool discovery and real baseline journey through the installed executable. Assert no accidental checkout import or bundled credentials/weights.
- [x] Document three explicit processes (API, worker, MCP launched by host), environment/token configuration, allowed roots/source IDs, shared filesystem requirement, generic stdio launch configuration, tested SDK version, complete example request and actual measured result. Do not publish desktop-specific compatibility without exercising that host; do not call SDK-only tests a live-model demonstration.
- [x] Update README/capability matrix/quickstart/roadmap from planned to implemented only for verified operations. Keep multi-origin backtesting, HTTP registration through MCP, autonomous lifecycle controls, full site/setup wizard and desktop-host validation pending. Explain the upstream list/response bounds and reconnect source allowlist.
- [x] Update Python CI checks to install and retain `--extra dev --extra mcp` for validation; allow pull requests against `main` and `codex/**` so the stacked MCP PR receives checks. MCP-dependent test modules must skip explicitly when the optional extra is absent, while CLI missing-extra behavior remains tested.
- [x] Run `uv run --locked --extra dev --extra mcp ruff check src tests`, `ruff format --check src tests`, the full Python suite, generated-contract `--check` and `uv build`. Expected: all ordinary tests pass, guarded real-provider tests retain explicit skips, existing API schemas unchanged. No frontend changes: no extra browser build is necessary unless a regression calls for it.
- [x] Leave delivery and evidence uncommitted. Request independent working-tree review; resolve material findings. Do not commit, push, open a PR, merge or publish, per owner instruction.

## Execution and self-review

Three sequential deliverables share the typed adapter interface. Preserve the subagent-driven execution method selected by the owner for this project: one implementer per task, task review before the next task, then independent whole-branch review. No parallel implementers on shared files.

Coverage: all spec step-1 capabilities map to Tasks 1–3; existing evaluation is included, while multi-origin backtest, website and continuous-autonomy extension remain the subsequent roadmap steps. Type names/routes were checked against contracts.py and api/routes.py. All five Review Focus conditions have explicit owning tests. The source allowlist is deliberately process configuration, not a tool argument. The owner approved this plan in chat on 2026-10-29 ("confermo, avanti tutta").

## Primary references checked 2026-10-29

- [Official MCP Python SDK](https://py.sdk.modelcontextprotocol.io/): current stable v2 line, server/tool and client interfaces.
- [SDK v2 changes](https://py.sdk.modelcontextprotocol.io/whats-new/): client and stdio configuration changes; do not copy legacy v1 examples into v2 code.
- Existing [API contracts](../../implementation/api.md) and [capability boundaries](../../capabilities.md) define what the adapter may actually execute.

## Local completion — 2026-10-30

All three task reviews and the final scoped re-review passed. Final verification: 665 Python tests passed, 1 guarded provider test skipped; real stdio and installed-wheel acceptance passed; Ruff, generated API contracts and build passed. Profile inspection is correctly advertised as mutating because the existing core can enqueue discovery; source-I/O descriptions acknowledge explicitly approved stored HTTP sources. Delivery remains uncommitted and unpushed per owner instruction. See [verification evidence](../../research/mcp-vertical-slice.md).
