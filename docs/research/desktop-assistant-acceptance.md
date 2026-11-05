# Desktop assistant acceptance — 5 November 2026

No commit or push performed. Desktop MCP reads and textual report presentation are accepted from the owner-supplied transcript. Full Desktop quit/reopen and MCP reread were confirmed by the owner at 17:09 Europe/Rome; graphical chart rendering is not claimed.

## Observed in this Codex chat

The configured Forecast Anything MCP tools are exposed to the assistant. Initial `list_sources` and `list_watches` returned `network_error` because the runtime was stopped. Starting the configured local API and worker restored both reads without restarting the chat. Local socket binding required sandbox escalation, which was approved.

Through the actual connected MCP tools, submitted a seasonal-naive period-2 forecast backtest on the existing synthetic `sales` source, horizon 2, period-1 comparator, two origins per partition. Job completed and persisted report:

- Backtest: `8a2f888fe105f38a43c5e80389ba262bfa697d47df13f4c62da4b3d0becdd6c1`
- Report: `05fd09da97a20c7b30c194f312a8195c2392c557b7448104edfc55bf768a4119`

`summarize_backtest`, `get_backtest` and `list_backtest_origins` agree: final model MAE 0, baseline MAE 1, four matched cells over two final origins. Final chart points cover 30–31 October and 1–2 November, with MAE 0 versus 1 in each window and matching evaluation IDs. Exploration retains one excluded origin; it is not silently dropped. These synthetic results establish no future accuracy or statistical significance.

The existing watch remains provisional, muted and non-operational. Summary correctly reports `linked_to_backtest=false`: this generic report does not qualify the watch. Its controls were not changed.

## Blocked and remaining

Computer-use explicitly refused access to `com.openai.codex` for safety reasons. No alternative UI automation was attempted. Therefore configuration screens, UI disconnect/reconnect, permission correction/revocation, automatic recurring updates, and visual chart rendering inside the Desktop assistant remain unverified. Reading chart points successfully is not evidence that a chart rendered.

Runtime was started for this verification using `.local/mcp-codex/config.json`. The backtest remains in the local workspace ledger.

## Owner-observed Desktop evidence

The owner supplied the transcript of a separate Desktop chat on 5 November, 16:57–16:59 Europe/Rome. `list_sources` and `list_watches` returned the existing source/watch. `summarize_backtest`, `get_backtest` and `list_backtest_origins` agreed; the assistant displayed the two final MAE points in a textual chart, retained exclusions and explained evidence limits and the horizon mismatch with the watch. A later `get_backtest` returned the unchanged completed report. This establishes the textual presentation path without the console, not native graphical rendering or restart of the MCP process. The answer omitted the explicit synthetic-data label; future presentations of this known fixture must include it.

## Reproducible acceptance added in this checkout

`tests/integration/test_assistant_acceptance.py` uses the official MCP SDK with independent API/worker and successive real stdio MCP processes in temporary workspaces. Only the test clock is controlled; the forecasting, source refresh, policy, ledger and tool implementations are production code.

- Registers an explicitly mapped CSV, corrects a missing timezone and verifies the resulting profile.
- Runs the actual CLI to persist grant/revoke, then verifies allowed/denied source profiling on successive MCP connections. Catalog metadata remains readable after revocation.
- Rejects a mismatched selection through the public `validation_error` envelope.
- Executes a candidate-bound backtest with 30 final origins on a 296-day synthetic alternating series. Model MAE is 0 and baseline MAE 2 for the one-day horizon. This fixture is distinct from the Desktop two-day-horizon report above.
- Compares stored partitions and all 30 final chart points with the MCP summary; verifies linked, operational watch and idempotent job replay.
- Stops and restarts API and worker, reconnects with no source grant and retrieves the identical report and summary. Source reads remain denied.
- Changes the source and advances the clock with no MCP process connected. The independent worker refreshes the source and creates a successor watch. Old candidate identity and historical report remain unchanged; old evidence is invalidated and neither old nor successor watch is silently treated as operational.
- Reads transition history with `limit=1` pagination. A larger page can legitimately exceed the full-result 64 KiB bound; callers should retry a smaller page.

Both new tests passed. The earlier full-suite run after correcting the fixture catalog passed 847 tests with one guarded Timestral skip. Final suite and static results are recorded below when completed.

## Final owner step (pending)

The owner agreed to do this after automated verification: fully quit Codex with Command-Q, reopen it and ask the Desktop assistant to read backtest `8a2f888fe105f38a43c5e80389ba262bfa697d47df13f4c62da4b3d0becdd6c1` through MCP. Record the actual response before closing the Desktop reconnection gate. The previous transcript confirms repeated reads only. Setup-screen interaction and graphical rendering remain unobserved; no automated test substitutes for those UI observations.

## Final verification for this increment

- Full Python suite: **849 passed, 1 skipped**, 52.81 seconds. The skip is the guarded real Timestral provider check.
- Ruff lint and format: passed (97 Python files formatted at check time).
- Generated core contracts: passed.
- Console typecheck and generated type snapshot: passed.
- `git diff --check`: passed.
- Connected workspace status after checks: API `available`, worker `running`.

The initial invocation without the virtualenv bin directory on PATH failed five CLI-launch checks; running with the documented environment resolved them. Two other failures exposed the test harness's stale 25-tool catalog; adding `summarize_backtest` restored checkout and installed-wheel journeys. No production behavior was altered by this increment. New acceptance tests and documentation remain local, uncommitted and unpushed.

## Desktop reopen failure and runtime supervision fix

The owner repeated the read after reopening Codex at 17:06 Europe/Rome: both MCP attempts returned `network_error`. The local CLI then reported API `unreachable`, worker `unknown`. The earlier foreground runtime had been launched from Codex's command session; that was insufficient to establish service continuity across app exit. The gate remains open until the corrected deployment passes the owner-observed reopen test.

Configured the existing foreground `up` command as user LaunchAgent `com.forecast-anything.local-runtime`, bootstrapped in `gui/501` from `.local/mcp-codex/runtime.launchagent.plist`. It runs the configured API/worker under launchd independently of Codex, with RunAtLoad, KeepAlive, private local config and local log files. No token is embedded in the plist. This bootstrap lasts for the current macOS login session; automatic startup after logout/reboot is not installed or claimed.

Verified `launchctl print` reports `running`, CLI reports API `available` and worker `running`, and the connected MCP `get_backtest` again returns the original completed report `05fd09da97a20c7b30c194f312a8195c2392c557b7448104edfc55bf768a4119`: final model MAE 0, baseline MAE 1, two evaluated origins/four matched cells. No forecast or evidence was recomputed to recover it.

To stop this session's supervised runtime, use `launchctl bootout gui/$(id -u)/com.forecast-anything.local-runtime`. To start again, bootstrap the private local plist. Do not start a second foreground worker against the same workspace while this agent is loaded.

## Owner-confirmed Desktop reopen — accepted at 17:09 Europe/Rome

Following the requested full quit/reopen after launchd setup, the owner supplied the new Desktop response: MCP `get_backtest` returned `ok: true`, `completed`, with unchanged report metrics. Exploration retains one evaluated/two matched cells and one excluded origin; selection and final each retain two evaluated/four matched cells. Model MAE 0, baseline MAE 1 and relative MAE 0 in all partitions; no failed origins.

This closes the pending Desktop quit/reopen/reconnection observation for the currently configured macOS login-session deployment. Combined with the earlier owner-observed summary/report/origin comparison and textual chart, the Desktop MCP read/reconnect and textual report presentation acceptance paths now pass. Historical pending/failure statements above describe prior attempts and are superseded by this result.

The broader release boundaries remain explicit: native graphical rendering and manual setup-screen interaction have not been observed; automatic startup after macOS logout/reboot has not been installed. The source permission, correction, qualification and independent-worker update paths have automated real-process evidence, not owner-observed UI evidence. External usability and general predictive accuracy are not established. No commit or push performed.

## Final live assistant workflow — accepted

The final journey used the MCP tools exposed to this Desktop chat against the supervised local runtime, the real clock and a separate explicitly synthetic CSV source, `acceptance-synthetic` (320 daily observations). Machine-readable tool evidence is in [desktop-assistant-live-evidence.json](desktop-assistant-live-evidence.json).

1. Registered the source with timezone intentionally omitted: profile retained `timezone` as unresolved. Re-registered with explicit UTC and verified no unresolved fields.
2. Submitted a candidate forecast using the frozen snapshot's exact origin. An earlier request using the current time was correctly rejected; snapshot and forecast origins must agree. The full 320-row snapshot exceeds the MCP result bound, so its origin metadata was inspected locally for this diagnostic step; the numerical execution remained core-owned.
3. Created a recurring watch and submitted its exact candidate-bound one-day backtest with 30 origins per partition. The core activated it with `qualified_final_backtest_evidence`. All 30 final origins had model MAE 0 versus baseline MAE 2. These are synthetic arithmetic checks, not general accuracy evidence.
4. Verified actual workspace CLI grant and revoke using two fresh official-SDK MCP processes: profiling succeeded after grant and returned `source_forbidden` after revoke. Existing `sales` grants were preserved. The already-connected Desktop MCP process retains its session grant until restart, as documented.
5. Changed the synthetic 4 November observation from 1 to 9, then allowed the watch's real deadline to arrive without a manual source-refresh tool call. The independent worker refreshed the source, invalidated the old candidate's evidence and created a non-operational provisional successor. Paginated history records creation, qualification, expiry and source revision.
6. Issued a second forecast on the original graph using the refreshed snapshot and called `summarize_watch_change`. For the common target 6 November, forecast/question values changed from 1 to 9 (delta +8 count), with a new snapshot identity. Seasonal period 2 repeats the changed 4 November value; the tool correctly describes an observed dependency change without asserting causality.
7. Reread the original backtest summary: historical metrics and linkage remain recorded, while current watch state is `evaluating/stale`, `candidate_invalidated=true`, `operational=false`. An historical activation decision is not presented as current qualification.

The two requested acceptance paths are complete for the supported local CSV, baseline, Desktop MCP and textual-report workflow. The owner's separate quit/reopen observation covers Desktop reconnection; the live tool journey covers source correction, forecast, qualification, automatic refresh and update explanation. Native graphical rendering and setup-screen automation are not supported acceptance claims for this path; text charts and structured report data are the verified presentation. Startup after macOS logout/reboot remains a separate installation task.

Independent review found two defects: late qualification replay could change the deterministic event payload, and enormous watch-history offsets overflowed SQLite. Both were reproduced with failing tests, fixed and re-reviewed with no remaining blocking finding. Retry now reuses the original persisted qualification event while retaining current watch relevance; history pagination bounds its SQLite offset. The final verification results supersede earlier counts below when recorded.

## Publication validation

The owner authorized commit, push and a PR after the initial no-commit acceptance work. The PR isolates backend/MCP workflows, generated contracts, source semantics and acceptance evidence from the remaining local public-site and console visual work. Independent re-review reported no remaining blocking findings after the two fixes.

- Exact prepared PR copy: 851 Python tests passed, one guarded Timestral skip (53.26 seconds).
- Exact prepared PR copy: 82 console component tests passed; typecheck, generated types and production build passed.
- Browser regression was updated to declare revision, frequency and timezone explicitly, retaining the assertion that source activation is blocked before semantic correction.
- Ruff lint/format, generated core contracts and staged diff whitespace checks passed.

The full working checkout's unrelated console visual changes have five component-test failures and remain outside this PR. The prepared PR's console tests pass; those remaining local changes are not covered by this acceptance claim.

Final browser verification on the exact prepared copy: **2 passed**, 7.8 seconds, including explicit temporal/revision correction and the two-source evaluation/update/scenario journey.
