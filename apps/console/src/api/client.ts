import type {
  EventRecord,
  Candidate,
  EvaluationRecord,
  GraphSpec,
  JobView,
  RunRecord,
  ScenarioRequest,
  ScenarioView,
  Snapshot,
  SourceProfile,
  SourceRegistration,
  SourceSpec,
  WatchView,
} from "./schema.generated";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly details: unknown,
  ) {
    super(code);
    this.name = "ApiError";
  }
}

export class ApiClient {
  private readonly origin: string;

  constructor(baseUrl: string, private readonly token: string) {
    const url = new URL(baseUrl);
    if (url.search || url.hash || url.username || url.password) {
      throw new Error("The API address must not contain credentials, a query, or a fragment.");
    }
    this.origin = url.toString().replace(/\/+$/, "");
  }

  inspectSource(sourceId: string): Promise<SourceProfile> {
    return this.request("GET", `/v1/sources/${encodeURIComponent(sourceId)}/profile`);
  }

  previewSource(spec: SourceSpec): Promise<SourceProfile> {
    return this.request("POST", "/v1/sources/preview", spec);
  }

  saveSource(spec: SourceSpec): Promise<SourceRegistration> {
    return this.request("POST", "/v1/sources", spec);
  }

  refreshSource(sourceId: string, key: string): Promise<SourceRegistration> {
    return this.request("POST", `/v1/sources/${encodeURIComponent(sourceId)}/refresh`, { key });
  }

  getWatches(): Promise<WatchView[]> {
    return this.request("GET", "/v1/watches");
  }

  getEvents(after = 0, limit = 100): Promise<EventRecord[]> {
    return this.request("GET", `/v1/events?after=${Math.max(0, after)}&limit=${Math.max(1, Math.min(1000, limit))}`);
  }

  getRun(runId: string): Promise<RunRecord> {
    return this.request("GET", `/v1/runs/${encodeURIComponent(runId)}`);
  }

  getRunEvaluations(runId: string): Promise<EvaluationRecord[]> {
    return this.request("GET", `/v1/runs/${encodeURIComponent(runId)}/evaluations`);
  }

  getJob(jobId: string): Promise<JobView> {
    return this.request("GET", `/v1/jobs/${encodeURIComponent(jobId)}`);
  }

  getCandidate(candidateId: string): Promise<Candidate> {
    return this.request("GET", `/v1/candidates/${encodeURIComponent(candidateId)}`);
  }

  submitRun(request: { kind: "run"; key: string; graph: GraphSpec; snapshot_ids: Record<string, string>; as_of: string }): Promise<JobView> {
    return this.request("POST", "/v1/jobs", request);
  }

  getGraph(graphId: string, version = 1): Promise<GraphSpec> {
    return this.request("GET", `/v1/graphs/${encodeURIComponent(graphId)}?version=${version}`);
  }

  getEvaluation(evaluationId: string): Promise<EvaluationRecord> {
    return this.request("GET", `/v1/evaluations/${encodeURIComponent(evaluationId)}`);
  }

  getSnapshot(snapshotId: string): Promise<Snapshot> {
    return this.request("GET", `/v1/snapshots/${encodeURIComponent(snapshotId)}`);
  }

  updateWatch(watchId: string, patch: { muted?: boolean; priority?: number }): Promise<WatchView> {
    return this.request("PATCH", `/v1/watches/${encodeURIComponent(watchId)}`, patch);
  }

  createScenario(request: ScenarioRequest): Promise<ScenarioView> {
    return this.request("POST", "/v1/scenarios", request);
  }

  async streamEvents(after: number, onEvent: (event: EventRecord) => void, signal: AbortSignal): Promise<void> {
    let cursor = Math.max(0, after);
    while (!signal.aborted) {
      try {
        cursor = await this.readEventStream(cursor, onEvent, signal);
        if (signal.aborted) return;
        cursor = await this.replayEvents(cursor, onEvent);
      } catch (error) {
        if (signal.aborted) return;
        if (error instanceof ApiError) throw error;
        await waitBeforeReconnect(signal, 250);
        cursor = await this.replayEvents(cursor, onEvent);
      }
    }
  }

  private async readEventStream(cursor: number, onEvent: (event: EventRecord) => void, signal: AbortSignal): Promise<number> {
    const response = await fetch(`${this.origin}/v1/events/stream?after=${cursor}&follow=true`, {
      headers: { Authorization: `Bearer ${this.token}`, Accept: "text/event-stream" },
      signal,
    });
    if (!response.ok) throw await toApiError(response);
    if (!response.body) throw new Error("Event stream is unavailable.");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let latest = cursor;
    while (!signal.aborted) {
      const chunk = await reader.read();
      if (chunk.done) return latest;
      buffer += decoder.decode(chunk.value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const data = frame.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
        if (!data) continue;
        const event = JSON.parse(data) as EventRecord;
        if (event.cursor <= latest) continue;
        latest = event.cursor;
        onEvent(event);
      }
    }
    return latest;
  }

  private async replayEvents(cursor: number, onEvent: (event: EventRecord) => void): Promise<number> {
    let latest = cursor;
    for (const event of await this.getEvents(cursor)) {
      if (event.cursor <= latest) continue;
      latest = event.cursor;
      onEvent(event);
    }
    return latest;
  }

  private async request<T>(method: "GET" | "POST" | "PATCH", path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${this.origin}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${this.token}`,
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) throw await toApiError(response);
    return await response.json() as T;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => null);
  return new ApiError(
    response.status,
    typeof payload?.code === "string" ? payload.code : "request_failed",
    payload?.details,
  );
}

function waitBeforeReconnect(signal: AbortSignal, ms: number): Promise<void> {
  return new Promise((resolve) => {
    const finish = () => { clearTimeout(timer); signal.removeEventListener("abort", finish); resolve(); };
    const timer = setTimeout(finish, ms);
    signal.addEventListener("abort", finish, { once: true });
  });
}
