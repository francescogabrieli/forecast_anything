import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "./client";

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("ApiClient", () => {
  it("sends the workspace token in the authorization header, not the URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ source_id: "sales" }),
    });
    globalThis.fetch = fetchMock;
    const client = new ApiClient("https://forecast.local/", "workspace-secret");

    await client.inspectSource("sales data");

    expect(fetchMock).toHaveBeenCalledWith(
      "https://forecast.local/v1/sources/sales%20data/profile",
      expect.objectContaining({
        method: "GET",
        headers: { Authorization: "Bearer workspace-secret" },
      }),
    );
  });

  it("rejects API addresses that contain query or credential values", () => {
    expect(() => new ApiClient("https://forecast.local/?token=leaked", "secret")).toThrow(/must not contain credentials/);
  });

  it("preserves authentication error codes for the UI", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ code: "unauthorized", details: {} }),
    });
    const client = new ApiClient("http://localhost:8000", "wrong-token");

    await expect(client.inspectSource("sales")).rejects.toMatchObject({
      status: 401,
      code: "unauthorized",
    });
  });
});

describe("ApiClient observatory methods", () => {
  it("keeps event cursors in the API query and auth in the header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    globalThis.fetch = fetchMock;
    const client = new ApiClient("https://forecast.local", "workspace-secret");

    await client.getEvents(12, 40);

    expect(fetchMock).toHaveBeenCalledWith(
      "https://forecast.local/v1/events?after=12&limit=40",
      expect.objectContaining({ headers: { Authorization: "Bearer workspace-secret" } }),
    );
  });

  it("replays from the last cursor after an event stream disconnect", async () => {
    const encoder = new TextEncoder();
    const event = (cursor: number) => JSON.stringify({ cursor, event_id: `event-${cursor}`, kind: "run_completed", run_id: `run-${cursor}`, payload: {} });
    const streamResponse = (frames: string[]) => new Response(new ReadableStream({
      start(controller) {
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        controller.close();
      },
    }), { status: 200, headers: { "Content-Type": "text/event-stream" } });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(streamResponse([`id: 2\ndata: ${event(2)}\n\n`]))
      .mockResolvedValueOnce({ ok: true, json: async () => [{ cursor: 3, event_id: "event-3", kind: "run_completed", run_id: "run-3", payload: {} }] })
      .mockImplementationOnce(async (_url, init) => {
        const response = streamResponse([`id: 4\ndata: ${event(4)}\n\n`]);
        const signal = (init as RequestInit).signal;
        signal?.addEventListener("abort", () => {}, { once: true });
        return response;
      });
    globalThis.fetch = fetchMock;
    const client = new ApiClient("http://localhost:8000", "workspace-secret");
    const controller = new AbortController();
    const cursors: number[] = [];

    await client.streamEvents(0, (received) => {
      cursors.push(received.cursor);
      if (received.cursor === 4) controller.abort();
    }, controller.signal);

    expect(cursors).toEqual([2, 3, 4]);
    expect(fetchMock.mock.calls[2]?.[0]).toBe("http://localhost:8000/v1/events/stream?after=3&follow=true");
  });
});


it("loads persisted evaluations for an encoded run with workspace authentication", async () => {
  const evaluation = { evaluation_id: "evaluation-1", run_id: "run one", actuals_snapshot_id: "actuals", status: "evaluated", metrics: {}, origin_count: 1, assumptions: [], discovery: null };
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([evaluation]), { status: 200 }));
  globalThis.fetch = fetchMock;
  const client = new ApiClient("https://forecast.local", "workspace-secret");

  expect(await client.getRunEvaluations("run one")).toEqual([evaluation]);
  expect(fetchMock).toHaveBeenCalledWith("https://forecast.local/v1/runs/run%20one/evaluations", {
    method: "GET", headers: { Authorization: "Bearer workspace-secret" },
  });
});
