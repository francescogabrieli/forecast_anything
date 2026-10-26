import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

const sourceCsv = resolve(process.cwd(), "../../tests/fixtures/console-e2e-actuals.csv");

test("reviews two-source evaluation, revision notification and immutable scenario", async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let interruptedStream = false;
  let replayRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/v1/events?")) replayRequests += 1;
  });
  await page.route("**/v1/events/stream?**", async (route) => {
    if (!interruptedStream) {
      interruptedStream = true;
      await route.abort();
      return;
    }
    await route.continue();
  });
  await page.goto("/");
  await page.getByLabel("Indirizzo API").fill("http://127.0.0.1:8000");
  await page.getByLabel("Token workspace").fill("local-e2e-token");
  await page.getByLabel("ID della fonte").fill("sales");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await expect(page.getByRole("heading", { name: "Scoperte e aggiornamenti" })).toBeVisible();
  const api = "http://127.0.0.1:8000/v1";
  const headers = { Authorization: "Bearer local-e2e-token" };
  const initialEvents = await (await request.get(`${api}/events?limit=1000`, { headers })).json();
  const baseRunId = initialEvents.find((event: { kind: string }) => event.kind === "run_completed").run_id;
  const baseRun = await (await request.get(`${api}/runs/${baseRunId}`, { headers })).json();
  const baseGraph = await (await request.get(`${api}/graphs/${baseRun.graph_id}`, { headers })).json();
  expect(baseGraph.nodes.filter((node: { kind: string }) => node.kind === "source")
    .map((node: { config: { source_id: string } }) => node.config.source_id).sort()).toEqual(["activity", "sales"]);
  const bindings = initialEvents.find((event: { kind: string; run_id: string }) => event.kind === "run_started" && event.run_id === baseRunId).payload.source_bindings;
  expect(Object.keys(bindings).sort()).toEqual(["activity", "sales"]);
  expect(baseRun.snapshot_ids.slice().sort()).toEqual(Object.values(bindings).sort());
  // Period 2 repeats sales=2; the known-future activity fixture adds 10.
  expect(baseRun.results.forecast.point).toEqual([[12]]);
  expect(baseRun.results.reference.point).toEqual([[13]]);
  await expect(page.getByText(`${initialEvents.length} eventi unici`)).toBeVisible();
  expect(interruptedStream).toBe(true);
  await page.getByRole("button", { name: "Silenzia segnalazioni" }).click();
  await expect(page.getByRole("button", { name: "Riattiva segnalazioni" })).toBeVisible();

  await page.getByRole("button", { name: "Riattiva segnalazioni" }).click();
  await expect(page.getByRole("button", { name: "Silenzia segnalazioni" })).toBeVisible();
  await page.getByLabel("ID della fonte").fill("sales");
  await page.getByLabel("Percorso o URL").fill(sourceCsv);
  await page.getByLabel("Mappatura JSON").fill(JSON.stringify({
    event_time: "time",
    value: "value",
    available_at: "available_at",
    revision: { constant: "2" },
    series_id: { constant: "sales" },
    unit: { constant: "count" },
    frequency: { constant: "1d" },
    timezone: { constant: "UTC" },
    calendar: { constant: "gregorian" },
    missing_values: { constant: [""] },
  }, null, 2));
  await page.getByRole("button", { name: "Analizza fonte" }).click();
  await expect(page.getByText("Profilo pronto per la revisione.")).toBeVisible();
  await page.getByRole("button", { name: "Attiva fonte" }).click();
  await expect(page.getByText("Fonte attiva. Profilo riletto dal servizio.")).toBeVisible();

  await expect.poll(async () => {
    const events = await (await request.get(`${api}/events?limit=1000`, { headers })).json();
    return events.filter((event: { kind: string; run_id: string }) => event.kind === "run_completed" && event.run_id !== baseRunId).length;
  }).toBe(1);
  const revisedEvents = await (await request.get(`${api}/events?limit=1000`, { headers })).json();
  const notification = revisedEvents.find((event: { kind: string; run_id: string }) => event.kind === "run_completed" && event.run_id !== baseRunId);
  expect(notification.payload.node_ids.slice().sort()).toEqual(["forecast", "question", "reference"]);
  const revisionBinding = revisedEvents.find((event: { kind: string; run_id: string }) => event.kind === "run_started" && event.run_id === notification.run_id).payload.source_bindings;
  expect(revisionBinding.sales).not.toBe(bindings.sales);
  await expect(page.locator(".event-list li").filter({ hasText: "run completed" }).filter({ hasText: notification.run_id })).toHaveCount(1);
  await expect(page.getByRole("heading", { name: notification.run_id, exact: true })).toBeVisible();
  await expect(page.locator('.graph-node[data-modified="true"]')).toHaveCount(3);
  for (const id of ["forecast", "question", "reference"]) {
    await expect(page.locator(`[data-node-id="${id}"]`)).toHaveAttribute("data-modified", "true");
    await expect(page.getByRole("button", { name: new RegExp(`^${id}, .*modificato$`) })).toBeVisible();
  }
  const watches = await (await request.get(`${api}/watches`, { headers })).json();
  expect(watches).toHaveLength(2);
  expect(watches.some((watch: { candidate_invalidated: boolean; quality: string }) => watch.candidate_invalidated && watch.quality === "stale")).toBe(true);
  await expect(page.getByText(/In verifica · Scaduta/)).toBeVisible();
  await expect.poll(() => replayRequests).toBeGreaterThan(1);
  expect(new Set(revisedEvents.map((event: { cursor: number }) => event.cursor)).size).toBe(revisedEvents.length);
  await expect(page.locator(".event-list li")).toHaveCount(revisedEvents.length);
  await expect(page.getByText(`${revisedEvents.length} eventi unici`)).toBeVisible();

  // Each event has an open action; choose the single run-completion entry.
  const runButton = page.locator(".event-list li").filter({ hasText: "run completed" })
    .getByRole("button", { name: `Apri run ${baseRunId}`, exact: true });
  await expect(runButton).toBeVisible();
  await runButton.click();
  await expect(page.getByRole("heading", { name: "Come si compone il futuro" })).toBeVisible();
  await expect(page.locator(".run-card")).toBeVisible();
  expect(baseRun.evidence_ids).toEqual([]);
  const evaluations = await (await request.get(`${api}/runs/${baseRunId}/evaluations`, { headers })).json();
  expect(evaluations).toHaveLength(1);
  const evaluation = evaluations[0];
  const actuals = await (await request.get(`${api}/snapshots/${evaluation.actuals_snapshot_id}`, { headers })).json();
  expect(actuals.observations.every((observation: { series_id: string }) => observation.series_id === "sales")).toBe(true);
  expect(actuals.observations.find((observation: { event_time: string }) => observation.event_time.startsWith("2026-10-24")).value).toBe(4);
  expect(evaluation.status).toBe("evaluated");
  expect(evaluation.metrics.forecast.mae).toBe(8);
  expect(evaluation.run_id).toBe(baseRunId);
  await expect(page.getByRole("heading", { name: `Valutazione ${evaluation.evaluation_id}`, exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: `Input effettivi: ${evaluation.actuals_snapshot_id}`, exact: true })).toBeVisible();

  const forecastNode = page.getByRole("button", { name: /forecast, previsione/ });
  await forecastNode.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "Selezionato:" })).toBeVisible();

  const scenarioInput = page.getByLabel("Snapshot ipotetici per fonte");
  const current = JSON.parse(await scenarioInput.inputValue()) as Record<string, { observations: Array<{ value: number | null }> }>;
  const source = "sales";
  current[source].observations = current[source].observations.map((item) => ({ ...item, value: 8 }));
  await scenarioInput.fill(JSON.stringify(current, null, 2));
  await page.getByRole("button", { name: "Crea scenario" }).click();
  await expect(page.getByText("Scenario pronto. Il confronto usa soltanto timestamp e unità comuni.")).toBeVisible({ timeout: 25_000 });
  await expect(page.getByRole("heading", { name: "Confronto sulle date comuni" })).toBeVisible();
  const comparison = page.locator(".scenario-card");
  await expect(comparison.getByRole("heading", { name: "Assunzioni — scenario", exact: true })).toBeVisible();
  await expect(comparison.locator("li").filter({ hasText: "assumed:" })).toHaveCount(3);
  const forecastRow = comparison.getByRole("row").filter({ has: page.getByRole("cell", { name: "forecast", exact: true }) });
  await expect(forecastRow.getByRole("cell")).toHaveText(["forecast", "sales (count)", "24/10/2026", "12", "18", "+6"]);
  const unchanged = await (await request.get(`${api}/runs/${baseRunId}`, { headers })).json();
  expect(unchanged.run_id).toBe(baseRunId);
  expect(unchanged.results).toEqual(baseRun.results);
  expect(unchanged).toEqual(baseRun);
});
