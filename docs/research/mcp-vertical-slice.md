# Local MCP vertical slice — verification

Historical baseline verification, 30 October 2026. The subsequent [configured forecast and frozen-backtest verification](forecast-evidence.md) extends the catalog to 19 tools and records current acceptance.

Verified 30 October 2026 against the local working tree. The owner requested no further commits or pushes; these changes remain unstaged. Two earlier commits, 448ac74 and 6be2353, predate that instruction.

## Result

The optional Python SDK v2.3.0 stdio server exposes 15 typed tools over the existing authenticated loopback API. The core retains numerical calculations, immutable runs, snapshots, evaluations and the durable queue. API and worker run independently of the MCP client. [Operating guide](../implementation/mcp.md).

The real-process acceptance path registers explicit CSV data, obtains candidate and snapshot identities, submits a baseline forecast, disconnects, lets the worker complete, reconnects and replays the same request without duplicating the run. It reads graph and snapshot evidence and records a single-run evaluation against later observations from the same source lineage. An isolated installed-wheel path exercises the same forecast/recovery flow outside the checkout.

In the historical synthetic evaluation fixture, the point forecast is 2 and the observed outcome is 4; the recorded MAE is 2 with one origin. This verifies calculation and evidence handling, not predictive quality. The guide’s separate current-clock SDK example was also executed against the real CLI API and worker.

## Verification evidence

| Check | Result |
| --- | --- |
| Final full Python suite (`uv run --locked --extra dev --extra mcp pytest -q`) | 665 passed, 1 skipped, 27.09 seconds |
| Final affected tool/stdio checks | 54 passed, 6.24 seconds |
| Real-process and installed-wheel acceptance before final metadata fix | 3 passed; subsequently included in the final full suite |
| Ruff and formatting | Passed |
| Generated core and console API contract checks | Passed; no API contract changes in the final metadata fix |
| Wheel and source-distribution build | Passed and refreshed after the final server changes |
| Optional SDK deliberately blocked | Baseline CLI works; missing-extra error is safe; SDK-only tests explicitly skip |
| Independent reviews | Three task gates approved; final whole-change review findings fixed and scoped re-review clean |

The single skipped test is the guarded real forecasting-provider check. No paid inference, model-weight download, desktop-host validation or public deployment formed part of this verification.

## Final review corrections

- Source-profile inspection is mutating and non-idempotent in MCP metadata: the existing API can queue discovery after source changes. A real protocol/API/worker regression proves the new durable job survives client disconnection and produces a snapshot, candidate epoch and graph.
- Source-I/O tools declare their external interaction honestly. The adapter itself contacts only the configured loopback API; the core may fetch an operator-approved stored HTTP source. No arbitrary network tool was added.
- The rejected-token test checks both tool errors and MCP stderr after shutdown. No actual credential leak was observed.

## Implementation decisions

- Parse the source-ID allowlist with other operator configuration, then enforce it at source-I/O tools. Moving this boundary later would require a configuration refactor, without changing product scope.
- CI installs the optional MCP extra and supports future stacked codex/** PRs. This widens CI coverage and adds optional test dependencies; base runtime dependencies stay unchanged.
- Use the official SDK’s public low-level Server to control safe validation errors and explicit error flags. This introduces SDK-major maintenance responsibility, without private SDK patches.
- Preserve the existing core profile behavior and expose it honestly as mutating. Clients may request permission for profile inspection; a genuinely read-only core route remains a separate future design.

## Remaining boundaries

The baseline is the default provider; Timestral remains explicitly opt-in with its separate code/weight conditions. MCP is a tool-access adapter, not an LLM or numerical model. The user’s assistant can use it without Eve or other project agents. Eve remains optional for autonomous discovery.

Desktop assistant compatibility, MCP HTTP-source registration, autonomous lifecycle tools and the dedicated public website/setup experience remain subsequent work. Configured forecasts and multi-origin backtesting are implemented in the subsequent increment linked above; their generic reports do not qualify discovery watches. The console remains optional. No forecast-quality, calibrated-probability, external-usability or production-readiness acceptance is implied.
