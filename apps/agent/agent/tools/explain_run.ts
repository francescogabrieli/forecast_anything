import { defineTool } from "eve/tools";
import { z } from "zod";

import { coreClientForTool } from "../../src/tool-client.js";

export default defineTool({
  description: "Read an evidence-bound explanation from the core for an existing run.",
  availableInSubagents: false,
  inputSchema: z.object({ run_id: z.string().min(1) }),
  async execute({ run_id }, ctx) {
    const { client } = await coreClientForTool(ctx);
    return client.explainRun(run_id);
  },
});
