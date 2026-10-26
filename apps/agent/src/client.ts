import Ajv2020Module from "ajv/dist/2020.js";
import addFormatsModule from "ajv-formats";
import { coreOperationFetch, isSafeHttpOrigin } from "./egress.js";

import {
  candidateRequestSchema,
  candidateSchema,
  sourceProfileSchema,
  agentOperationRequestSchema,
  agentOperationResponseSchema,
  type Candidate,
  type SourceProfile,
} from "./schema.generated.js";

const Ajv2020 = Ajv2020Module as unknown as typeof import("ajv/dist/2020.js").default;
const addFormats = addFormatsModule as unknown as typeof import("ajv-formats").default;
const ajv = new Ajv2020({ strict: false, allErrors: false });
addFormats(ajv);
const validProposal = ajv.compile(candidateRequestSchema);
const validCandidate = ajv.compile(candidateSchema);
const validProfile = ajv.compile(sourceProfileSchema);
const validOperationRequest = ajv.compile(agentOperationRequestSchema);
const validOperationResponse = ajv.compile(agentOperationResponseSchema);

export interface CoreClientOptions {
  coreUrl: string;
  agentToken: string;
  jobId: string;
  epochId: string;
  sessionId: string;
  callKey: string;
  fetcher?: typeof fetch;
}

export class AgentClientError extends Error {
  constructor(readonly code: string) {
    super(code);
  }
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

export function createCoreClient(options: CoreClientOptions) {
  let base: URL;
  try { base = new URL(options.coreUrl); }
  catch { throw new AgentClientError("invalid_core_url"); }
  if (!isSafeHttpOrigin(base) || base.username || base.password || base.search || base.hash || base.pathname !== "/") {
    throw new AgentClientError("invalid_core_url");
  }
  const endpoint = new URL("/v1/agent/operations", base);
  const fetcher = coreOperationFetch(base.origin, options.fetcher ?? globalThis.fetch);
  if (!options.agentToken.trim()) throw new AgentClientError("missing_agent_token");

  async function operation(tool: "inspectSource" | "proposeCandidates" | "explainRun", input: object): Promise<unknown> {
    const request = {
      job_id: options.jobId, epoch_id: options.epochId, session_id: options.sessionId,
      call_key: options.callKey, tool, input,
    };
    if (!validOperationRequest(request)) throw new AgentClientError("invalid_core_operation");
    const response = await fetcher(endpoint.href, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${options.agentToken}` },
      redirect: "error",
      body: JSON.stringify(request),
    });
    let body: unknown;
    try { body = await response.json(); } catch { throw new AgentClientError("invalid_core_response"); }
    if (!response.ok) {
      const code = record(body)?.code;
      throw new AgentClientError(typeof code === "string" && /^[a-z_]+$/.test(code) ? code : "core_operation_failed");
    }
    const payload = record(body);
    if (!payload || !validOperationResponse(payload)) {
      throw new AgentClientError("invalid_core_response");
    }
    return payload.result;
  }

  return {
    async submitProposal(value: unknown): Promise<{ candidateIds: string[] }> {
      const proposals = Array.isArray(value) ? value : [value];
      if (proposals.length === 0 || !proposals.every((item) => validProposal(item))) {
        throw new AgentClientError("invalid_proposal");
      }
      const result = record(await operation("proposeCandidates", { proposals }));
      if (!result || !Array.isArray(result.candidateIds) || !result.candidateIds.every((id) => typeof id === "string") ||
          !Array.isArray(result.candidates) || !result.candidates.every((candidate) => validCandidate(candidate)) ||
          result.candidates.length !== result.candidateIds.length ||
          result.candidates.some((candidate: Candidate, index: number) => candidate.candidate_id !== (result.candidateIds as string[])[index])) {
        throw new AgentClientError("invalid_core_response");
      }
      return { candidateIds: result.candidateIds };
    },
    async proposeCandidates(sourceIds: string[], epochId: string, proposals: unknown): Promise<Candidate[]> {
      const values = Array.isArray(proposals) ? proposals : [proposals];
      if (epochId !== options.epochId || !Array.isArray(sourceIds) || !sourceIds.length ||
          values.length === 0 || !values.every((item) => validProposal(item)) ||
          values.some((item: { source_ids: string[] }) => item.source_ids.some((id) => !sourceIds.includes(id)))) {
        throw new AgentClientError("invalid_proposal");
      }
      const result = record(await operation("proposeCandidates", { proposals: values }));
      if (!result || !Array.isArray(result.candidateIds) || !Array.isArray(result.candidates) ||
          result.candidateIds.length !== result.candidates.length ||
          !result.candidates.every((candidate) => validCandidate(candidate)) ||
          result.candidates.some((candidate: Candidate, index: number) => candidate.candidate_id !== (result.candidateIds as string[])[index])) {
        throw new AgentClientError("invalid_core_response");
      }
      return result.candidates as Candidate[];
    },
    async explainRun(runId: string): Promise<{ text: string; evidenceIds: string[] }> {
      const result = record(await operation("explainRun", { run_id: runId }));
      if (!result || typeof result.text !== "string" || !Array.isArray(result.evidenceIds) ||
          !result.evidenceIds.every((id) => typeof id === "string" && id.length > 0)) {
        throw new AgentClientError("invalid_core_response");
      }
      if (/\b\d+(?:[.,]\d+)?\s*%/.test(result.text) && result.evidenceIds.length === 0) {
        throw new AgentClientError("missing_evidence");
      }
      return { text: result.text, evidenceIds: result.evidenceIds };
    },
    async inspectSource(sourceId: string): Promise<SourceProfile> {
      const result = await operation("inspectSource", { source_id: sourceId });
      if (!validProfile(result)) throw new AgentClientError("invalid_core_response");
      return result as SourceProfile;
    },
  };
}
