// Test-only fixture for tests/e2e/serve_observatory.py; no private workspace data.
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
const api = "http://127.0.0.1:8000/v1";
const headers = { Authorization: "Bearer local-e2e-token", "Content-Type": "application/json" };
async function request(path, body) {
  const response = await fetch(api + path, { method: body ? "POST" : "GET", headers, ...(body ? { body: JSON.stringify(body) } : {}) });
  const value = await response.json();
  if (!response.ok) throw new Error(`Fixture API error: ${response.status}`);
  return value;
}
async function wait(jobId) {
  for (let i = 0; i < 100; i++) {
    const job = await request(`/jobs/${jobId}`);
    if (job.state === "completed") return job.result;
    if (["failed", "cancelled"].includes(job.state)) throw new Error("Fixture job failed.");
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error("Fixture job timed out.");
}
const events = await request("/events?limit=1000");
const source = events.find(event => event.kind === "run_started" && event.payload.source_bindings?.sales);
if (!source) throw new Error("Start tests/e2e/serve_observatory.py first.");
const run = await request("/jobs", { kind: "configured_run", key: "phase5-host-fixture", source_id: "sales", snapshot_id: source.payload.source_bindings.sales, selection: { provider: "seasonal_naive", horizon: 1, options: { period: 2 } } });
const runResult = await wait(run.job_id);
const directory = await mkdtemp(join(tmpdir(), "forecast-mcp-app-fixture-"));
const path = join(directory, "history.csv");
await writeFile(path, "time,value\n" + Array.from({ length: 20 }, (_, i) => `2026-10-${String(i + 1).padStart(2, "0")},${i + 1}\n`).join(""));
const registration = await request("/sources", { source_id: "phase5-host-history", kind: "csv", location: path, refresh_seconds: 86400, mapping: { event_time: "time", available_at: "time", value: "value", revision: { constant: "1" }, series_id: { constant: "sales" }, unit: { constant: "count" }, frequency: { constant: "1d" }, timezone: { constant: "UTC" }, calendar: { constant: "gregorian" }, missing_values: { constant: [""] } } });
await wait(registration.job_id);
const question = await request("/questions", { key: "phase5-host-question", title: "Domanda MCP Apps", meaning: "Prevedere le vendite", source_ids: ["phase5-host-history"], selection: { provider: "seasonal_naive", horizon: 1 } });
const backtest = await request("/jobs", { kind: "backtest", key: "phase5-host-report", source_id: "phase5-host-history", selection: { provider: "seasonal_naive", horizon: 1 } });
const report = await wait(backtest.job_id);
console.log(`FA_RUN_ID=${runResult.run_id}\nFA_QUESTION_ID=${question.question_id}\nFA_REPORT_ID=${report.report_id}`);
