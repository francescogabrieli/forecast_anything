#!/usr/bin/env bash
set -euo pipefail

agent_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="$(cd "${agent_dir}/../.." && pwd)"
temp_dir="$(mktemp -d)"
container_name="forecast-agent-restart-${$}"
core_log="${temp_dir}/core.log"
agent_log="${temp_dir}/agent.log"
worker_log="${temp_dir}/worker.log"
build_log="${temp_dir}/build.log"
core_db="${temp_dir}/core.sqlite3"
marker_file="${temp_dir}/after-inspect.marker"
db_port=""
core_port=""
agent_port=""
core_pid=""
agent_pid=""
worker_pid=""
bridge_token="restart-test-bridge-${$}"
core_token="restart-test-core-${$}"
workspace_token="restart-test-workspace-${$}"
uv_cache_dir="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/forecast-anything-uv-cache}"

free_port() {
  python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

stop_process() {
  local pid="$1"
  if [[ -n "${pid}" ]]; then
    kill -TERM "${pid}" 2>/dev/null || true
    wait "${pid}" 2>/dev/null || true
  fi
}

cleanup() {
  stop_process "${worker_pid}"
  stop_process "${agent_pid}"
  stop_process "${core_pid}"
  docker rm -f "${container_name}" >/dev/null 2>&1 || true
  rm -rf "${temp_dir}"
}
trap cleanup EXIT

wait_http() {
  local url="$1" pid="$2" log="$3"
  for _ in $(seq 1 120); do
    if curl --silent --max-time 1 "${url}" >/dev/null; then return; fi
    if ! kill -0 "${pid}" 2>/dev/null; then cat "${log}"; return 1; fi
    sleep 0.25
  done
  cat "${log}"
  return 1
}

wait_postgres() {
  for _ in $(seq 1 120); do
    if docker exec "${container_name}" pg_isready -U world -d world >/dev/null 2>&1; then return; fi
    sleep 0.25
  done
  docker exec "${container_name}" pg_isready -U world -d world
}

start_agent() {
  (cd "${agent_dir}" && exec env -u OPENAI_API_KEY -u MISTRAL_API_KEY \
    NODE_ENV=development \
    FORECAST_AGENT_SCRIPTED_MODEL=1 \
    FORECAST_AGENT_SCRIPTED_RESUME_MARKER="${marker_file}" \
    FORECAST_AGENT_BRIDGE_TOKEN="${bridge_token}" \
    FORECAST_AGENT_DATABASE_URL="${db_url}" \
    FORECAST_AGENT_CORE_URL="http://127.0.0.1:${core_port}" \
    FORECAST_AGENT_CORE_TOKEN="${core_token}" \
    WORKFLOW_POSTGRES_URL="${db_url}" \
    WORKFLOW_POSTGRES_WORKER_CONCURRENCY=10 \
    ./node_modules/.bin/eve start --host 127.0.0.1 --port "${agent_port}" >"${agent_log}" 2>&1) &
  agent_pid=$!
  wait_http "http://127.0.0.1:${agent_port}/" "${agent_pid}" "${agent_log}"
}

run_worker_once() {
  (cd "${repo_root}" && exec env \
    UV_CACHE_DIR="${uv_cache_dir}" \
    FORECAST_ANYTHING_WORKSPACE_TOKEN="${workspace_token}" \
    FORECAST_ANYTHING_AGENT_CORE_TOKEN="${core_token}" \
    FORECAST_ANYTHING_AGENT_URL="http://127.0.0.1:${agent_port}" \
    FORECAST_ANYTHING_AGENT_BRIDGE_TOKEN="${bridge_token}" \
    uv run --locked forecast-anything worker --db "${core_db}" --once --limit 1) \
    >"${worker_log}" 2>&1 &
  worker_pid=$!
}

python_helper() {
  (cd "${repo_root}" && UV_CACHE_DIR="${uv_cache_dir}" uv run --locked python \
    "${agent_dir}/scripts/restart-test-core.py" "$@")
}

core_port="$(free_port)"
agent_port="$(free_port)"
seed_json="$(python_helper seed --db "${core_db}" --csv "${temp_dir}/source.csv")"
job_id="$(node --input-type=module -e 'let s=""; for await (const c of process.stdin) s+=c; console.log(JSON.parse(s).job_id);' <<<"${seed_json}")"
candidate_id="$(node --input-type=module -e 'let s=""; for await (const c of process.stdin) s+=c; console.log(JSON.parse(s).candidate_id);' <<<"${seed_json}")"
python_helper make-due --db "${core_db}" --job-id "${job_id}" >/dev/null

(cd "${repo_root}" && exec env \
  UV_CACHE_DIR="${uv_cache_dir}" \
  FORECAST_ANYTHING_WORKSPACE_TOKEN="${workspace_token}" \
  FORECAST_ANYTHING_AGENT_CORE_TOKEN="${core_token}" \
  uv run --locked forecast-anything serve --db "${core_db}" --host 127.0.0.1 --port "${core_port}" \
  >"${core_log}" 2>&1) &
core_pid=$!
wait_http "http://127.0.0.1:${core_port}/health" "${core_pid}" "${core_log}"

docker run --detach --rm --name "${container_name}" \
  -e POSTGRES_USER=world -e POSTGRES_PASSWORD=world -e POSTGRES_DB=world \
  -p 127.0.0.1::5432 postgres:17-alpine >/dev/null
db_port="$(docker port "${container_name}" 5432/tcp | sed -E 's/.*:([0-9]+)$/\1/')"
db_url="postgres://world:world@127.0.0.1:${db_port}/world"
wait_postgres
(cd "${agent_dir}" && env WORKFLOW_POSTGRES_URL="${db_url}" ./node_modules/.bin/bootstrap)

(cd "${agent_dir}" && env NODE_ENV=development FORECAST_AGENT_SCRIPTED_MODEL=1 \
  ./node_modules/.bin/eve build >"${build_log}" 2>&1) || { cat "${build_log}"; exit 1; }
start_agent
run_worker_once

for _ in $(seq 1 200); do
  if [[ -f "${marker_file}" ]]; then break; fi
  sleep 0.1
done
if [[ ! -f "${marker_file}" ]]; then
  echo "scripted Eve model did not reach the post-inspect checkpoint" >&2
  cat "${worker_log}"
  cat "${agent_log}"
  exit 1
fi

first_session="$(docker exec "${container_name}" psql -U world -d world -Atc \
  "SELECT session_id FROM forecast_agent.discovery_sessions WHERE idempotency_key = '${job_id}'")"
if [[ -z "${first_session}" ]]; then echo "bridge session was not persisted" >&2; exit 1; fi
first_operations="$(python_helper operations --db "${core_db}" --job-id "${job_id}")"
node --input-type=module -e '
let s=""; for await (const c of process.stdin) s+=c;
const ops=JSON.parse(s);
if (ops.length!==1 || ops[0].tool!=="inspectSource") throw new Error(`expected one persisted inspect operation: ${s}`);
' <<<"${first_operations}"
echo "scripted Eve completed inspect_source and paused before proposing"

stop_process "${agent_pid}"
agent_pid=""
stop_process "${worker_pid}"
worker_pid=""
docker restart "${container_name}" >/dev/null
wait_postgres
db_port="$(docker port "${container_name}" 5432/tcp | sed -E 's/.*:([0-9]+)$/\1/')"
db_url="postgres://world:world@127.0.0.1:${db_port}/world"
# Graphile Worker makes abandoned locks eligible after four hours. Age the
# isolated test DB's lock so restart recovery can be verified without waiting.
docker exec "${container_name}" psql -U world -d world -v ON_ERROR_STOP=1 -c \
  "UPDATE graphile_worker._private_jobs SET locked_at = now() - interval '4 hours 1 second' WHERE locked_at IS NOT NULL" >/dev/null
start_agent
python_helper make-due --db "${core_db}" --job-id "${job_id}" >/dev/null
run_worker_once
for _ in $(seq 1 200); do
  final_operations="$(python_helper operations --db "${core_db}" --job-id "${job_id}")"
  operation_count="$(node --input-type=module -e 'let s=""; for await (const c of process.stdin) s+=c; console.log(JSON.parse(s).length);' <<<"${final_operations}")"
  if [[ "${operation_count}" == "2" ]]; then break; fi
  sleep 0.1
done
if [[ "${operation_count}" != "2" ]]; then
  echo "scripted Eve did not complete the proposal operation after restart" >&2
  cat "${worker_log}"
  cat "${agent_log}"
  exit 1
fi
stop_process "${worker_pid}"
worker_pid=""

# Poll the same completed turn until Eve publishes its terminal event. The
# first operation may be visible just before the session completion event.
job_state="pending"
for _ in $(seq 1 30); do
  run_worker_once
  if ! wait "${worker_pid}"; then cat "${worker_log}"; cat "${agent_log}"; exit 1; fi
  worker_pid=""
  job_state="$(python_helper job-state --db "${core_db}" --job-id "${job_id}" | node --input-type=module -e 'let s=""; for await (const c of process.stdin) s+=c; console.log(JSON.parse(s).state);')"
  if [[ "${job_state}" == "completed" ]]; then break; fi
  python_helper make-due --db "${core_db}" --job-id "${job_id}" >/dev/null
done
if [[ "${job_state}" != "completed" ]]; then
  echo "scripted Eve session did not complete after restart" >&2
  cat "${worker_log}"
  cat "${agent_log}"
  exit 1
fi

recovered_session="$(docker exec "${container_name}" psql -U world -d world -Atc \
  "SELECT session_id FROM forecast_agent.discovery_sessions WHERE idempotency_key = '${job_id}'")"
if [[ "${recovered_session}" != "${first_session}" ]]; then
  echo "session changed across restart: ${first_session} -> ${recovered_session}" >&2
  cat "${agent_log}"
  exit 1
fi

final_operations="$(python_helper operations --db "${core_db}" --job-id "${job_id}")"
node --input-type=module -e '
const before=JSON.parse(process.argv[1]);
const after=JSON.parse(process.argv[2]);
if (before.length!==1 || after.length!==2 || after[0].operation_id!==before[0].operation_id || after[1].tool!=="proposeCandidates") {
  throw new Error(`operation replay/budget mismatch: before=${process.argv[1]} after=${process.argv[2]}`);
}
' "${first_operations}" "${final_operations}"

python_helper verify --db "${core_db}" --job-id "${job_id}" \
  --candidate-id "${candidate_id}" --session-id "${first_session}"
echo "same Eve session resumed, reused its persisted inspect operation, and completed the candidate proposal"
