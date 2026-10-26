import { defineTool } from "eve/tools";
import { z } from "zod";

import { coreClientForTool } from "../../src/tool-client.js";

export default defineTool({
  description: "Inspect the core's bounded profile of one source in the frozen discovery epoch.",
  availableInSubagents: false,
  inputSchema: z.object({ source_id: z.string().min(1) }),
  async execute({ source_id }, ctx) {
    const { client, sourceIds } = await coreClientForTool(ctx);
    if (!sourceIds.includes(source_id)) throw new Error("source_not_in_epoch");
    return client.inspectSource(source_id);
  },
});
