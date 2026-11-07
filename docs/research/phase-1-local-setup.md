# Phase 1 — Installed macOS service and Codex setup

## Scope and baseline

The isolated candidate is based on `72dcc1e` plus the approved integrated Phase 0 patch. Snapshot commit `190fc23` records that exact base for the Phase 1 diff. The original checkout and connected Phase 0 service are outside the change set. The new runtime is `forecast-anything 0.1.1`, on Python 3.14, Apple Silicon macOS, with Codex CLI 0.160.0 and the official Python MCP SDK 2.3.0.

`setup` reuses private workspace initialization, Timestral preparation and the `up` supervisor. It validates an existing workspace, checks Codex registration conflicts, enables the per-workspace LaunchAgent and waits for authenticated readiness and model load in its worker. Registration uses the official `codex mcp` CLI. Retry preserves an existing matching registration and the workspace bytes. A failed final Codex registration leaves a running service available and a recoverable setup result.

`service` owns the LaunchAgent lifecycle. `up` reserves the listening socket before starting children. The worker locks the canonical ledger path in both continuous and one-shot modes. Migration 010 adds worker runtime state to the ledger. Its heartbeat is associated with the current supervisor; the public health response cannot by itself establish readiness. The CLI `doctor` and MCP `get_diagnostics` use the same bounded signed health probe, with independent permission counts. Service readiness also checks the LaunchAgent supervisor PID.

## Verification results

| Gate | Observed result |
| --- | --- |
| Installed artifact | Fresh venv outside the checkout with the locked MCP requirements. Pinned local weights were already cached. A separate empty-cache setup returned `model_not_prepared`. |
| Setup and Codex CLI | Ready on macOS 27.0 arm64. Codex CLI added the named stdio entry to an isolated profile. A second setup preserved workspace and Codex config bytes and retained the unrelated entry. A conflicting name failed before creating a workspace config. |
| Port, worker and interruption | The real occupied port returned `port_in_use`. A competing real one-shot worker returned `worker_already_running`. A focused regression interrupts child creation and checks that the supervisor reaps the API without launching a worker. The process tests also terminate a running supervisor and check that its API stops. |
| Diagnostics | CLI and SDK confirmed ready with the worker's loaded model. Wrong credentials returned `rejected`. With the service stopped, SDK stdio still returned `api=unreachable` and recovery guidance. Focused tests cover a forged health response and a peer that drips headers. |
| Service lifecycle | Real launchd stop unloaded the job and persisted the disabled state. Start and restart each preserved the exact run and replayed job identity. Remove preserved the ledger, config and stored run. |
| Real model | Run `098f18f0f6a13c4ae28b60eaaed58faa47e50500e57f8e131745fdbbcf372644`, job `fbddd5819ad3be0bac4f4bc24bc08aa8eb35a36226713cc48a73590c9a29c9b6`, point `0.9951812028884888`, primary `model`, separate seasonal reference. Provider revision `mistralai/Timestral-28M@49b26409ac87b5935539a5d8ffe7f397b720db47;code=a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff`. Inputs were synthetic. |
| Desktop preservation check | The existing Phase 0 Desktop MCP connection still returned its required Timestral capabilities. The new Phase 1 registration and forecast were exercised in Codex CLI and SDK respectively. |
| Automated suite | 919 Python tests passed, including model parity and installed-wheel smoke. The final targeted run passed 31 tests. Ruff lint and format and the two generated contract checks passed. |

The first real stop exposed that launchd can return from bootout before its job has finished exiting. The final lifecycle waits for unloading and socket and worker release. The independent review also prompted strict checks of the managed plist and loaded job, the listening socket reservation, early Codex conflict detection and a bounded signed diagnostic exchange.

## Reproduce the installed SDK proof

From the candidate checkout, build the artifacts or obtain the reviewed artifacts from the handoff. The [installation guide](../installation.md) has the exact commands for checking hashes, installing the wheel with locked dependencies and preparing Timestral.

The accompanying `check-installed-setup.py` is a macOS acceptance harness for a fresh private directory. Install the wheel and requirements into `TRIAL/runtime`, then run the script with that Python from outside the checkout:

```sh
cd "$trial"
"$trial/runtime/bin/python" "$harness" "$trial" "$report" "$(command -v codex)"
```

It uses the real GUI launchd domain with an isolated home for the plist, a separate `CODEX_HOME`, an available loopback port, prepared pinned local weights and synthetic CSV. It seeds an unrelated Codex entry, exercises setup twice, issues a real forecast through SDK stdio, stops the service, restarts it twice and reads the same run and replayed job. It removes only its test LaunchAgent and confirms the ledger can still read the immutable run. The saved JSON contains the provider pin, run identity, job identity and safe diagnostic fields.

## Desktop and login cycle manual acceptance

The phase's direct Codex result is CLI registration into an isolated profile. Desktop loading of the new entry, the Desktop forecast and quit/reopen, and physical macOS logout and reboot remain manual gates. The SDK proof and the earlier [Phase 0 Desktop record](phase-0-timestral.md) are separate.

1. From a terminal outside the checkout, install the reviewed wheel and locked dependencies in a fresh versioned environment using the [installation guide](../installation.md). Use a new workspace directory and a free port. Run setup under the same macOS user and Codex profile used by Desktop. For example:

   ```sh
   workspace="$HOME/Library/Application Support/Forecast Anything/desktop-phase1-review"
   workspace_config="$workspace/config.json"
   "$forecast_cli" setup --workspace "$workspace" --port 18431 \
     --codex-name forecast-phase1-review --prepare-model
   ```

2. Generate a recent, synthetic fixture in the authorized sources folder:

   ```sh
   "$runtime/bin/python" - "$workspace/sources/sales.csv" <<'PY'
   import sys
   from datetime import datetime, timedelta, timezone
   from pathlib import Path

   today = datetime.now(timezone.utc).date()
   rows = ["date,value,published"]
   for index in range(60):
       day = today - timedelta(days=59-index)
       rows.append(f"{day},{1 if index % 2 == 0 else 3},{day}")
   Path(sys.argv[1]).write_text("\n".join(rows) + "\n")
   PY
   ```

3. In Codex Desktop, confirm **forecast-phase1-review** appears and is enabled. If necessary, quit with Command-Q and reopen Codex. In a chat, ask Codex to call that server's `get_diagnostics` and show API, authentication, worker, model and runtime version. Expect `ready=true`, `worker=running`, `model=loaded` and version `0.1.1`.
4. Give Codex the absolute synthetic CSV path from step 2. Ask it to use that named MCP server to register source `phase1-desktop-sales` with `date` as event time, `published` as availability and `value` as the value. Set constants revision `1`, series `sales`, unit `count`, frequency `1d`, timezone `UTC`, Gregorian calendar and empty string as missing. Ask it to poll discovery for the snapshot ID, submit a configured forecast using `timestral`, horizon 1 and baseline period 1 with key `phase1-desktop-first`, poll the job and read the emitted run. Record the run ID, job ID, model provenance, target and value. Keep credentials out of the transcript and screenshots.
5. Quit Codex fully with Command-Q. In Terminal run `service status --config "$workspace_config"` and verify the worker remains ready. Reopen Codex and ask the named server to read the same run ID. Compare the recorded value, target and provenance.
6. Stop with `service stop --config "$workspace_config"`. In Desktop, call `get_diagnostics` again and expect `api=unreachable` with recovery guidance. Start with `service start --config "$workspace_config"` and wait for `doctor` to return ready. Reread the same run. Repeat after `service restart`.
7. With the service enabled, log out of macOS and log back in. Before opening Codex or manually starting the service, run `service status` and `doctor` and verify readiness. Repeat after reboot and login. Reread the stored run in Desktop. To test a persistent stop, stop the service, log out and back in, and check that it stays unloaded until explicitly started.
8. Clean up with `service remove --config "$workspace_config"` and `codex mcp remove forecast-phase1-review`. The test config, sources and ledger remain available for review.
