import { expect, test } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

test("issues a real required Timestral forecast from the console", async ({ page, request }, testInfo) => {
  test.skip(process.env.FORECAST_ANYTHING_TIMESTRAL_WEIGHTS_APPROVED !== "1", "Real licensed local model acceptance is explicit; ordinary fixtures do not establish it.");
  test.setTimeout(60_000);
  const root = await mkdtemp(resolve(tmpdir(), "forecast-real-console-"));
  const source = resolve(root, "synthetic.csv");
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  const rows = Array.from({ length: 60 }, (_, i) => {
    const day = new Date(today.getTime() - (59 - i) * 86_400_000).toISOString().slice(0, 10);
    return `${day},${i % 2 ? 3 : 1},${day}`;
  });
  await writeFile(source, `time,value,published\n${rows.join("\n")}\n`);
  const server = createServer();
  const port = await new Promise<number>((done, reject) => {
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") { reject(new Error("No test port")); return; }
      server.close(() => done(address.port));
    });
  });
  const api = `http://127.0.0.1:${port}`;
  const token = "synthetic-required-model-test-token";
  const headers = { Authorization: `Bearer ${token}` };
  const runtime = spawn(resolve(process.cwd(), "../../.venv/bin/forecast-anything"), ["up", "--db", resolve(root, "state.db"), "--port", String(port)], {
    env: { ...process.env, FORECAST_ANYTHING_WORKSPACE_TOKEN: token, FORECAST_ANYTHING_CONSOLE_ORIGINS: "http://127.0.0.1:4173", OMP_NUM_THREADS: "1", MKL_NUM_THREADS: "1", HF_HUB_OFFLINE: "1" },
    stdio: "ignore",
  });
  try {
    await expect.poll(async () => {
      try { return (await request.get(`${api}/health`)).status(); } catch { return 0; }
    }, { timeout: 15_000 }).toBe(200);
    await page.goto("/#workspace");
    await page.getByLabel("Indirizzo API").fill(api);
    await page.getByLabel("Token workspace").fill(token);
    await page.getByRole("button", { name: /Apri il workspace/ }).click();
    await page.getByLabel("ID della fonte").fill("timestral-browser");
    await page.getByLabel("Percorso o URL").fill(source);
    await page.getByLabel("Data osservazione — campo", { exact: true }).fill("time");
    await page.getByLabel("Valore — campo", { exact: true }).fill("value");
    await page.getByRole("combobox", { name: /^Disponibile dal — origine/ }).selectOption("column");
    await page.getByLabel("Disponibile dal — campo", { exact: true }).fill("published");
    await page.getByLabel("Serie — campo", { exact: true }).fill("sales");
    await page.getByLabel("Unità — campo", { exact: true }).fill("count");
    await page.getByLabel("Revisione — campo", { exact: true }).fill("1");
    await page.getByLabel("Frequenza", { exact: true }).fill("1d");
    await page.getByLabel("Fuso orario", { exact: true }).fill("UTC");
    await page.getByRole("button", { name: "Analizza fonte" }).click();
    await page.getByRole("button", { name: "Attiva fonte" }).click();
    await expect(page.getByText("Modello: timestral", { exact: true })).toBeVisible();
    const submitted = page.waitForResponse(response => response.url() === `${api}/v1/jobs` && response.request().method() === "POST");
    await page.getByRole("button", { name: "Calcola la prima previsione" }).click();
    const accepted = await (await submitted).json();
    await expect.poll(async () => (await (await request.get(`${api}/v1/jobs/${accepted.job_id}`, { headers })).json()).state, { timeout: 30_000 }).toBe("completed");
    const job = await (await request.get(`${api}/v1/jobs/${accepted.job_id}`, { headers })).json();
    const run = await (await request.get(`${api}/v1/runs/${job.result.run_id}`, { headers })).json();
    expect(run.primary_node_id).toBe("question");
    expect(run.results.forecast.provider_id).toBe("timestral");
    expect(run.results.forecast.provider_revision).toContain("mistralai/Timestral-28M@49b26409ac87b5935539a5d8ffe7f397b720db47");
    expect(run.results.reference.provider_id).toBe("seasonal_naive");
    expect(Number.isFinite(run.results.forecast.point[0][0])).toBe(true);
    await expect(page.locator(".run-card").getByText(`ID run: ${run.run_id}`)).toBeVisible();
    await expect(page.locator(".forecast-summary")).toContainText("timestral");
    await page.screenshot({ path: testInfo.outputPath("timestral-console.png"), fullPage: true });
  } finally {
    if (runtime.exitCode === null) await new Promise<void>(done => {
      const timer = setTimeout(() => { runtime.kill("SIGKILL"); done(); }, 5_000);
      runtime.once("exit", () => { clearTimeout(timer); done(); });
      runtime.kill("SIGTERM");
    });
  }
});
