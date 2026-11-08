# Phase 3 — Guided conversation and recovery

## Scope and baseline

Base: `db8bb4c05e82829d9150faace7734299efcb6055` (merged phase 2). The candidate extends the existing local core, queue, questions, presentations and MCP adapter. It does not implement browser views, MCP Apps, notifications or per-watch scheduling controls.

`preview_csv_source` inspects an operator-root CSV before registration. It proposes column roles and gives sample-based unit/cadence hints without resolving semantics. The caller supplies the intended aware cutoff; the proposal version binds the canonical source spec, cutoff, content digest and proposal algorithm version. After an explicit human confirmation, `confirm_csv_source` validates every row from one byte capture, freezes the snapshot with the content digest in its assumptions, and atomically records the source revision and discovery job. The worker uses that frozen snapshot. Any changed content, mapping or cutoff needs another preview and confirmation.

The guided path rejects symlink paths and opens each path component without following replacement symlinks; its limits are 64 MiB and 100,000 rows. Source paths must be accessible to the runtime in a configured root; an assistant-visible attachment does not establish transfer. A stable key recovers the same committed job, including if the file disappears after acceptance. A replay in a new adapter process does not grant source access. A per-process random identifier lets a response lost after core commit be retried in the original process without losing its already-authorized temporary grant; an operator grant remains necessary after reconnect for source I/O, backtests and watch creation. Reads of saved operation and job state stay separate from resume authorization.

The shared source catalog and queue insertion use one SQLite write transaction. A failed enqueue rolls back the source revision; conflicting concurrent confirmations cannot supersede the winning revision. Historical snapshots and results remain immutable.

## SDK stdio transcript

The following records programmatic tool calls made by `scripts/check_timestral_mcp.py` against a fresh local API, worker, official MCP SDK and synthetic 360-row daily CSV. It is not a transcript of a human interaction or evidence of Desktop rendering. The script supplies the explicit mapping and confirmation in tool arguments; an assistant would ask the user to confirm those semantics rather than ask them to write JSON.

1. `get_capabilities`: required primary provider `timestral`; pinned model and weights revisions are recorded in the machine-readable report.
2. `preview_csv_source` with an empty mapping: timezone and other semantics remain unresolved. The completed mapping explicitly declares event and publication dates, revision, series, count unit, daily frequency, UTC, Gregorian calendar and empty-string missing values. A second preview binds it and the cutoff to the CSV digest.
3. `confirm_csv_source`: returns the source and durable discovery job. `get_job` completes; `summarize_snapshot` reports 360 observations and includes the confirmed content digest. No raw database inspection is used.
4. `create_question`, `create_operation`, `submit_operation`: the configured forecast runs with Timestral as primary and seasonal naive as separate comparator. `get_forecast_presentation` identifies `model` as primary. The run is linked to the question revision.
5. A candidate and recurring watch are saved and linked to the same question. A watch-bound backtest with 30 origins per partition completes; its presentation and summary agree. The recorded decision is `activate` for this synthetic fixture, not a general accuracy claim.
6. With the MCP client disconnected, the worker processes a changed synthetic source. On a new connection, `get_question_presentation` retrieves the question, `resume_operation` returns the same job and the same recorded run, and `summarize_watch_change` compares two recorded compatible runs. In the observed fixture the primary point changed from about 1.012 to 11.067 (+10.055); the seasonal reference changed from 3 to 13 (+10). The old watch became stale and invalidated. These are recorded differences, not causal claims.

The report `phase-3-guided-timestral-evidence.json` contains the synthetic IDs, pinned revisions, source digest, snapshot summary, forecast presentation, backtest presentation and change result. Reproduce with a prepared local Timestral model and unused paths:

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra dev --extra mcp python scripts/check_timestral_mcp.py \
  --workspace /tmp/forecast-phase3-new-workspace \
  --report /tmp/forecast-phase3-report.json
```

The process takes several minutes because it waits for the real watch refresh deadline. It starts and stops its own API and worker. No paid provider is called and no raw SQLite access is used to obtain the journey results.

## Other checks and limits

The complete Python suite passed with 943 tests and 2 skips; one subsequently added directory-symlink regression passed separately. A redundant later full rerun was interrupted after 544 passes and 2 skips, without reaching a final result. Ruff, generated contract checks, Python package build, console typecheck/84 tests/build and agent contract/typecheck/29 tests passed. The agent build could not finish because its Eve build requires an unavailable Docker daemon. Independent review identified and rechecked the replay, authorization, atomicity, file-size and symlink corrections; it did not find another blocking issue in the examined diff.

The focused tests cover ambiguous/irregular sampled mapping, a missing versus forbidden path, changed and malformed replacement files, changed cutoff, capture provenance, replay after file removal and reconnect, same-key conflicts, concurrent conflicting registrations, rollback on enqueue failure, response loss after core commit, revoked grant on backtest resume, symlink substitution, and file/row limits. The response-loss fault injection uses an in-process MCP client and API transport; the reconnect and authorization checks also use real SDK stdio processes. Existing stdio tests cover unsupported requests, insufficient backtest history and question recovery. Run focused checks with:

```sh
PYTHONPATH=src:tests/integration uv run --locked --extra dev --extra mcp pytest -q \
  tests/integration/test_guided_csv_stdio.py \
  tests/integration/test_operation_grant_stdio.py \
  tests/integration/test_operations_api.py tests/unit/test_guided_csv.py
```

MCP source grants are loaded at process start. Revoking a grant does not stop the worker or already scheduled reads. Muting a watch and pausing a question also do not stop those reads. There is no per-watch stop control in this phase; stopping the service stops all scheduled reads. Qualification and notification delivery are unchanged. The 64 MiB and 100,000-row limits apply to the new guided path, not all legacy source APIs.

## Codex Desktop observation and reopen status

In the Desktop chat, the assistant inspected the synthetic CSV via `forecast-phase3-review`, presented a complete mapping, cutoff and one-step horizon, and asked the user for confirmation. The user supplied the mapping. The first turn was interrupted after source capture was submitted; the subsequent turn recovered the same completed capture, created the question, completed a Timestral forecast and generic backtest, and linked both results to the question. The observed primary point was 23.03101348876953 and the baseline was 22, for 8 November 2026; the last source observation was 7 November. Final-partition historical MAE over 10 matched cases was 0.021102523803710936 for Timestral and 1.5 for the baseline. This is a synthetic fixture, not evidence of future accuracy. No recurring watch was created in this Desktop journey.

Recorded identities from that first Desktop journey:

- Question: `2bd4277c4278154be54a4b314d9492d9c4c6ebd261870907947c6f093238c6fb`
- Run: `0474ab84d03f9f209f4a398eee5ed5103af01c5290d1d9969c65be9e11ad6e01`
- Backtest: `3403f69a73026edaec1f4c238d83672a51bf265554e53dbd2c8aedc93bfba3fb`
- Report: `4bc02d3773efb60129904b5c07d7436277363ca5508a1b3e574477a09f7971d7`

After the owner reported closing Codex with `⌘Q` and reopening it on 8 November 2026, the existing MCP connection initially returned `network_error`: the foreground workspace service was no longer reachable. The assistant restarted the existing workspace service with `up --verify-model`, then read the question presentation, its revision-bound references, the stored forecast presentation and the stored backtest presentation through `forecast-phase3-review`. The question ID, run ID, backtest ID and report ID all matched the first Desktop journey above. The forecast still reported Timestral 23.03101348876953 and baseline 22; the final backtest MAEs remained 0.021102523803710936 and 1.5. These were reads of existing records: no question was created and no forecast or backtest was submitted again.

Computer control denied access to `com.openai.codex`, so the `⌘Q` and reopening are owner-reported; the subsequent MCP reads and their results were observed in the reopened chat. The SDK reconnect evidence above is separate. This check required restarting the service and does not prove that it survives an application restart, nor does it establish client attachment-transfer or embedded-view support.
