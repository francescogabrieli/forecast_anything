# Local Worker Status Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the configured workspace command report whether its API and worker are running, stopped, or stale.

**Architecture:** Persist one worker heartbeat in the workspace SQLite database. A background heartbeat runs independently of job activity, the existing `/health` response reads the heartbeat, and the local `status` command combines authenticated API access with that health result.

**Tech Stack:** Python 3.12+, SQLite, FastAPI, stdlib threading and HTTP client.

**Spec:** `docs/superpowers/specs/2026-11-04-local-worker-status-design.md`; product gate: `docs/first-release.md`.

## Global Constraints

- Use the configured workspace's shared local SQLite database; one worker per workspace.
- Do not expose credentials, local paths, source content, or job payloads in status output.
- Preserve the public `/health` route and keep it independent of forecast quality.
- The user selected Codex Desktop as the MCP host to try. A focused local process regression and a Codex CLI MCP smoke were run. Direct UI verification was attempted, but this environment denied automation access to the Codex Desktop app; CLI evidence is not treated as Desktop acceptance.

## Review Focus

- An idle worker must continue to report `running`, independent of job activity.
- A long-running provider call must not make a healthy worker appear stale.
- A crashed worker must report `stale`; SIGTERM clean stop must report `not_running` immediately.
- Stopping an older worker must not clear a newer worker's heartbeat.
- API auth failure or API unavailability must not falsely report worker health.

---

### Task 1: Persist and refresh worker liveness

**Files:**
- Create: `src/forecast_anything/migrations/009_worker_liveness.sql`
- Modify: `src/forecast_anything/store.py`
- Modify: `src/forecast_anything/worker.py`
- Modify: `src/forecast_anything/cli.py`

**Interfaces:**
- `Ledger.update_worker_heartbeat(worker_id: str, now: datetime) -> None`
- `Ledger.clear_worker_heartbeat(worker_id: str) -> None`
- `Ledger.worker_status(now: datetime, stale_after_seconds: int = 10) -> str`
- `Worker.liveness(interval_seconds: float = 2) -> ContextManager[None]`

- [x] Add migration 009 with one replaceable heartbeat row and advance SQLite `user_version` to 9.
- [x] Add UTC-validated, instance-guarded heartbeat write/clear methods and status calculation to `Ledger`.
- [x] Add a worker liveness context that refreshes in a daemon thread while jobs execute and clears only its own heartbeat on clean shutdown.
- [x] Wrap the continuous CLI worker loop in the liveness context; leave `--once` as a one-shot invocation without an active-service claim.
- [x] Update the existing migration and local-services process assertions for schema version 9 and `worker: running` after both services start.
- [x] Review migration sequencing and shutdown paths; add a process regression proving `up` drains a durable source job, including the initial liveness-loop deadlock, and rerun it after the fix.

### Task 2: Report liveness through the existing local status path

**Files:**
- Modify: `src/forecast_anything/api/app.py`
- Modify: `src/forecast_anything/workspace_config.py`
- Modify: `src/forecast_anything/cli.py`
- Modify: `docs/implementation/mcp.md`
- Modify: `docs/first-release.md`

**Interfaces:**
- `/health` returns `{"status":"ok","worker":"running|stale|not_running"}`.
- `check_api(config)` returns `{"api":"available|unreachable|authentication_or_api_error","worker":"running|stale|not_running|unknown"}`.

- [x] Return only the worker state from `/health`, while retaining its public access behavior.
- [x] Have `status` authenticate to `/v1/sources`, then read `/health`; report `unknown` if that health response cannot be read or parsed.
- [x] Return exit code 0 only when the authenticated API and worker are both available; preserve nonzero diagnostics otherwise.
- [x] Update setup guidance and first-release evidence to describe `stale` semantics and worker status limits.
- [x] Review the final diff and documentation links; local-services, packaged-wheel liveness/recovery, and Codex CLI MCP configured-forecast paths pass. Direct desktop-app UI acceptance remains open because the available automation cannot access that app.
