import { describe, expect, it, vi } from "vitest";

import { DiscoveryBridge } from "../src/bridge.js";

describe("durable discovery bridge", () => {
  it("reuses one parked session for repeated and concurrent starts", async () => {
    const records = new Map<string, unknown>();
    const driver = {
      create: vi.fn(async (_address: string) => ({ id: "session-1" })),
      send: vi.fn(async (_sessionId: string, _message: string, _key: string) => {}),
      events: vi.fn(async () => []),
    };
    const store = {
      put: vi.fn(async (record: { sessionId: string }) => { records.set(record.sessionId, record); }),
      get: vi.fn(async (sessionId: string) => records.get(sessionId)),
    };
    const bridge = new DiscoveryBridge(driver, store);
    const request = { epochId: "epoch-1", sourceIds: ["source-1"], idempotencyKey: "job-1" };

    const [a, b] = await Promise.all([bridge.start(request), bridge.start(request)]);
    expect(a).toEqual({ sessionId: "session-1" });
    expect(b).toEqual(a);
    expect(driver.create).toHaveBeenCalledWith("discovery/job-1");
    expect(driver.send).not.toHaveBeenCalled();
    const afterRestart = new DiscoveryBridge(driver, store);
    await expect(afterRestart.start(request)).resolves.toEqual(a);
  });
  it("starts the turn only during polling and reads validated tool results, never model prose", async () => {
    const records = new Map<string, unknown>();
    const driver = {
      create: vi.fn(async () => ({ id: "session-2" })),
      send: vi.fn(async (_sessionId: string, _message: string, _key: string) => {}),
      events: vi.fn()
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([
          { type: "message.completed", data: { message: "The probability is 99%." } },
          { type: "action.result", data: { status: "completed", result: {
            kind: "tool-result", toolName: "propose_candidates",
            output: { candidateIds: [], candidates: [] },
          } } },
          { type: "turn.completed", data: {} },
        ]),
    };
    const store = {
      put: vi.fn(async (record: { sessionId: string }) => { records.set(record.sessionId, record); }),
      get: vi.fn(async (sessionId: string) => records.get(sessionId)),
    };
    const bridge = new DiscoveryBridge(driver, store);
    await bridge.start({ epochId: "epoch-2", sourceIds: ["source-2"], idempotencyKey: "job-2" });
    expect(driver.send).not.toHaveBeenCalled();

    await expect(bridge.poll("session-2")).resolves.toEqual({ state: "pending", candidates: [] });
    const resumed = new DiscoveryBridge(driver, store);
    await expect(resumed.poll("session-2")).resolves.toEqual({ state: "completed", candidates: [] });
    expect(driver.send).toHaveBeenCalledTimes(2);
    expect(driver.send.mock.calls[0]![2]).toBe(driver.send.mock.calls[1]![2]);
  });

});
