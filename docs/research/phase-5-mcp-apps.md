# Phase 5: MCP Apps contextual views

Base: `9c831200dceb1ca5c2b9e28f6ac33e67ca38292e` (`origin/main`, containing the approved phase 4 commit `bef8226c93ebd38db553957049641d5e43b1ad3e`). Worktree branch: `codex/phase-5-mcp-apps`. No push or phase 6 work is implied.

## Protocol and implementation

The implementation follows the [official MCP Apps overview](https://modelcontextprotocol.io/extensions/apps/overview) and its [`ui/initialize` lifecycle](https://github.com/modelcontextprotocol/ext-apps/blob/main/docs/overview.md). The Python server uses the locked MCP SDK 2.3.0 and advertises `io.modelcontextprotocol/ui` in modern MCP server capabilities. Legacy negotiation still exposes the resource and tool metadata, without relying on an extension capability field unsupported by that protocol version. The `open_context_view` tool takes the exact kind and record ID plus an operator-provided browser origin. It returns a bounded structured result with the existing shared presentation and verified workspace-bound browser link. Its text remains useful without rendering; if the presentation would exceed 64 KiB the response retains the text and browser link and marks the presentation unavailable. The tool and its resource advertise `ui://forecast-anything/context.html` and `text/html;profile=mcp-app`.

The resource is a bundled static React view using `@modelcontextprotocol/ext-apps` 2.0.4 and the phase 4 `ContextView`, chart and graph components. It receives the result via the host and requests optional detail only through host-mediated existing MCP tools. It contains no workspace credential or API URL; its CSP blocks direct network access. Resource CSP declares no external domains. A denied detail call leaves the report visible and explicitly marks missing origin details. The wheel contains the HTML bundle. `npm run build:mcp-app` regenerates it and `npm run check:mcp-app` checks reproducibility.

## Observed host and compatibility matrix

| Host / transport | Tools and text | Embedded rendering | Evidence |
| --- | --- | --- | --- |
| Official MCP Apps `basic-host` at ext-apps commit `19256f52cad5517ba8272581ed2e11d6a81273d5`, SDK 2.0.4, host identity `MCP Apps Host` 1.0.0 | Observed | Observed for exact run, question and report; provenance opened and browser actions relayed | Chromium; host Streamable HTTP via test-only `mcp-proxy` 6.9.1 to the Python server over stdio. MCP initialize requested `2025-11-25` with client capabilities `{}`; iframe `ui/initialize` used `2026-01-26`, app capabilities `{}`, followed by `ui/notifications/initialized`. Host supplies `serverTools`, `serverResources` and `openLinks` on the iframe channel. |
| Official Python MCP SDK 2.3.0, stdio | Observed, including text and browser fallback | Not a UI host | Real separate MCP process and local API/worker; tests cover the legacy protocol without an Apps capability field and modern negotiation with an advertised extension both without and with the supported MIME type; the modern server advertises `io.modelcontextprotocol/ui`. |
| Codex Desktop | Existing phase 3/4 tool behavior only; this change not observed in Desktop | **Not verified** | No rendering or interaction claim is made. |

The reference host is an actual host implementation, not a commercial chat client. Its upstream initialization does not explicitly advertise the Apps extension; the separate iframe handshake and rendered interactions were observed. UI resource failure was injected at `resources/read`: the host still exposed the tool's text and the link. A direct fetch from the sandbox was rejected by CSP. The local fixture uses a synthetic seasonal-naive provider, not real Timestral; it does not establish forecast accuracy. The browser origin in the test identifies the phase 4 browser destination; the fallback's independent browser-link behavior was tested in phase 4.

## Reproduction

Prepare the project: `uv sync --locked --extra dev --extra mcp`, then `(cd apps/console && npm ci && npm run check:mcp-app)`. The reference host setup below uses temporary directories, no production data and no public tunnel. Use separate terminals:

```sh
# A: synthetic API and independent worker, port 8000
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python tests/e2e/serve_observatory.py

# B: once, prepare the official reference host at the tested revision
git clone https://github.com/modelcontextprotocol/ext-apps.git /tmp/forecast-mcp-reference
git -C /tmp/forecast-mcp-reference checkout 19256f52cad5517ba8272581ed2e11d6a81273d5
cd /tmp/forecast-mcp-reference
npm ci --ignore-scripts
npm rebuild bun
npm run build
npm run build -w examples/basic-host
npm install --no-save --ignore-scripts mcp-proxy@6.9.1

# C: synthetic test token only; bridge binds loopback and launches the Python server
FORECAST_ANYTHING_WORKSPACE_TOKEN=local-e2e-token FORECAST_ANYTHING_MCP_API_URL=http://127.0.0.1:8000 FORECAST_ANYTHING_MCP_SOURCE_IDS='["sales","activity"]' /tmp/forecast-mcp-reference/node_modules/.bin/mcp-proxy --host 127.0.0.1 --port 3001 -- /absolute/path/to/forecast_anything/.venv/bin/forecast-anything mcp

# D: reference host (8080) and its sandbox origin (8081)
cd /tmp/forecast-mcp-reference/examples/basic-host
SERVERS='["http://127.0.0.1:3001/mcp"]' ../../node_modules/.bin/bun serve.ts

# E: from the project root, prepare synthetic records; use the three printed IDs
node apps/console/scripts/prepare-mcp-app-fixture.mjs
FA_RUN_ID=<run> FA_QUESTION_ID=<question> FA_REPORT_ID=<report> node apps/console/scripts/check-mcp-app-host.mjs
```

The host test uses the operator's synthetic API fixture and asserts the exact IDs, interactive provenance and browser link, blocked direct network, and text fallback after UI resource failure. Run it against a fresh fixture service so keys and source revisions are consistent. Stop the three local services afterward. The proxy is test-only, unauthenticated and bound to loopback; it is not a deployment recommendation.

## Recorded acceptance run

On the fresh synthetic fixture the reference-host script observed run `ff4361f964d54392a5af4f9b275d61fc83b665c7d43928c105162c6aa6b3b9b9` (primary 2 count, baseline 3 count), question `613550010db91512384576f5d010c601a55da99d84a22e953d51b2cacb473341`, and report `f7499cb34ba78ae6b80205142a7e673d080bb9e9e1c08aad57ae4e6a8cf305a2`. The report showed final-partition model and baseline MAE 1 over five evaluated origins. These IDs are fixture-specific; the browser assertions compare the rendered records and values with the live API rather than relying on those IDs.

The acceptance script opened provenance and relayed the exact browser destination through the host for all three records. It verified direct network access from the embedded view was blocked. With `resources/read` deliberately failed, it found the textual result and browser fallback in the reference host. SDK stdio tests covered absent, unsupported/unknown and advertised Apps capabilities; all retained the same structured result and browser fallback. An oversized presentation was reduced to a bounded result containing the browser link and an explicit unavailability reason.

Verification: Python **949 passed, 2 skipped**; console **99 passed**, typecheck, generated-type checks, deterministic MCP App bundle check and production build passed. The phase 4 browser regression suite passed **6 tests, 1 optional Timestral test skipped**. The installed-wheel test verified the UI HTML is packaged and served outside the checkout. Ruff, formatting and existing generated core-contract checks passed. The reference-host script passed all three rendered records and UI-load failure fallback on a fresh fixture.

After adding the modern extension capability announcement, 98 focused MCP and installed-wheel tests passed, and the three-record reference-host acceptance plus UI-load failure was repeated successfully. The full 949-test run preceded that final announcement change.
