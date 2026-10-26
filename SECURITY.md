# Security

This is a development release candidate for a local workspace. There is no published supported-version schedule, security contact address or hosted-service guarantee yet. The public owner and repository destination remain unresolved.

## Report a vulnerability

Do not post credentials, private source data or exploit details in a public issue. In the repository where you obtained this code, use private vulnerability reporting if it is enabled. Otherwise contact the maintainer through an existing private channel to arrange secure disclosure; no unverified email address is provided here. Share the affected revision, a minimal synthetic reproducer, expected impact and relevant sanitized logs. No response-time commitment is established yet.

## Operate the local workspace

- Bind the API to loopback unless you have configured an appropriate network boundary and TLS. Its workspace bearer token grants broad workspace access; this is not a multi-user authorization system. `/health` is unauthenticated; documentation, normal API routes and event streams require authentication.
- Generate a private workspace token. Keep it out of source control, URLs and logs. The console holds its token in memory. Restrict `FORECAST_ANYTHING_CONSOLE_ORIGINS` to the exact trusted console origins; an empty setting permits no cross-origin browser access. CORS is not an authorization boundary.
- Treat source registration as privileged: registered CSV locations are read by the core process and HTTP JSON sources can make outbound requests. The HTTP adapter is not a general network isolation or SSRF prevention layer. Restrict filesystem permissions and source-service network access to the sources you intend to allow.
- Keep SQLite files on local disk, protect their permissions and backups, and run one worker per workspace. The source catalog retains source locations and secret references even though API responses omit them. Sanitized samples can still contain sensitive business data; review what a source exposes before registering it.
- For authenticated HTTP JSON sources, inject a source-scoped credential resolver in the application. `secret_ref` names a credential; it is not the credential itself. The stock CLI does not resolve arbitrary environment secrets. Authenticated fetches require HTTPS; redirects must preserve origin and credential-shaped URLs are rejected.

## Optional services

The Eve bridge uses a dedicated worker-to-bridge token and a distinct agent-to-core token; neither is the workspace token. Only the agent service receives `OPENAI_API_KEY`. Keep model access separate from source credentials and retain persistent core budgets. Source content and model prose do not authorize execution or activation.

Use the documented [agent egress overlay](apps/agent/compose.agent-egress.yaml) and verify it for the deployment. The agent process must remain on an internal network with provider egress through its allowlisted proxy; the Docker sandbox's `deny-all` policy alone does not restrict the service process. Keep the core and Workflow Postgres reachable on the internal network. See [agent runtime decisions](docs/decisions/agent-runtime.md) for the tested boundary and restart limitations.

Timestral is optional and not accepted until its separate weight-license and real-parity gates are resolved. Do not enable its guarded real-model test or download weights as part of ordinary offline verification. External data, dependencies and weights retain their own terms and trust boundaries; keep revisions pinned and review changes before use.
