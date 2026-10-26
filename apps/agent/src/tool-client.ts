import { BridgeError, type DiscoveryRecord } from "./bridge.js";
import { createCoreClient, type CoreClientOptions } from "./client.js";
import { coreOperationFetch } from "./egress.js";
import { PostgresDiscoveryStore } from "./store.js";

type EveToolIdentity = { session: { id: string }; callId: string };
type ToolStore = { get(sessionId: string): Promise<DiscoveryRecord | undefined> };
type ToolOptions = {
  store?: ToolStore;
  coreUrl?: string;
  agentToken?: string;
  fetcher?: typeof fetch;
};

let store: PostgresDiscoveryStore | undefined;
function durableStore(): PostgresDiscoveryStore {
  store ??= new PostgresDiscoveryStore();
  return store;
}

export async function coreClientForTool(identity: EveToolIdentity, options: ToolOptions = {}) {
  if (!identity.session.id || !identity.callId) throw new BridgeError("invalid_tool_identity");
  const record = await (options.store ?? durableStore()).get(identity.session.id);
  if (!record || record.sessionId !== identity.session.id) throw new BridgeError("unknown_session");
  const coreUrl = options.coreUrl ?? process.env.FORECAST_AGENT_CORE_URL;
  const agentToken = options.agentToken ?? process.env.FORECAST_AGENT_CORE_TOKEN;
  if (!coreUrl || !agentToken) throw new BridgeError("missing_core_configuration");
  const clientOptions: CoreClientOptions = {
    coreUrl, agentToken, jobId: record.idempotencyKey, epochId: record.epochId,
    sessionId: record.sessionId, callKey: identity.callId,
    fetcher: coreOperationFetch(coreUrl, options.fetcher ?? globalThis.fetch),
  };
  return { client: createCoreClient(clientOptions), sourceIds: record.sourceIds, epochId: record.epochId };
}
