# Local installation and maintenance

The verified desktop workflow uses macOS on Apple Silicon, a local SQLite workspace and the stdio MCP adapter. Linux CI verifies Python 3.12 and 3.14, installed artifacts and synthetic browser flows. Treat Linux desktop integration, Windows and Intel Mac as unverified. See the [Timestral guide](implementation/timestral.md) for model preparation and licensing.

## Install the macOS login service

From the intended release revision, install the CLI in a versioned directory that will remain available after the checkout is moved. Use an existing private workspace configuration, or create one with the [quickstart](quickstart.md). The example assumes a local workspace in Application Support. Set the configuration path to your actual workspace before running it.

```sh
workspace_config="$HOME/Library/Application Support/Forecast Anything/config.json"
runtime_root="$HOME/Library/Application Support/Forecast Anything/runtimes"
runtime_revision="$(git rev-parse --short=12 HEAD)"
runtime_dir="$runtime_root/$runtime_revision"
UV_PROJECT_ENVIRONMENT="$runtime_dir" uv sync --locked --no-dev --no-editable --extra mcp
forecast_cli="$runtime_dir/bin/forecast-anything"
"$forecast_cli" model prepare
```

Save a user LaunchAgent. The label below manages one workspace per user. If that label is already installed, use the update procedure instead. The plist stores paths only. The existing private configuration remains the source of credentials and permissions.

```sh
agent_plist="$HOME/Library/LaunchAgents/com.forecast-anything.local-runtime.plist"
"$runtime_dir/bin/python" - "$forecast_cli" "$workspace_config" "$agent_plist" <<'PY'
import plistlib
import sys
from pathlib import Path

executable, config, destination = map(Path, sys.argv[1:])
config = config.resolve(strict=True)
destination.parent.mkdir(parents=True, exist_ok=True)
with destination.open("xb") as output:
    plistlib.dump({
        "Label": "com.forecast-anything.local-runtime",
        "ProgramArguments": [str(executable), "up", "--config", str(config)],
        "WorkingDirectory": str(config.parent),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "EnvironmentVariables": {"HF_HUB_OFFLINE": "1"},
        "StandardOutPath": str(config.parent / "runtime.stdout.log"),
        "StandardErrorPath": str(config.parent / "runtime.stderr.log"),
    }, output)
destination.chmod(0o600)
PY
plutil -lint "$agent_plist"
launchctl bootstrap "gui/$(id -u)" "$agent_plist"
"$forecast_cli" status --config "$workspace_config"
```

Wait for API and worker readiness, then configure the assistant's MCP command to use that same executable with `mcp --config` and the absolute configuration path. If the adapter was already running, restart the client to load its new executable. After a logout and login, check status again without starting the CLI manually. On reboot, the user service starts at login.

## Update or roll back

1. Prepare the new version in a separate runtime directory and verify `model prepare`. Keep the old executable and a copy of the installed plist.
2. Stop the existing service with `launchctl bootout "gui/$(id -u)/com.forecast-anything.local-runtime"`. Confirm the job has unloaded. With the worker stopped, back up the workspace database using SQLite's backup command and keep the backup private.
3. Change only the executable path in the plist to point at the new runtime. Validate it with `plutil -lint`, bootstrap it again and run `status`. Read a saved report through MCP and verify a forecast on synthetic data. Update the MCP command to the same version.
4. If you need to roll back, stop the new service and restore the previous plist and MCP executable. If the newer version changed the database format, restore the pre-update backup after preserving a copy of the newer database. Recheck API and worker status before resuming.

## Uninstall

Run `launchctl bootout "gui/$(id -u)/com.forecast-anything.local-runtime"`, confirm the job is no longer listed, and remove its plist from `~/Library/LaunchAgents`. Remove the associated MCP entry in your assistant, then remove the versioned runtime directory if it is no longer used. Archive the workspace separately if you want to retain the database, configuration and registered sources.
