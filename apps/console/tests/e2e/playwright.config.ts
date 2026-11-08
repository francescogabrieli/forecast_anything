import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const configDirectory = new URL(".", import.meta.url);
const testDirectory = resolve(fileURLToPath(configDirectory), "../../../../tests/e2e");

export default defineConfig({
  testDir: testDirectory,
  testMatch: ["observatory.spec.ts", "timestral.spec.ts"],
  timeout: 45_000,
  fullyParallel: false,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:4173", trace: "retain-on-failure", ...devices["Desktop Chrome"] },
  webServer: [
    { command: "cd ../../../.. && uv run --locked --extra dev --extra mcp python tests/e2e/serve_observatory.py", url: "http://127.0.0.1:8000/health", reuseExistingServer: !process.env.CI, timeout: 120_000 },
    { command: "cd ../../../.. && FA_USABILITY_PORT=8001 uv run --locked --extra dev --extra mcp python tests/e2e/serve_observatory.py", url: "http://127.0.0.1:8001/health", reuseExistingServer: !process.env.CI, timeout: 120_000 },
    { command: "npm run build && npm run preview -- --host 127.0.0.1 --port 4173", url: "http://127.0.0.1:4173", reuseExistingServer: !process.env.CI, timeout: 120_000 },
  ],
});
