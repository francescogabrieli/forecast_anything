import { expect, test, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const sourceCsv = resolve(process.cwd(), "../../tests/fixtures/console-e2e-actuals.csv");

async function visualSnapshot(page: Page, name: string) {
  if (!process.env.FA_VISUAL_OUTPUT) return;
  const directory = resolve(process.env.FA_VISUAL_OUTPUT);
  await mkdir(directory, { recursive: true });
  const html = await page.evaluate(() => {
    const copy = document.documentElement.cloneNode(true) as HTMLElement;
    copy.querySelectorAll("script").forEach((element) => element.remove());
    const originals = document.querySelectorAll("input, select, textarea");
    copy.querySelectorAll("input, select, textarea").forEach((element, index) => {
      const original = originals[index];
      if (element instanceof HTMLSelectElement && original instanceof HTMLSelectElement) {
        [...element.options].forEach((option, i) => option.toggleAttribute("selected", original.options[i].selected));
      } else if (element instanceof HTMLTextAreaElement && original instanceof HTMLTextAreaElement) {
        element.textContent = original.value;
      } else if (element instanceof HTMLInputElement && original instanceof HTMLInputElement) {
        if (element.type !== "password") element.setAttribute("value", original.value);
        element.toggleAttribute("checked", original.checked);
      }
    });
    copy.querySelectorAll('input[type="password"]').forEach((element) => element.removeAttribute("value"));
    const base = document.createElement("base");
    base.href = "http://127.0.0.1:4175/";
    copy.querySelector("head")!.prepend(base);
    return `<!doctype html>${copy.outerHTML}`;
  });
  await writeFile(resolve(directory, `${name}.html`), html);
  await page.screenshot({ path: resolve(directory, `${name}.png`), fullPage: true });
}

async function navigate(page: Page, label: string) {
  const menu = page.getByRole("button", { name: "Apri navigazione" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("navigation", { name: "Navigazione principale" }).getByRole("link", { name: label, exact: true }).click();
}

test("connects a source and issues its first forecast through the worker", async ({ page, request }) => {
  await page.addInitScript(() => { Date.now = () => Date.parse("2026-10-24T12:00:00Z"); });
  await page.goto("/#workspace");
  await page.getByLabel("Indirizzo API").fill("http://127.0.0.1:8000");
  await page.getByLabel("Token workspace").fill("local-e2e-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await page.getByLabel("ID della fonte").fill("first-sales");
  await page.getByLabel("Percorso o URL").fill(sourceCsv);
  await page.getByLabel("Data osservazione — campo", { exact: true }).fill("time");
  await page.getByLabel("Valore — campo", { exact: true }).fill("value");
  await page.getByRole("combobox", { name: /^Disponibile dal — origine/ }).selectOption("column");
  await page.getByLabel("Disponibile dal — campo", { exact: true }).fill("available_at");
  await page.getByLabel("Serie — campo", { exact: true }).fill("first-sales");
  await page.getByLabel("Unità — campo", { exact: true }).fill("count");
  await page.getByRole("button", { name: "Analizza fonte" }).click();
  await expect(page.getByText("Profilo pronto per la revisione.")).toBeVisible();
  await visualSnapshot(page, "sources");
  await page.getByRole("button", { name: "Attiva fonte" }).click();
  const calculate = page.getByRole("button", { name: "Calcola la prima previsione" });
  await expect(calculate).toBeVisible();
  await page.getByLabel("Percorso o URL").fill(`${sourceCsv}.changed`);
  await expect(calculate).toHaveCount(0);
  await page.getByLabel("Percorso o URL").fill(sourceCsv);
  await page.getByRole("button", { name: "Analizza fonte" }).click();
  await page.getByRole("button", { name: "Attiva fonte" }).click();
  await expect(calculate).toBeVisible();
  const refresh = page.waitForResponse((response) =>
    response.url().endsWith("/v1/sources/first-sales/refresh") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Aggiorna dati" }).click();
  expect((await refresh).status()).toBe(202);
  await expect(calculate).toBeVisible();
  await calculate.click();
  await expect(page.getByRole("heading", { name: "Osservatorio", exact: true })).toBeVisible();

  const api = "http://127.0.0.1:8000/v1";
  const headers = { Authorization: "Bearer local-e2e-token" };
  const events = await (await request.get(`${api}/events?limit=1000`, { headers })).json();
  const started = events.find((event: { kind: string; payload: { source_bindings?: Record<string, string> } }) =>
    event.kind === "run_started" && event.payload.source_bindings?.["first-sales"]);
  expect(started).toBeTruthy();
  const run = await (await request.get(`${api}/runs/${started.run_id}`, { headers })).json();
  expect(run.state).toBe("completed");
  expect(run.snapshot_ids).toContain(started.payload.source_bindings["first-sales"]);
  expect(run.results.forecast.point).toEqual([[3]]);
  expect(new Date(run.results.forecast.timestamps[0]).getTime()).toBeGreaterThan(new Date(run.as_of).getTime());
  await expect(page.locator(".run-card").getByText(`ID run: ${run.run_id}`)).toBeVisible();
  await expect(page.locator(".run-card .forecast-summary")).toContainText("first-sales");
  await navigate(page, "Home");
  await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
  await expect(page.locator(".recent-run-list")).toContainText("first-sales");
  await visualSnapshot(page, "home-connected");
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Osservatorio", exact: true })).toBeVisible();
  await expect(page.locator(".run-card").getByText(`ID run: ${run.run_id}`)).toBeVisible();
  await navigate(page, "Fonti");
  await page.getByRole("link", { name: "Vai al dettaglio", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Osservatorio", exact: true })).toBeVisible();
  await expect(page.locator(".run-card").getByText(`ID run: ${run.run_id}`)).toBeVisible();
});

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
  await page.goto("/#workspace");
  await page.getByLabel("Indirizzo API").fill("http://127.0.0.1:8000");
  await page.getByLabel("Token workspace").fill("local-e2e-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await page.getByLabel("ID della fonte").fill("sales");
  await navigate(page, "Osservatorio");
  await expect(page.getByRole("heading", { name: "Scoperte e aggiornamenti" })).toBeVisible();
  const api = "http://127.0.0.1:8000/v1";
  const headers = { Authorization: "Bearer local-e2e-token" };
  const initialEvents = await (await request.get(`${api}/events?limit=1000`, { headers })).json();
  const baseRunId = initialEvents.find((event: { kind: string }) => event.kind === "run_completed").run_id;
  const initialRunIds = new Set(initialEvents.filter((event: { kind: string }) => event.kind === "run_completed").map((event: { run_id: string }) => event.run_id));
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
  await navigate(page, "Fonti");
  await page.getByLabel("ID della fonte").fill("sales");
  await page.getByLabel("Percorso o URL").fill(sourceCsv);
  await page.getByText("Mappatura avanzata", { exact: true }).click();
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
  await navigate(page, "Osservatorio");

  await expect.poll(async () => {
    const events = await (await request.get(`${api}/events?limit=1000`, { headers })).json();
    return events.filter((event: { kind: string; run_id: string }) => event.kind === "run_completed" && !initialRunIds.has(event.run_id)).length;
  }).toBe(1);
  const revisedEvents = await (await request.get(`${api}/events?limit=1000`, { headers })).json();
  const notification = revisedEvents.find((event: { kind: string; run_id: string }) => event.kind === "run_completed" && !initialRunIds.has(event.run_id));
  expect(notification.payload.node_ids.slice().sort()).toEqual(["forecast", "question", "reference"]);
  const revisionBinding = revisedEvents.find((event: { kind: string; run_id: string }) => event.kind === "run_started" && event.run_id === notification.run_id).payload.source_bindings;
  expect(revisionBinding.sales).not.toBe(bindings.sales);
  await expect(page.locator(".event-list li").filter({ hasText: "run completed" }).filter({ hasText: notification.run_id })).toHaveCount(1);
  await expect(page.locator(".run-card").getByText(`ID run: ${notification.run_id}`)).toBeVisible();
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
  await page.getByText("Cronologia", { exact: true }).click();
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
  await page.getByRole("link", { name: `Input effettivi: ${evaluation.actuals_snapshot_id}`, exact: true }).click();
  await navigate(page, "Home");
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Osservatorio", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: `Snapshot ${evaluation.actuals_snapshot_id}`, exact: true })).toBeInViewport();
  await page.evaluate(() => window.scrollTo(0, 0));
  await visualSnapshot(page, "observatory");
  // Reopen the same home request after a different run was selected inside the observer.
  await navigate(page, "Home");
  await page.locator(`button[data-run-id="${baseRunId}"]`).click();
  await expect(page.locator(".run-card").getByText(`ID run: ${baseRunId}`)).toBeVisible();
  await page.locator(".event-list li").filter({ hasText: "run completed" })
    .getByRole("button", { name: `Apri run ${notification.run_id}`, exact: true }).click();
  await expect(page.locator(".run-card").getByText(`ID run: ${notification.run_id}`)).toBeVisible();
  await navigate(page, "Home");
  await page.locator(`button[data-run-id="${baseRunId}"]`).click();
  await expect(page.locator(".run-card").getByText(`ID run: ${baseRunId}`)).toBeVisible();

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
