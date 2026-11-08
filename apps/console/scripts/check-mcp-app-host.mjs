// Run against the official MCP Apps basic-host and a synthetic local workspace.
// Supply FA_RUN_ID, FA_QUESTION_ID and FA_REPORT_ID; see phase-5 report.
import { chromium, expect } from "@playwright/test";

const host = process.env.FA_MCP_HOST ?? "http://localhost:8080";
const browserOrigin = process.env.FA_BROWSER_ORIGIN ?? "http://127.0.0.1:4173";
const targets = [
  ["run", process.env.FA_RUN_ID, "ID run"],
  ["question", process.env.FA_QUESTION_ID, "ID domanda"],
  ["report", process.env.FA_REPORT_ID, "ID report"],
];
if (targets.some(([, id]) => !id)) throw new Error("Set FA_RUN_ID, FA_QUESTION_ID and FA_REPORT_ID.");
const browser = await chromium.launch({ headless: true });
try {
  for (const [kind, id, label] of targets) {
    const apiPath = { run: "runs", question: "questions", report: "reports" }[kind];
    const response = await fetch(`http://127.0.0.1:8000/v1/${apiPath}/${id}/presentation`, { headers: { Authorization: "Bearer local-e2e-token" } });
    if (!response.ok) throw new Error(`Fixture presentation unavailable: ${kind}`);
    const expected = await response.json();
    const page = await browser.newPage();
    await page.addInitScript(() => { window.open = url => { window.__openedUrl = String(url); return null; }; });
    await page.goto(host);
    await page.waitForSelector('option[value="open_context_view"]', { state: "attached" });
    await page.waitForTimeout(300);
    await page.locator("textarea").fill(JSON.stringify({ kind, resource_id: id, browser_url: browserOrigin }));
    await page.getByRole("button", { name: "Call Tool" }).click();
    const frame = page.frameLocator("iframe").frameLocator("iframe");
    await expect(frame.getByText(`${label}: ${id}`)).toBeVisible({ timeout: 15000 });
    if (kind === "question") await expect(frame.getByRole("heading", { name: expected.question.title })).toBeVisible();
    if (kind === "run") {
      const point = expected.points.find(item => item.node_id === expected.primary_node_id);
      if (!point || point.point === null) throw new Error("The fixture must have a primary point.");
      await expect(frame.getByRole("table", { name: "Previsione e baseline allineata" })).toContainText(String(point.point));
    }
    if (kind === "report") await expect(frame.getByText(`Stato: ${expected.summary.status} · Orizzonte: ${expected.summary.selection.horizon}`)).toBeVisible();
    await frame.getByRole("button", { name: "Apri nel browser" }).click();
    await expect.poll(() => page.evaluate(() => window.__openedUrl)).toMatch(new RegExp(`/w/[0-9a-f]{32}/${kind}/${id}$`));
    if (kind === "run" || kind === "report") {
      await frame.getByText("Assunzioni e provenienza").click();
      await expect(frame.getByText(kind === "run" ? /Emissione:/ : /revisione/)).toBeVisible();
      await expect(frame.getByRole("table", { name: kind === "run" ? "Previsione e baseline allineata" : "Errori per origine" })).toBeVisible();
    }
    const blocked = await frame.locator("body").evaluate(async () => {
      try { await fetch("http://127.0.0.1:8000/health"); return false; } catch { return true; }
    });
    if (!blocked) throw new Error("The embedded view could make a direct network request.");
    console.log(`${kind}: exact record rendered, interactive controls verified, direct network blocked`);
    await page.close();
  }
  const page = await browser.newPage();
  await page.route("**/mcp", async route => {
    let request;
    try { request = route.request().postDataJSON(); } catch { /* not JSON */ }
    if (request?.method === "resources/read") return route.fulfill({ status: 200, contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify({ jsonrpc: "2.0", id: request.id, error: { code: -32602, message: "resource unavailable" } }) });
    return route.continue();
  });
  await page.goto(host);
  await page.waitForSelector('option[value="open_context_view"]', { state: "attached" });
  await page.waitForTimeout(300);
  await page.locator("textarea").fill(JSON.stringify({ kind: "run", resource_id: process.env.FA_RUN_ID, browser_url: browserOrigin }));
  await page.getByRole("button", { name: "Call Tool" }).click();
  await expect(page.getByText(/Primo punto previsto:.*count/)).toBeVisible({ timeout: 15000 });
  await page.getByText("Tool Result", { exact: false }).click();
  await expect(page.getByText(/Apri nel browser:/)).toBeVisible();
  console.log("UI resource failure: textual result and browser fallback remain available");
} finally { await browser.close(); }
