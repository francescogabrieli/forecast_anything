#!/bin/sh
set -eu

# Postgres and the policy proxy are healthy before Compose starts this service.
# Workflow schema migrations are idempotent; durable sessions survive restarts.
./node_modules/.bin/bootstrap
exec ./node_modules/.bin/eve start --host 0.0.0.0 --port 3000
