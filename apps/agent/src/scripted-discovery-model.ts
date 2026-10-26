import { existsSync, writeFileSync } from "node:fs";

import { mockModel } from "eve/evals";

export interface ScriptedDiscoveryModelOptions {
  resumeMarkerPath?: string;
}

/** Deterministic model used only by the isolated Eve/Postgres recovery check. */
export function createScriptedDiscoveryModel(options: ScriptedDiscoveryModelOptions = {}) {
  return mockModel(async ({ toolResults }) => {
    const inspected = toolResults.some((result) => result.name === "inspect_source");
    if (!inspected) {
      return {
        toolCalls: [{
          name: "inspect_source",
          input: { source_id: "source-synthetic-1" },
        }],
      };
    }

    if (options.resumeMarkerPath && !existsSync(options.resumeMarkerPath)) {
      writeFileSync(options.resumeMarkerPath, "inspect_source completed; awaiting Eve restart\n");
      await new Promise<never>(() => {});
    }

    const proposed = toolResults.some((result) => result.name === "propose_candidates");
    if (!proposed) {
      return {
        toolCalls: [{
          name: "propose_candidates",
          input: {
            template_id: "forecast_change",
            source_ids: ["source-synthetic-1"],
            reason: "A synthetic question for the restart recovery check.",
          },
        }],
      };
    }

    return { text: "The synthetic candidate was submitted to the trusted core." };
  });
}
