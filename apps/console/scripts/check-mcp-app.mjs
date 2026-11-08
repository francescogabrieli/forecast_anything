import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
const directory = mkdtempSync(join(tmpdir(), "forecast-mcp-app-build-"));
try {
  execFileSync(process.execPath, [resolve("node_modules/vite/bin/vite.js"), "build", "--config", "vite.mcp.config.ts", "--outDir", directory], { stdio: "inherit" });
  const generated = readFileSync(join(directory, "context.html"));
  const committed = readFileSync(resolve("../../src/forecast_anything/mcp_adapter/ui_dist/context.html"));
  if (!generated.equals(committed)) throw new Error("MCP App bundle is stale; run npm run build:mcp-app.");
} finally { rmSync(directory, { recursive: true, force: true }); }
