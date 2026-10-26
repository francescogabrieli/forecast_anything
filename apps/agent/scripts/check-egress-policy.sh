#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../../.." && pwd)"
base_file="${script_dir}/../compose.egress-test-base.yaml"
policy_file="${script_dir}/../compose.agent-egress.yaml"
project="forecast-agent-egress-test"

cleanup() {
  docker compose -p "${project}" --project-directory "${repo_root}" \
    -f "${base_file}" -f "${policy_file}" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -p "${project}" --project-directory "${repo_root}" \
  -f "${base_file}" -f "${policy_file}" up \
  --build --abort-on-container-exit --exit-code-from agent
