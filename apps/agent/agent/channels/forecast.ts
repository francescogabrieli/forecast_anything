import { defineChannel, GET, POST, type RouteHandlerArgs } from "eve/channels";

import { DiscoveryBridge, type SessionDriver } from "../../src/bridge.js";
import { createBridgeHttp } from "../../src/bridge-http.js";
import { PostgresDiscoveryStore } from "../../src/store.js";

let store: PostgresDiscoveryStore | undefined;
function durableStore(): PostgresDiscoveryStore {
  store ??= new PostgresDiscoveryStore();
  return store;
}

function driver(args: RouteHandlerArgs): SessionDriver {
  return {
    async create(address) {
      const { session } = await args.from(address).create({ auth: null });
      return { id: session.id };
    },
    async send(sessionId, message, key) {
      await args.attachSession(sessionId).send(message, { auth: null, idempotencyKey: key });
    },
    async events(sessionId) {
      const stream = await args.attachSession(sessionId).getEventStream({ follow: false });
      const reader = stream.getReader();
      const events: unknown[] = [];
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          events.push(value);
        }
      } finally { reader.releaseLock(); }
      return events;
    },
  };
}

function http(args: RouteHandlerArgs) {
  return createBridgeHttp(
    () => new DiscoveryBridge(driver(args), durableStore()),
    () => process.env.FORECAST_AGENT_BRIDGE_TOKEN,
  );
}

export default defineChannel({
  routes: [
    POST("/forecast/discover", (request, args) => http(args).start(request)),
    GET("/forecast/discover/:sessionId", (request, args) =>
      http(args).poll(request, args.params.sessionId)),
  ],
});
