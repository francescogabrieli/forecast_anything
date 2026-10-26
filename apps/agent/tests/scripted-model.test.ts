import { generateText, stepCountIs, tool } from "ai";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { createCoreClient } from "../src/client.js";
import { createScriptedDiscoveryModel } from "../src/scripted-discovery-model.js";

describe("scripted Eve discovery model", () => {
  it("calls the registered discovery tools before returning its final response", async () => {
    const inspectSource = vi.fn(async ({ source_id }: { source_id: string }) => ({ source_id }));
    const coreFetch = vi.fn(async () => Response.json({
      operation_id: "operation-scripted-1",
      result: { candidateIds: [], candidates: [] },
    }));
    const client = createCoreClient({
      coreUrl: "http://127.0.0.1:8000",
      agentToken: "test-agent-token",
      jobId: "job-scripted-1",
      epochId: "epoch-scripted-1",
      sessionId: "session-scripted-1",
      callKey: "call-scripted-1",
      fetcher: coreFetch,
    });
    const proposeCandidates = vi.fn(async (proposal: {
      template_id: string;
      source_ids: string[];
      reason: string;
    }) => client.proposeCandidates(["source-synthetic-1"], "epoch-scripted-1", proposal));

    const result = await generateText({
      model: createScriptedDiscoveryModel(),
      prompt: "Discover a candidate from source-1.",
      stopWhen: stepCountIs(3),
      tools: {
        inspect_source: tool({
          description: "Read a source profile.",
          inputSchema: z.object({ source_id: z.string() }),
          execute: inspectSource,
        }),
        propose_candidates: tool({
          description: "Submit a structured question.",
          inputSchema: z.object({
            template_id: z.string(),
            source_ids: z.array(z.string()),
            reason: z.string(),
          }),
          execute: proposeCandidates,
        }),
      },
    });

    expect(inspectSource).toHaveBeenCalledWith({ source_id: "source-synthetic-1" }, expect.anything());
    expect(proposeCandidates).toHaveBeenCalledWith({
      template_id: "forecast_change",
      source_ids: ["source-synthetic-1"],
      reason: "A synthetic question for the restart recovery check.",
    }, expect.anything());
    expect(coreFetch).toHaveBeenCalledTimes(1);
    expect(result.text).toBe("The synthetic candidate was submitted to the trusted core.");
  });
});
