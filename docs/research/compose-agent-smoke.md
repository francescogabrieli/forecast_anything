# Clean Compose agent-stack smoke

Status: **passed for build, startup, and local health only** on 2026-10-26. This did not make an LLM request and does not establish provider quality or production readiness.

## Environment

- A fresh temporary workspace was created with `scripts/bootstrap_demo.py`.
- The Compose overlay used separate dummy workspace, bridge, and core tokens, a dummy URL-safe Postgres password, and `OPENAI_API_KEY=dummy-no-provider-call`.
- No real provider key or user data was used. No request was sent to OpenAI.
- Compose configuration validation used `docker compose ... config --quiet`.

## Results

The base stack and agent overlay built from the checkout and started together:

| Service | Result |
| --- | --- |
| core | running, healthy |
| worker | running |
| console | running |
| agent | running, healthy |
| agent egress proxy | running, healthy |
| workflow Postgres | running, healthy |

The local API `/health` endpoint and console `/` both returned HTTP 200. The workspace used synthetic/empty state only. The temporary Compose stack and its test volume were stopped and removed after verification.

## Boundary

This verifies clean container builds, service dependencies, startup, healthchecks, and local HTTP reachability. It does not verify a live model turn through this Compose stack: the provider credential was intentionally fake. A separate bounded GPT smoke had previously verified the provider-to-Eve-to-core tool path using synthetic local data. Timestral parity and M4 benchmark evidence are tracked separately.
