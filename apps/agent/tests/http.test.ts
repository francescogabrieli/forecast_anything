import { describe, expect, it, vi } from "vitest";

import { createBridgeHttp } from "../src/bridge-http.js";

describe("discovery bridge HTTP contract", () => {
  it("authenticates start and poll before entering the session driver", async () => {
    const bridge = {
      start: vi.fn(async () => ({ sessionId: "session-1" })),
      poll: vi.fn(async () => ({ state: "pending" as const, candidates: [] })),
    };
    const http = createBridgeHttp(() => bridge, () => "bridge-token");
    const body = JSON.stringify({ epochId: "epoch-1", sourceIds: ["source-1"], idempotencyKey: "job-1" });
    const request = (token?: string) => new Request("http://127.0.0.1/forecast/discover", {
      method: "POST", body, headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    expect((await http.start(request())).status).toBe(401);
    expect(bridge.start).not.toHaveBeenCalled();
    const started = await http.start(request("bridge-token"));
    expect(started.status).toBe(202);
    expect(await started.json()).toEqual({ sessionId: "session-1" });
    expect((await http.poll(new Request("http://127.0.0.1/forecast/discover/session-1"), "session-1")).status).toBe(401);
    const polled = await http.poll(new Request("http://127.0.0.1/forecast/discover/session-1", {
      headers: { Authorization: "Bearer bridge-token" },
    }), "session-1");
    expect(await polled.json()).toEqual({ state: "pending", candidates: [] });
  });
});
