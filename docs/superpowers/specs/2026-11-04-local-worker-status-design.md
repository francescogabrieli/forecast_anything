# Local worker status design

## Intent

Make the configured local workspace status command report whether its API and background worker are available, so an assistant user can diagnose a setup that accepts jobs but does not process them.

## Goals

- Keep `forecast-anything status --config ...` the operator-facing check.
- Report worker liveness from the same SQLite database used by the API.
- Detect both an orderly stop and a worker that stopped updating its heartbeat.
- Keep health output small and free of workspace paths, tokens, job payloads, and source data.
- Keep worker liveness independent from job activity: an idle worker is healthy.

## Non-goals

- Installing or managing an operating-system background service.
- Supporting more than one worker per workspace.
- Claiming that a live heartbeat proves every provider or job will succeed.
- Changing the forecast ledger, MCP tool catalog, or published API contracts.

## Approaches

- A PID file written by the `up` supervisor is simple, but misses workers started with the standalone command and can misreport reused process IDs.
- Queue activity timestamps are not a liveness signal: a healthy idle worker has no job activity.
- **Chosen: a SQLite heartbeat written by the worker process.** The API exposes only a short state on its existing public health route. The configured status command first authenticates to the API, then reads that health state. This works for either `up` or separately started processes and reports a stale heartbeat after a crash.

## Behavior

The worker writes an instance ID and UTC timestamp at startup and every two seconds while running, including during long jobs. A heartbeat no older than ten seconds means `running`; an older heartbeat means `stale`; no row means `not_running`. Clean shutdown removes only that worker instance's row. `status` exits successfully only when both API and worker are running; its JSON keeps the `api` field and reports `worker` as `running`, `stale`, `not_running`, or `unknown` when API health cannot be read.

The existing release criteria in `docs/first-release.md` are the approved product requirements. These details are implementation choices for the first setup milestone.

## Constraints

- Python 3.12+, SQLite on local disk, FastAPI, no new dependency.
- The public `/health` route remains unauthenticated and reveals only API and worker state.
- Runtime behavior and documentation must not imply that a heartbeat proves forecast quality or worker job success.
