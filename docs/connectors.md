# Source connectors and extension guide

The runtime has two source kinds: local CSV and bounded HTTP JSON GET. Both produce the same `Observation`/`Snapshot` contracts through explicit mapping and availability-aware freezing. The minimal CLI's normalized CSV loader is a separate convenience path; it requires exactly the six observation columns.

## Register an explicitly mapped source

The API's `POST /v1/sources` accepts `SourceSpec`; the library exposes `inspect_source` and `ingest_source` from `forecast_anything.sources.catalog`. A CSV example for a file visible to the core process:

```json
{
  "source_id": "sales",
  "kind": "csv",
  "location": "/absolute/path/observations.csv",
  "refresh_seconds": 3600,
  "mapping": {
    "event_time": "date",
    "available_at": "published",
    "revision": "edition",
    "value": "amount",
    "series_id": {"constant": "sales"},
    "unit": {"constant": "items"},
    "frequency": {"constant": "1d"},
    "timezone": {"constant": "UTC"},
    "calendar": {"constant": "gregorian"},
    "missing_values": {"constant": [""]}
  }
}
```

```csv
date,published,edition,amount
2026-10-21,2026-10-22,1,12
2026-10-22,2026-10-23,1,15
```

Observation roles map to a column name or a `{"constant": value}` object. Frequency, timezone, calendar and missing-value sentinels use explicit constants. The frequency mapping accepts `D`, `H` or a positive integer followed by `d`/`h`; provider requests use fixed UTC hourly/daily steps. Ingestion does not resample data. Use an IANA timezone and `gregorian` calendar; ambiguous/nonexistent local timestamps fail. Missing sentinels apply only to values. JSON `null` is missing only when explicitly listed.

`event_time` is when the observation applies; `available_at` is when it could first be used. Do not substitute the event timestamp for an unknown publication time without recording that assumption. Revisions distinguish corrections. Freezing excludes unavailable records and preserves the issued snapshot. A mapping with unresolved roles cannot ingest; inspection proposals never authorize execution.

In the library:

```python
from datetime import datetime, timezone
from forecast_anything.contracts import SourceSpec
from forecast_anything.sources.catalog import inspect_source, ingest_source

spec = SourceSpec.model_validate(source_configuration)
profile = inspect_source(spec)
if profile.unresolved:
    raise ValueError(f"Resolve source semantics: {profile.unresolved}")
snapshot = ingest_source(spec, datetime(2026, 10, 24, tzinfo=timezone.utc))
```

Here `source_configuration` is the decoded JSON object above, with a real local path. Registration persists configuration before inspection; an inspection error can leave the registration present. Re-registering changed configuration appends a catalog revision. API responses expose sanitized profiles and IDs, omitting locations and secret references.

## HTTP JSON

Use `kind: "http_json"` and a configured URL. The response must be a top-level array of scalar-valued objects, or configure `mapping.records_path` as a dotted object path to that array. For example, `"records_path": "data.rows"` selects `{"data": {"rows": [...]}}`. Nested record values, nonfinite numbers and absent paths fail.

The adapter performs GET requests with a 10-second timeout and a 5 MiB response bound. Redirects must preserve origin. HTTPS is required except for unauthenticated loopback HTTP sources. URLs cannot contain credentials; authenticated reads use `Authorization: Bearer` through an injected `secret_resolver(source_id, secret_ref) -> str`. The resolver must scope credentials to the requested source. The stock CLI does not provide arbitrary environment-secret lookup. CSV credentials are unsupported.

Sensitive fields and credential-shaped strings are filtered/redacted before profiling; this is not a guarantee that arbitrary source text contains no private information. Treat source data as untrusted and review exposed samples. There is no general source destination allowlist: restrict network/filesystem access at deployment boundaries. See [SECURITY](../SECURITY.md).

## Add a connector without changing the numerical runtime

Start with a synthetic local fixture and the existing `SourceSpec`, `Observation` and `Snapshot` contracts. Transport code belongs under `src/forecast_anything/connectors`; source interpretation/ingestion belongs under `src/forecast_anything/sources`. Dispatch currently occurs in `sources/profiling.py`; there is no generic connector plugin registry. A new `kind` requires updating the literal contract and regenerating JSON Schema/OpenAPI plus both console and agent consumers.

Document how the source identifies series, event/availability times, revisions, units, cadence, timezone, missing data and provenance. Keep credentials out of locations, profiles, errors and logs. Preserve caller-injected credential resolution and explicit source scope. Do not execute source contents or let an agent fetch a raw location.

Acceptance should cover successful inspection and ingestion, unresolved mapping, late revisions, missing/irregular data, timezone ambiguity, source unavailability, bounded reads, unsafe redirects and credential redaction where applicable. Assert immutable point-in-time snapshots and reuse the existing runtime for the fixture's forecast. Run the source tests and relevant API/worker integration checks, then regenerate contracts if the public schema changed. Follow [CONTRIBUTING](../CONTRIBUTING.md) for verification commands.

An additional forecasting model is a `ForecastProvider`, not a connector; numerical composition is an `Operator`. Their signatures and representation limits are in the [capability matrix](capabilities.md). Keep example-specific recipes outside the generic runtime and retain external dataset attribution in the recipe manifest.
