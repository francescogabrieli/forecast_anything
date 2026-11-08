import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import { resolve } from "node:path";
export default defineConfig({ publicDir: false, plugins: [viteSingleFile()], build: { outDir: resolve(import.meta.dirname, "../../src/forecast_anything/mcp_adapter/ui_dist"), emptyOutDir: true, rollupOptions: { input: resolve(import.meta.dirname, "context.html") } } });
