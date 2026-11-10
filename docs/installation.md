# Local installation and maintenance

The guided route uses a macOS user LaunchAgent, an installed wheel, a local SQLite workspace and Codex stdio MCP. It needs Python 3.12+, uv and the Codex CLI on PATH. The tested machine is Apple Silicon. The foreground route uses POSIX process supervision. The acceptance run here used macOS. See the [model guide](implementation/timestral.md) for the separate weights license and pin.

## Install the local artifact

Obtain the wheel, source archive, `uv.lock`, `requirements-mcp.txt` and `SHA256SUMS` from the same reviewed build. Run the following from a directory holding those files. Use a new, stable environment path for each version and keep it available to launchd and Codex.

```sh
shasum -a 256 -c SHA256SUMS
runtime="$HOME/Library/Application Support/Forecast Anything/runtimes/0.1.1"
uv venv --python 3.14 "$runtime"
uv pip sync --python "$runtime/bin/python" requirements-mcp.txt
uv pip install --no-deps --python "$runtime/bin/python" forecast_anything-0.1.1-py3-none-any.whl
forecast_cli="$runtime/bin/forecast-anything"
```

Build locally from the reviewed source with `uv build --out-dir dist` and `uv export --locked --no-dev --extra mcp --no-emit-project --format requirements-txt --output-file dist/requirements-mcp.txt`. Copy the reviewed `uv.lock` to `dist/uv.lock`, then run `(cd dist && shasum -a 256 *.whl *.tar.gz uv.lock requirements-mcp.txt > SHA256SUMS)`. The source archive excludes local environments, frontend dependencies and test outputs. The wheel installs the runtime and MCP uses the exported locked dependency set. A console build is a separate optional path.

## Set up the workspace and Codex

After reviewing the weights license, run this in Terminal as the logged-in desktop user:

```sh
workspace="$HOME/Library/Application Support/Forecast Anything/workspace"
"$forecast_cli" setup --workspace "$workspace" --prepare-model
workspace_config="$workspace/config.json"
"$forecast_cli" doctor --config "$workspace_config"
```

`setup` creates a private configuration and a `sources` folder on the first run. It loads pinned Timestral, installs and starts a user service, then registers its stdio server with `codex mcp add`. It prints the server name and confirms authenticated API access, a current worker heartbeat and a model loaded in that worker. On retry, it reuses the workspace config and an identical Codex registration. `--prepare-model` explicitly allows downloading missing weights. Omit it to require a usable cache. The worker uses its prepared cache offline.

The default port is 8000. To use a different free port, set `--port` when creating a workspace. If a workspace already exists, setup keeps its stored port, source grants and token. `--csv-root` accepts an existing directory. Use `--codex-bin /absolute/path/to/codex` if Codex CLI is elsewhere. The default server name is derived from the config path. Use `--codex-name` to choose a distinct name. Setup refuses to replace a different entry with the same name. To read your configured entries, use `codex mcp list`. Keep `config.json` private. The plist and the Codex entry contain the path to the config, and the credentials remain in that file. [OpenAI MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

For the step-by-step Desktop and logout/reboot checks, use the [acceptance procedure](research/phase-1-local-setup.md#desktop-and-login-cycle-manual-acceptance). In Codex Desktop, open the MCP settings and confirm the returned name is enabled. Restart the app if it was already running when you registered the entry. Ask it to call `get_diagnostics` on that named MCP server. A ready response means the adapter can reach the local API with its workspace credentials and the worker has loaded Timestral. The [assistant workflow](implementation/mcp.md) shows how to map an authorized CSV and submit a forecast.

## Choose a Timestral checkpoint

New workspaces use Timestral-28M by default. To use Timestral-123M, review the
[pinned weights terms](https://huggingface.co/mistralai/Timestral-123M/blob/5a147287addda85f6acd8da3fb8858fe9af7e8f7/LICENSE)
and create a workspace with its own directory and free port:

```sh
workspace="$HOME/Library/Application Support/Forecast Anything/workspace-123m"
"$forecast_cli" setup --workspace "$workspace" --port 8001 --timestral-model 123m --prepare-model
"$forecast_cli" model status --config "$workspace/config.json"
```

For foreground operation, pass `--timestral-model 123m` to `init`, then use
`model prepare --config PATH` and `up --config PATH --verify-model` with that
workspace's configuration. MCP `get_capabilities` reports the active checkpoint.
The guided setup reuses a workspace's saved choice. The ledger rejects a different checkpoint even when opened directly with `--db`. Use a new workspace when
choosing a different checkpoint so jobs, watches and evidence retain their
original model. Keep both workspaces on distinct ports if running them together.

## Operate the service

```sh
"$forecast_cli" service status --config "$workspace_config"
"$forecast_cli" service stop --config "$workspace_config"
"$forecast_cli" service start --config "$workspace_config"
"$forecast_cli" service restart --config "$workspace_config"
"$forecast_cli" service remove --config "$workspace_config"
```

`service install` writes the service definition in a disabled state until `start` enables it. `start` enables and bootstraps the job, and `restart` stops and starts it. Use `doctor` or `service status` to wait for readiness after starting. `stop` persists the disabled state across logins, then unloads the job. `remove` unloads and removes the managed plist. The configuration, sources and ledger remain available. To remove the assistant connection as a separate operation, use `codex mcp remove SERVER_NAME` and reopen Codex.

The enabled LaunchAgent is designed to run independently of Codex during the current macOS login session. It stops at logout. After a logout or reboot, macOS loads it when the same user next logs in. Availability before login is outside this mode. Keep the machine awake for scheduled work. See the [acceptance record](research/phase-1-local-setup.md) for which lifecycle cases were observed. [Apple launchd lifecycle](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)

The worker holds an OS lock keyed to the canonical ledger path, including one-shot execution. Use a local filesystem and one ledger path. A leftover `.worker.lock` file is normal; ownership is released by the OS when the process exits.

| Finding | Recovery |
| --- | --- |
| API unreachable | Run `service start` and check `runtime.stderr.log` beside the config. MCP `get_diagnostics` still returns a report while the API is stopped. The diagnostic probe authenticates with a signed challenge and does not send the bearer token. |
| Wrong process on port or `port_in_use` | Stop the process occupying that port, or choose another port for a new workspace. Retry setup with the existing workspace after freeing the configured port. |
| Invalid config or rejected authentication | Use the same private config for setup, service and Codex. Restore it from backup if malformed. Restart the MCP adapter after changes. |
| Worker stale or already running | Stop the other worker or supervisor for the same ledger. Start one service and check its logs. |
| Model missing, incompatible or unloadable | Run `model status --config PATH`. Reinstall the pinned dependencies if needed, run `model prepare --config PATH` with the intended cache, then restart the service. |
| Source permissions missing | Copy CSV files into an approved root. For a source already registered, use `permissions grant SOURCE_ID --config "$workspace_config"` and reopen the adapter. |
| Runtime version mismatch | Use the same installed wheel for the service and MCP. |
| Codex registration conflict | Review the existing entry or choose a different `--codex-name`. Unrelated entries remain available. |

For an upgrade, stop the previous service and worker, make a private consistent SQLite backup, install the new wheel in a new runtime directory, and replace the managed plist and Codex registration deliberately. Migration 010 adds worker diagnostics. For rollback to an artifact that predates migration 010, stop the new service and restore the pre-upgrade backup before starting the older version. Never start a second supervisor against the same workspace.

## Portable foreground mode

Use the installed CLI `init`, `model prepare`, `up --verify-model`, and `doctor` commands. Supply the same private config to `up`, `doctor`, and `mcp`. The terminal remains responsible for the supervisor. For checkout development and the optional console, see the [quickstart](quickstart.md).
