export class EgressDeniedError extends Error {
  readonly code = "egress_denied";
  constructor() { super("egress_denied"); }
}

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

export function isSafeHttpOrigin(url: URL): boolean {
  return url.protocol === "https:" ||
    (url.protocol === "http:" && (LOOPBACK_HOSTS.has(url.hostname) ||
      (url.hostname === "core" && url.port === "8000")));
}

function requestUrl(input: RequestInfo | URL): URL {
  try {
    return new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
  } catch { throw new EgressDeniedError(); }
}

/** Restricts an authored HTTP call to exact origins and prevents redirect escape. */
export function allowlistedFetch(origins: readonly string[], transport: typeof fetch = globalThis.fetch): typeof fetch {
  const allowed = new Set(origins.map((origin) => {
    let parsed: URL;
    try { parsed = new URL(origin); } catch { throw new EgressDeniedError(); }
    if (!isSafeHttpOrigin(parsed) || parsed.origin !== origin || parsed.username || parsed.password ||
        parsed.pathname !== "/" || parsed.search || parsed.hash) throw new EgressDeniedError();
    return parsed.origin;
  }));
  return async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    if (!isSafeHttpOrigin(url) || url.username || url.password || !allowed.has(url.origin)) {
      throw new EgressDeniedError();
    }
    return transport(input, { ...init, redirect: "error" });
  };
}

export function coreOperationFetch(coreUrl: string, transport: typeof fetch = globalThis.fetch): typeof fetch {
  return allowlistedFetch([new URL(coreUrl).origin], transport);
}

export function openAIProviderFetch(transport: typeof fetch = globalThis.fetch): typeof fetch {
  return allowlistedFetch(["https://api.openai.com"], transport);
}
