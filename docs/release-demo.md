# Reproduce the local assistant demo

This demo follows one synthetic question from a CSV snapshot through a real local Timestral forecast, its seasonal-naive comparison, a saved watch and a worker update after the MCP client disconnects. The browser page shows the recorded run and its limits; it does not call a model from the browser.

## Requirements

- Python 3.12 or newer and `uv`.
- The checked-in synthetic fixture at [`examples/release-demo/observations.csv`](../examples/release-demo/observations.csv).
- The optional MCP extra pinned by `uv.lock`; the runner requires official Python MCP SDK `2.3.0`.
- The pinned Timestral code and CPU dependencies. Model weights are separate from the package and must be prepared locally. Review the [Timestral weights terms](implementation/timestral.md) for your own use before preparing them.
- A free loopback port and a new private workspace path. The runner starts an API and worker, launches the installed MCP stdio command, sends a signed test webhook to a local receiver, and shuts down its process group when it exits.

## Run it

From the repository root:

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra mcp forecast-anything model status
uv run --locked --extra mcp forecast-anything model prepare
uv run --locked --extra dev --extra mcp python scripts/reproduce_phase7_demo.py \
  --workspace /private/tmp/forecast-phase7-demo-run \
  --output site/demo-data.json
```

For the clean-install acceptance, the local release candidate was installed into a Python 3.14 virtual environment outside the checkout using only the exported lock and wheel:

```sh
uv venv --python 3.14 /private/tmp/forecast-phase7-clean-install/.venv
uv pip install --python /private/tmp/forecast-phase7-clean-install/.venv/bin/python \
  -r dist/requirements-mcp.txt
uv pip install --python /private/tmp/forecast-phase7-clean-install/.venv/bin/python \
  --no-deps dist/forecast_anything-0.1.1-py3-none-any.whl
/private/tmp/forecast-phase7-clean-install/.venv/bin/python \
  scripts/reproduce_phase7_demo.py \
  --cli /private/tmp/forecast-phase7-clean-install/.venv/bin/forecast-anything \
  --workspace /private/tmp/forecast-phase7-clean-install/workspace \
  --output site/demo-data.json
```

The acceptance used an already prepared local Timestral weights cache; the weights are not part of either package archive. It proves that the wheel and pinned runtime dependencies can execute the full local journey outside the source checkout. It does not measure a first-time weights download.

Choose a new `--workspace` path for each run; an existing workspace is rejected. The script previews and explicitly confirms the fixture at its declared UTC cutoff, grants that synthetic source to the local assistant process, and stores the source and run records in the private workspace. It performs a candidate-bound historical backtest against the independent seasonal baseline, saves a question and watch, then submits a Timestral forecast. After that forecast is immutable, the script appends the declared 2026-10-24 observation and closes the MCP client. The independent worker discovers the change by polling; the runner waits for the new snapshot, successor run, inbox event and local test webhook, then reconnects over stdio to recover them.

The source's one-minute polling interval and its subscription exist only in this temporary workspace. The runner appends the observation, closes the MCP connection, and lets the independent worker poll the source, persist the new snapshot, issue the successor run, update the inbox and deliver the test webhook. It reconnects only after those records exist. The runner writes a sanitized, allowlisted `journey` record alongside the existing recorded examples in `site/demo-data.json`. It never writes the workspace token, webhook signing secret, private source path or SQLite database into that file. Build and serve the public site locally to review the page:

```sh
npm --prefix site ci
npm --prefix site run build
npm --prefix site run preview -- --host 127.0.0.1 --port 4176
```

Open `http://127.0.0.1:4176/`. The build renders the chart and tables from the fixture and recorded JSON into `site/dist/`; they are available without JavaScript. The exact question route in the local record is tied to the generated workspace and is not a public hosted result. The recorded run is dated: its target dates can pass, and a later worker restart may record that the horizon has expired.

## What the record proves

The journey records the fixture SHA-256, frozen snapshot and run IDs, Timestral weight and code revisions, device, first forecast and seasonal baseline, the matched backtest partitions, question revision, successor run, inbox event, test-webhook delivery and elapsed automation timings. The first-forecast timing starts when the script starts; it includes private workspace setup, local service startup/model load, CSV confirmation, backtest and first forecast. It excludes dependency installation, explicit model-weight preparation and human review. The listed manual prerequisites are dependency install, model-license review/preparation and choosing a fresh workspace path.

The values are hand-authored synthetic counts. The CSV assumes publication time equals event time and alternates 1 and 3; it does not represent a real demand process. Historical MAE on this toy series verifies the recorded comparison and replay path only. It does not establish real-world accuracy, calibration or general superiority. If the watch is marked provisional, the page and JSON retain its state and reason.

In the recorded run, Timestral's first point was 1.013 orders for 2026-10-24 and the independent seasonal baseline was 3.000. The candidate-bound comparison matched 30 origins in each of the exploration, selection and final partitions. Those unusually regular synthetic scores are a persistence/calculation example only. The appended value of 7 orders creates a new source snapshot and moves the successor target to 2026-10-25; there is no common target between the two forecasts, so the values are not directly comparable. The successor remains provisional with reason `insufficient_new_final_origins`: a single appended observation does not meet the 30-new-final-origin qualification requirement.

For a short live walkthrough, show the declared CSV assumptions, compare the first Timestral point with its baseline, open the saved question and exact linked view, then close the MCP client before appending the one synthetic row. The independent worker takes about one polling interval to publish the new snapshot, successor, inbox event and test webhook. Reconnect to show the provisional reason and the change summary. In the clean-install capture, the first forecast took 11.673 seconds, the full journey took 73.340 seconds, disconnected processing took 61.604 seconds, and reconnect recovery took 0.712 seconds. The run started with the pinned weights already cached. Dependency installation, model-weight preparation, license review and the operator's mapping review are not included; this single automated run is not a user-study result.

The SDK stdio path is distinct from browser rendering and MCP Apps hosts. `open_context_view` returns a textual summary and exact link in hosts that do not embed the UI. The MCP Apps reference-host observation is recorded separately from Codex Desktop; the latter's embedded rendering remains to be verified. See the [compatibility matrix](capabilities.md) and [MCP host evidence](research/phase-5-mcp-apps.md).
