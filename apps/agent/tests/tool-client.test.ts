import { describe, expect, it, vi } from "vitest";

import { coreClientForTool } from "../src/tool-client.js";

describe("Eve tool boundary", () => {
  it("binds every tool call to persisted job, epoch and Eve call ID", async () => {
    const get = vi.fn(async (_sessionId: string) => ({
      sessionId: "session-1", idempotencyKey: "job-1", epochId: "epoch-1", sourceIds: ["source-1"],
    }));
    const fetcher = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => Response.json({
      operation_id: "core-operation-1", result: { candidateIds: [], candidates: [] },
    }));
    const bound = await coreClientForTool({ session: { id: "session-1" }, callId: "eve-call-1" }, {
      store: { get }, coreUrl: "http://127.0.0.1:8000", agentToken: "agent-token", fetcher,
    });
    await bound.client.submitProposal({ template_id: "expected_deviation", source_ids: ["source-1"], reason: "Compare observed deviation" });
    expect(JSON.parse(String(fetcher.mock.calls[0]![1]!.body))).toMatchObject({
      job_id: "job-1", epoch_id: "epoch-1", session_id: "session-1", call_key: "eve-call-1",
    });
    expect(bound.sourceIds).toEqual(["source-1"]);
  });

  it("fails closed when no checkpointed session exists", async () => {
    await expect(coreClientForTool({ session: { id: "missing" }, callId: "call-1" }, {
      store: { get: async () => undefined }, coreUrl: "http://127.0.0.1:8000", agentToken: "agent-token",
    })).rejects.toMatchObject({ code: "unknown_session" });
  });
});
