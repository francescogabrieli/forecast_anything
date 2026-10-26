import { expect, test } from "@playwright/test";

test("reviews a deterministic run and compares an assumed scenario", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let interruptedStream = false;
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
  await expect(page.getByText("6 eventi unici")).toBeVisible();
  expect(interruptedStream).toBe(true);
  await page.getByRole("button", { name: "Silenzia segnalazioni" }).click();
  await expect(page.getByRole("button", { name: "Riattiva segnalazioni" })).toBeVisible();

  await page.getByLabel("ID della fonte").fill("activity");
  await page.getByLabel("Percorso o URL").fill("/private/tmp/forecast-anything-console-e2e.csv");
  await page.getByLabel("Mappatura JSON").fill(JSON.stringify({
    event_time: "time",
    value: "value",
    available_at: { constant: "2026-10-23" },
    revision: { constant: "1" },
    series_id: { constant: "activity" },
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

  const runButton = page.getByRole("button", { name: /Apri run/ }).first();
  await expect(runButton).toBeVisible();
  await runButton.click();
  await expect(page.getByRole("heading", { name: "Come si compone il futuro" })).toBeVisible();
  await expect(page.locator(".run-card")).toBeVisible();

  const forecastNode = page.getByRole("button", { name: /forecast, previsione/ });
  await forecastNode.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "Selezionato:" })).toBeVisible();

  const scenarioInput = page.getByLabel("Snapshot ipotetici per fonte");
  const current = JSON.parse(await scenarioInput.inputValue()) as Record<string, { observations: Array<{ value: number | null }> }>;
  const source = Object.keys(current)[0];
  current[source].observations = current[source].observations.map((item) => ({ ...item, value: 8 }));
  await scenarioInput.fill(JSON.stringify(current, null, 2));
  await page.getByRole("button", { name: "Crea scenario" }).click();
  await expect(page.getByText("Scenario pronto. Il confronto usa soltanto timestamp e unità comuni.")).toBeVisible({ timeout: 25_000 });
  await expect(page.getByRole("heading", { name: "Confronto sulle date comuni" })).toBeVisible();
  await expect(page.getByText(/ipotesi|assunzion/i).last()).toBeVisible();
});
