import { describe, expect, it, vi } from "vitest";

import { coreOperationFetch, openAIProviderFetch } from "../src/egress.js";

describe("service HTTP egress allowlist", () => {
  it("permits the configured core and OpenAI origins", async () => {
    const transport = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => Response.json({ ok: true }));
    const coreFetch = coreOperationFetch("http://127.0.0.1:8000", transport);
    const openAIFetch = openAIProviderFetch(transport);

    await coreFetch("http://127.0.0.1:8000/v1/agent/operations");
    await openAIFetch("https://api.openai.com/v1/responses");
    expect(transport).toHaveBeenCalledTimes(2);
    expect(transport.mock.calls[0]![1]).toMatchObject({ redirect: "error" });
    expect(transport.mock.calls[1]![1]).toMatchObject({ redirect: "error" });
  });

  it("permits only the exact Docker core service origin over HTTP", async () => {
    const transport = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => Response.json({ ok: true }));
    const coreFetch = coreOperationFetch("http://core:8000", transport);
    await coreFetch("http://core:8000/v1/agent/operations");
    await expect(coreFetch("http://core:8001/v1/agent/operations")).rejects.toMatchObject({ code: "egress_denied" });
    expect(transport).toHaveBeenCalledTimes(1);
  });

  it.each(["https://arbitrary.example/v1", "http://arbitrary.example/v1", "http://127.0.0.1:9000/other", "https://api.mistral.ai/v1/chat/completions"])(
    "blocks a request to %s before transport", async (url) => {
      const transport = vi.fn();
      const fetcher = coreOperationFetch("http://127.0.0.1:8000", transport);
      await expect(fetcher(url)).rejects.toMatchObject({ code: "egress_denied" });
      expect(transport).not.toHaveBeenCalled();
    },
  );

  it("does not permit the OpenAI provider to call the core, Mistral, or another site", async () => {
    const transport = vi.fn();
    const fetcher = openAIProviderFetch(transport);
    await expect(fetcher("http://127.0.0.1:8000/v1/agent/operations")).rejects.toMatchObject({ code: "egress_denied" });
    await expect(fetcher("https://arbitrary.example/v1")).rejects.toMatchObject({ code: "egress_denied" });
    await expect(fetcher("https://api.mistral.ai/v1/chat/completions")).rejects.toMatchObject({ code: "egress_denied" });
    expect(transport).not.toHaveBeenCalled();
  });
});
