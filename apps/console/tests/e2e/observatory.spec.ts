import { expect, test, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

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
  await page.getByLabel("Token workspace").fill("wrong-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await expect(page.getByRole("alert")).toContainText("Token workspace non valido");
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
  await expect(page.getByRole("button", { name: "Attiva fonte" })).toBeDisabled();
  await page.getByLabel("Frequenza", { exact: true }).fill("1d");
  await page.getByLabel("Fuso orario", { exact: true }).fill("UTC");
  await page.getByLabel("Revisione — campo", { exact: true }).fill("1");
  await page.getByRole("button", { name: "Analizza fonte" }).click();
  await expect(page.getByRole("button", { name: "Attiva fonte" })).toBeEnabled();
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
  await expect(page.getByRole("heading", { name: "Sorveglianza e cronologia" })).toBeVisible();
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
  await page.getByText("Cronologia", { exact: true }).click();
  await page.locator(".event-list li").filter({ hasText: "run completed" }).getByRole("button", { name: `Apri run ${baseRunId}`, exact: true }).click();
  await expect(page.locator(".run-card").getByText(`ID run: ${baseRunId}`)).toBeVisible();
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
  await expect(page.getByText(`Nuovo risultato disponibile: ${notification.run_id}. Aprilo dalla cronologia.`)).toBeVisible();
  await expect(page.locator(".run-card").getByText(`ID run: ${baseRunId}`)).toBeVisible();
  await expect(page.locator(".run-card").getByText(`ID run: ${notification.run_id}`)).toHaveCount(0);
  await page.locator(".event-list li").filter({ hasText: "run completed" }).getByRole("button", { name: `Apri run ${notification.run_id}`, exact: true }).click();
  await expect(page.locator(".run-card").getByText(`ID run: ${notification.run_id}`)).toBeVisible();
  await expect(page.locator('.graph-node[data-modified="true"]')).toHaveCount(3);
  for (const id of ["forecast", "question", "reference"]) {
    await expect(page.locator(`[data-node-id="${id}"]`)).toHaveAttribute("data-modified", "true");
    await expect(page.getByRole("button", { name: new RegExp(`^${id}, .*modificato$`) })).toBeVisible();
  }
  const watches = await (await request.get(`${api}/watches`, { headers })).json();
  expect(watches).toHaveLength(2);
  expect(watches.some((watch: { candidate_invalidated: boolean; quality: string }) => watch.candidate_invalidated && watch.quality === "stale")).toBe(true);
  const staleWatch = page.locator(".watch-list li").filter({ has: page.getByText("Scaduta", { exact: true }) });
  await expect(staleWatch).toBeVisible();
  await expect(staleWatch).toContainText("In verifica");
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
  await page.getByText("Input e metodo", { exact: true }).click();
  const actualsLink = page.getByRole("link", { name: "Apri snapshot effettivi", exact: true });
  await expect(actualsLink).toHaveAttribute("href", `#snapshot-${evaluation.actuals_snapshot_id}`);
  await actualsLink.click();
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
  const actualsPath = `**/v1/snapshots/${evaluation.actuals_snapshot_id}`;
  await page.route(actualsPath, async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.fulfill({ response });
  });
  await page.locator(`button[data-run-id="${baseRunId}"]`).click();
  await expect(page.locator(".run-card").getByText(`ID run: ${baseRunId}`)).toBeVisible();
  await page.unroute(actualsPath);

  const forecastNode = page.getByRole("button", { name: /forecast, previsione/ });
  await forecastNode.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "Selezionato:" })).toBeVisible();

  await page.getByText("Opzioni avanzate: JSON degli snapshot").click();
  const scenarioInput = page.getByLabel("Snapshot ipotetici per fonte");
  const current = JSON.parse(await scenarioInput.inputValue()) as Record<string, { observations: Array<{ value: number | null }> }>;
  const source = "sales";
  current[source].observations = current[source].observations.map((item) => ({ ...item, value: 8 }));
  await scenarioInput.fill(JSON.stringify(current, null, 2));
  await page.getByRole("button", { name: "Mostra modifiche proposte" }).click();
  await expect(page.getByRole("region", { name: "Modifiche proposte" })).toBeVisible();
  await page.getByRole("button", { name: "Conferma e crea scenario" }).click();
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

test("opens the linked run after a cold browser connection and retains it on reload", async ({ page, request }) => {
  const api = "http://127.0.0.1:8000/v1";
  const headers = { Authorization: "Bearer local-e2e-token" };
  const workspaceResponse = await request.get(`${api}/workspace`, { headers });
  expect(workspaceResponse.ok()).toBeTruthy();
  const { workspace_id: workspaceId } = await workspaceResponse.json();
  const events = await (await request.get(`${api}/events?limit=1000`, { headers })).json();
  const runId = events.find((event: { kind: string }) => event.kind === "run_completed").run_id;
  const link = `/#/w/${workspaceId}/run/${encodeURIComponent(runId)}`;
  await page.goto(link);
  await expect(page.getByLabel("Token workspace")).toBeVisible();
  await page.getByLabel("Indirizzo API").fill("http://127.0.0.1:8000");
  await page.getByLabel("Token workspace").fill("local-e2e-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await expect(page.locator(".run-card").getByText(`ID run: ${runId}`)).toBeVisible();
  expect(new URL(page.url()).hash).toBe(link.slice(1));
  expect(page.url()).not.toContain("local-e2e-token");
  const streaming = page.waitForRequest(req => req.url().includes("/v1/events/stream?"));
  await page.reload();
  await expect(page.locator(".run-card").getByText(`ID run: ${runId}`)).toBeVisible();
  await streaming;
  expect(new URL(page.url()).hash).toBe(link.slice(1));
  const original = await (await request.get(`${api}/runs/${runId}`, { headers })).json();
  const graph = await (await request.get(`${api}/graphs/${original.graph_id}?version=${original.graph_version}`, { headers })).json();
  const bindings = events.find((event: { kind: string; run_id: string }) => event.kind === "run_started" && event.run_id === runId).payload.source_bindings;
  const submitted = await request.post(`${api}/jobs`, { headers, data: { kind: "run", key: "browser-new-result", graph, snapshot_ids: bindings, as_of: original.as_of } });
  expect(submitted.status()).toBe(202);
  const jobId = (await submitted.json()).job_id;
  await expect.poll(async () => (await (await request.get(`${api}/jobs/${jobId}`, { headers })).json()).state, { timeout: 20000 }).toBe("completed");
  const newRunId = (await (await request.get(`${api}/jobs/${jobId}`, { headers })).json()).result.run_id;
  expect(newRunId).not.toBe(runId);
  await expect(page.getByRole("status").filter({ hasText: `Nuovo risultato disponibile: ${newRunId}` })).toBeVisible();
  await expect(page.locator(".run-card").getByText(`ID run: ${runId}`)).toBeVisible();
  await page.goto(`/#/w/${workspaceId}/run/missing`);
  await expect(page.getByRole("alert")).toContainText("Risorsa non trovata");
  await page.goto(`/#/w/${"f".repeat(32)}/run/${encodeURIComponent(runId)}`);
  await expect(page.getByLabel("Token workspace")).toBeVisible();
  await page.getByLabel("Indirizzo API").fill("http://127.0.0.1:8000");
  await page.getByLabel("Token workspace").fill("local-e2e-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await expect(page.getByRole("alert")).toContainText("workspace diverso");
});

test("opens exact saved question and historical report across navigation and reload", async ({ page, request }, testInfo) => {
  const api = "http://127.0.0.1:8000/v1";
  const headers = { Authorization: "Bearer local-e2e-token" };
  const sourcePath = testInfo.outputPath("browser-history.csv");
  await mkdir(dirname(sourcePath), { recursive: true });
  await writeFile(sourcePath, "time,value\n" + Array.from({ length: 20 }, (_, i) => `2026-10-${String(i + 1).padStart(2, "0")},${i + 1}\n`).join(""));
  const source = await request.post(`${api}/sources`, { headers, data: { source_id: "browser-history", kind: "csv", location: sourcePath, refresh_seconds: 86400, mapping: { event_time: "time", available_at: "time", value: "value", revision: { constant: "1" }, series_id: { constant: "sales" }, unit: { constant: "count" }, frequency: { constant: "1d" }, timezone: { constant: "UTC" }, calendar: { constant: "gregorian" }, missing_values: { constant: [""] } } } });
  expect(source.status()).toBe(201);
  const backtest = await request.post(`${api}/jobs`, { headers, data: { kind: "backtest", key: "browser-history-test", source_id: "browser-history", selection: { provider: "seasonal_naive", horizon: 2, options: { period: 2 } } } });
  expect(backtest.status()).toBe(202);
  const jobId = (await backtest.json()).job_id;
  await expect.poll(async () => (await (await request.get(`${api}/jobs/${jobId}`, { headers })).json()).state, { timeout: 20000 }).toBe("completed");
  const report = await (await request.get(`${api}/backtests/${jobId}`, { headers })).json();
  const questionResponse = await request.post(`${api}/questions`, { headers, data: { key: "browser-question", title: "Domanda browser", meaning: "Prevedere le vendite", source_ids: ["browser-history"], selection: { provider: "seasonal_naive", horizon: 2 } } });
  expect(questionResponse.status()).toBe(201);
  const question = await questionResponse.json();
  const workspace = await (await request.get(`${api}/workspace`, { headers })).json();
  const questionLink = `/#/w/${workspace.workspace_id}/question/${question.question_id}`;
  const reportLink = `/#/w/${workspace.workspace_id}/report/${report.report_id}`;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(questionLink);
  await page.getByLabel("Indirizzo API").fill("http://127.0.0.1:8000");
  await page.getByLabel("Token workspace").fill("local-e2e-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await expect(page.getByText(`ID domanda: ${question.question_id}`)).toBeVisible();
  await page.goto(reportLink);
  await expect(page.getByText(`ID report: ${report.report_id}`)).toBeVisible();
  await expect(page.getByRole("table", { name: /Confronto e origini escluse/ })).toBeVisible();
  await page.reload();
  await expect(page.getByText(`ID report: ${report.report_id}`)).toBeVisible();
  await page.goBack();
  await expect(page.getByText(`ID domanda: ${question.question_id}`)).toBeVisible();
  await page.goForward();
  await expect(page.getByText(`ID report: ${report.report_id}`)).toBeVisible();
  await page.goto("/#questions");
  await expect(page.getByRole("link", { name: "Domanda browser" })).toBeVisible();
  await page.getByRole("link", { name: "Domanda browser" }).click();
  await expect(page.getByText(`ID domanda: ${question.question_id}`)).toBeVisible();
  expect(page.url()).not.toContain("local-e2e-token");
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.activeElement !== document.body)).toBeTruthy();
});

test("switches between separate workspaces and ignores a late rejected connection", async ({ page, request }) => {
  const headers = { Authorization: "Bearer local-e2e-token" };
  const first = await (await request.get("http://127.0.0.1:8000/v1/workspace", { headers })).json();
  const second = await (await request.get("http://127.0.0.1:8001/v1/workspace", { headers })).json();
  expect(second.workspace_id).not.toBe(first.workspace_id);
  const events = await (await request.get("http://127.0.0.1:8001/v1/events?limit=1000", { headers })).json();
  const runId = events.find((event: { kind: string }) => event.kind === "run_completed").run_id;
  await page.goto(`/#/w/${second.workspace_id}/run/${runId}`);
  await page.getByLabel("Indirizzo API").fill("http://127.0.0.1:8000");
  await page.getByLabel("Token workspace").fill("local-e2e-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await expect(page.getByRole("alert")).toContainText("workspace diverso");
  await expect(page.getByText(`ID run: ${runId}`)).toHaveCount(0);
  await page.getByLabel("Indirizzo API").fill("http://127.0.0.1:8001");
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  let observed!: () => void;
  const started = new Promise<void>(resolve => { observed = resolve; });
  await page.route("**/v1/capabilities", async route => {
    if (route.request().headers().authorization === "Bearer wrong-late-token") { observed(); await held; }
    await route.continue();
  });
  await page.getByLabel("Token workspace").fill("wrong-late-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await started;
  await page.getByLabel("Token workspace").fill("local-e2e-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await expect(page.getByText(`ID run: ${runId}`)).toBeVisible();
  release();
  await expect(page.getByText(`ID run: ${runId}`)).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.reload();
  await expect(page.getByText(`ID run: ${runId}`)).toBeVisible();
});

test("reuses and revokes the local connection across independent tabs", async ({ context, page, request }) => {
  const api = "http://127.0.0.1:8000/v1";
  const headers = { Authorization: "Bearer local-e2e-token" };
  const { workspace_id: workspaceId } = await (await request.get(`${api}/workspace`, { headers })).json();
  const events = await (await request.get(`${api}/events?limit=1000`, { headers })).json();
  const runId = events.find((event: { kind: string }) => event.kind === "run_completed").run_id;
  const link = `/#/w/${workspaceId}/run/${encodeURIComponent(runId)}`;
  await page.goto("/#workspace");
  await page.evaluate(() => {
    localStorage.setItem("forecast-anything.workspace-session.v1", JSON.stringify({ url: "http://127.0.0.1:8000", token: "legacy-secret" }));
    sessionStorage.setItem("forecast-anything.workspace-session.v1", JSON.stringify({ token: "legacy-secret" }));
  });
  await page.goto(link);
  await page.reload();
  await expect.poll(() => page.evaluate(() => [localStorage.getItem("forecast-anything.workspace-session.v1"), sessionStorage.getItem("forecast-anything.workspace-session.v1")])).toEqual([null, null]);
  await page.getByLabel("Indirizzo API").fill("http://127.0.0.1:8000");
  await page.getByLabel("Token workspace").fill("local-e2e-token");
  await page.getByRole("button", { name: /Apri il workspace/ }).click();
  await expect(page.getByText(`ID run: ${runId}`)).toBeVisible();
  const cookies = await context.cookies("http://127.0.0.1:8000");
  const browserCookie = cookies.find(cookie => cookie.name.startsWith("fa_browser_"));
  expect(browserCookie?.httpOnly).toBeTruthy();
  expect(browserCookie?.value).toBeTruthy();
  expect(browserCookie?.value).not.toBe("local-e2e-token");
  const staleCookie = `${browserCookie!.name}=${browserCookie!.value}`;
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("local-e2e-token");
  const questionResponse = await request.post(`${api}/questions`, { headers, data: { key: "cross-tab-question", title: "Domanda tra schede", meaning: "Prevedere le vendite", source_ids: ["sales"], selection: { provider: "seasonal_naive", horizon: 1 } } });
  expect(questionResponse.status()).toBe(201);
  const questionId = (await questionResponse.json()).question_id;
  const secondLink = `/#/w/${workspaceId}/question/${encodeURIComponent(questionId)}`;
  const other = await context.newPage();
  const apiRequests: string[] = [];
  other.on("request", req => { if (req.url().startsWith("http://127.0.0.1:8000/v1/")) apiRequests.push(req.headers().authorization ?? ""); });
  await other.goto(secondLink);
  await expect(other.getByText(`ID domanda: ${questionId}`)).toBeVisible({ timeout: 4000 });
  expect(apiRequests.length).toBeGreaterThan(0);
  expect(apiRequests.every(header => header === "")).toBeTruthy();
  expect(other.url()).not.toContain("local-e2e-token");
  await page.goto("/#workspace");
  await page.getByRole("button", { name: "Scollega questo browser" }).click();
  const rejected = await request.get(`${api}/workspace`, { headers: { Origin: "http://127.0.0.1:4173", Cookie: staleCookie } });
  expect(rejected.status()).toBe(401);
  await expect(page.getByLabel("Token workspace")).toBeVisible();
  await expect(other.getByLabel("Token workspace")).toBeVisible();
  await other.reload();
  await expect(other.getByLabel("Token workspace")).toBeVisible();
  await expect(other.getByText(`ID domanda: ${questionId}`)).toHaveCount(0);
});
