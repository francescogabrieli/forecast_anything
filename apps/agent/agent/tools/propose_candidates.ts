import { defineTool } from "eve/tools";

import { candidateRequestSchema } from "../../src/schema.generated.js";
import { coreClientForTool } from "../../src/tool-client.js";

export default defineTool({
  description: "Submit one structured candidate proposal to the core for budgeted validation and registration.",
  availableInSubagents: false,
  inputSchema: candidateRequestSchema,
  async execute(input, ctx) {
    const { client, sourceIds, epochId } = await coreClientForTool(ctx);
    const candidates = await client.proposeCandidates(sourceIds, epochId, input);
    return { candidateIds: candidates.map((candidate) => candidate.candidate_id), candidates };
  },
});
