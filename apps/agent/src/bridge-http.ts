import { bridgeAuthorized } from "./auth.js";
import { BridgeError, type DiscoveryBridge, type DiscoveryStart } from "./bridge.js";

type BridgeSurface = Pick<DiscoveryBridge, "start" | "poll">;

function failure(error: unknown): Response {
  const code = error instanceof BridgeError ? error.code : "bridge_unavailable";
  const status = code === "idempotency_conflict" ? 409 :
    code === "unknown_session" ? 404 :
    code.startsWith("invalid_") ? 422 : 503;
  return Response.json({ code }, { status });
}

export function createBridgeHttp(bridge: () => BridgeSurface, token: () => string | undefined) {
  return {
    async start(request: Request): Promise<Response> {
      if (!bridgeAuthorized(request, token())) return Response.json({ code: "unauthorized" }, { status: 401 });
      let input: unknown;
      try { input = await request.json(); } catch { return Response.json({ code: "invalid_discovery_start" }, { status: 422 }); }
      try {
        return Response.json(await bridge().start(input as DiscoveryStart), { status: 202 });
      } catch (error) { return failure(error); }
    },
    async poll(request: Request, sessionId: string): Promise<Response> {
      if (!bridgeAuthorized(request, token())) return Response.json({ code: "unauthorized" }, { status: 401 });
      try { return Response.json(await bridge().poll(sessionId)); }
      catch (error) { return failure(error); }
    },
  };
}
