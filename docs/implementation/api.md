# Local observatory API

`create_app(ledger, runtime, workspace_token)` exposes the version-one API over the shared local Ledger. `forecast-anything serve --db PATH` uses the baseline provider and builtin operator registry, binds to `127.0.0.1:8000`, and reads the required workspace token from `FORECAST_ANYTHING_WORKSPACE_TOKEN`. `--host` and `--port` are explicit overrides. `forecast-anything worker --db PATH` processes the same durable A4 queue. `--once` runs one batch; lease duration defaults to 60 seconds and renews while work executes. Keep the SQLite database on local disk.

Every route except `GET /health` requires `Authorization: Bearer TOKEN`, including `/docs`, `/openapi.json`, capabilities, event history and SSE. Authentication never uses query strings. Domain failures return `{code, details}` with 404 for absent identities, 409 for immutable/idempotency conflicts, and 422 for invalid plans or input. Validation errors omit submitted values to protect credentials.

## Sources and discovery

`POST /v1/sources` accepts the real `SourceSpec`. Registration explicitly persists the source before inspection. Its response contains a sanitized profile, source revision, discovery `job_id` and `epoch_id`; source location and secret references are omitted. `GET /v1/sources` returns safe registration summaries, and `GET /v1/sources/{id}/profile` inspects only registered sources. Each new profile identity queues deterministic template discovery. Repeated reads reuse that job independently of the current clock. An inspection failure can leave the explicit registration present while returning a sanitized source error.

The worker rechecks the registered revision and profile, ingests resolved sources, checkpoints frozen inputs, and creates candidates through the trusted template compiler. Its job result names `candidate_ids` and `source_snapshot_ids`. Refreshed or newly discovered candidates have empty final-origin reservations and remain provisional. Neither forecast-only runs nor stale holdouts activate watches. Unresolved profiles produce non-executable proposals without inventing semantics. Protected HTTP sources require an explicitly injected A1 credential resolver; the stock CLI does not resolve secrets from arbitrary environment variables.

`POST /v1/candidates` accepts `CandidateRequest`: `template_id`, `source_ids`, `reason`, and optional `selection_method`. The server obtains profiles itself, compiles the proposal and registers a fresh provisional lineage. Clients cannot submit executable graphs, final-origin reservations, evaluations, or eligibility attestations as candidate evidence. `GET /v1/candidates/{id}` returns its issued contract.

`POST /v1/watches` takes `candidate_id` and timezone-aware `next_due_at`. It creates a provisional watch. `GET /v1/watches` and `PATCH /v1/watches/{id}` synchronize expiry and catalog revisions against the current authoritative clock, then reload current Ledger state. PATCH accepts only `muted` and/or `priority` (0–5). Operational is a derived response field. Resume is a typed queued control and goes through A4's guarded current-clock resume path.

## Jobs and immutable reads

`POST /v1/jobs` accepts a discriminated request:

- `run`: `key`, `graph`, `snapshot_ids` (registered source ID to stored snapshot ID), `as_of`, optional `previous_run_id`.
- `evaluation`: `key`, `run_id`, `actuals_snapshot_id`. This cannot submit a discovery attestation, and assumed outcomes cannot become observed evidence.
- `watch_resume`: `key`, `watch_id`. No raw watch transition is exposed.

Successful submission returns 202 and a safe `JobView`. Reusing a key with different content returns 409. Plans are validated against the runtime registries, snapshot metadata/calendar, registered source provenance, graph identity and lineage before enqueue. Evaluation actuals must carry a revision belonging to the run’s registered sources. Provider execution occurs only in the worker, outside SQLite transactions; runtime and Ledger revalidate the execution boundary. `GET /v1/jobs/{id}` exposes state, attempt and result/error without queue payloads, lease tokens or source configuration.

Immutable reads are `GET /v1/runs/{id}`, `/evaluations/{id}`, `/snapshots/{id}` and `/graphs/{id}?version=N`. Run evidence IDs remain the issued immutable evidence; later evaluation records are read separately. `GET /v1/capabilities` reports the installed provider/operator contracts and registered templates.

## Events and scenarios

`GET /v1/events?after=N&limit=100` reads durable global cursor history without consuming it. `Last-Event-ID` is also supported; when both are supplied, the greater cursor wins. `GET /v1/events/stream` provides SSE with `id: cursor`, typed event names, and JSON `EventRecord` data. `follow=false` returns the currently available replay and closes; the default keeps polling for new committed events. Disconnection does not delete history or change any other client's cursor. Reconnect using the last received ID and deduplicate by cursor/event ID. Run/outbox publication is atomic; publication and replay survive API and worker restarts.

`POST /v1/scenarios` accepts `ScenarioRequest(base_graph_id, base_version, label, source_overrides)`. The latest completed base run supplies the parent and original source bindings. Each override is a Snapshot with the same issue origin and source series/units; the server assigns new snapshot IDs, marks assumptions and revisions as assumed, and clones the graph under a new identity. The response names `scenario_id`, `graph_id`, `version`, `parent_run_id`, isolated `snapshot_ids`, and `job_id`. Repeating an identical request against the same parent is idempotent. Scenario runs carry their parent and scenario IDs, cannot overwrite base sources/graphs/runs, and cannot qualify as observed outcomes. Chaining scenarios is currently rejected.

## Generated contracts

`uv run python scripts/export_contracts.py contracts/v1` exports checked-in `schemas.json` and `openapi.json` directly from the Pydantic models and FastAPI app. Schemas use serialization mode so computed response fields are present. `--check` regenerates in a temporary directory and fails on byte drift; CI runs this check. Client packages should generate from these artifacts instead of maintaining separate schemas.

No external provider or external source dataset was needed to verify this implementation. The integration suite exercises a real loopback source/server and two CLI processes: it kills a worker during source ingestion, recovers the original leased attempt, creates a run via HTTP, checks immutable evidence IDs, restarts the server and replays independent event cursors.
