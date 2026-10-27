import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Candidate, JobView, Snapshot, SourceRegistration } from "../../api/schema.generated";
import { makeProfile, makeRun } from "../../test/fixtures";
import { FirstForecast } from "./FirstForecast";

const registration: SourceRegistration = {
  source_id: "sales", kind: "csv", revision: "rev-1", refresh_seconds: 3600,
  profile: makeProfile(), epoch_id: "epoch-1", job_id: "discovery-1",
};
const snapshot: Snapshot = {
  snapshot_id: "snapshot-1", as_of: "2026-10-24T12:00:00Z", assumptions: [],
  observations: [{ series_id: "sales", event_time: "2026-10-24T00:00:00Z", available_at: "2026-10-24T00:00:00Z", revision: "1", value: 3, unit: "count" }],
};
const candidate: Candidate = {
  candidate_id: "candidate-1", epoch_id: "epoch-1", protocol_id: "protocol-1", template_id: "expected_deviation",
  source_ids: ["sales"], reason: "Candidate", executable: true,
  graph: { graph_id: "graph-1", version: 1, nodes: [
    { node_id: "source", kind: "source", inputs: [], config: { source_id: "sales", series_ids: ["sales"], frequency: "1d" } },
    { node_id: "forecast", kind: "forecast", inputs: ["source"], config: { history: "source", horizon: 1, frequency: "1d", provider: "seasonal_naive" } },
  ] },
};
const job = (job_id: string, state: string, result: Record<string, unknown> | null = null): JobView => ({ job_id, state, result, attempt: 1 });
function oneStepRun() {
  const run = makeRun({ as_of: snapshot.as_of });
  run.results.forecast = { ...run.results.forecast, point: [[3]], timestamps: ["2026-10-25T00:00:00Z"] };
  return run;
}
function client() {
  return {
    getJob: vi.fn(async (id: string) => id === "discovery-1"
      ? job(id, "completed", { candidate_ids: ["candidate-1"], source_snapshot_ids: ["snapshot-1"] })
      : job(id, "completed", { run_id: "run-1" })),
    getCandidate: vi.fn().mockResolvedValue(candidate),
    getSnapshot: vi.fn().mockResolvedValue(snapshot),
    refreshSource: vi.fn().mockResolvedValue({ ...registration, job_id: "discovery-2", epoch_id: "epoch-2" }),
    getRun: vi.fn().mockResolvedValue(oneStepRun()),
    submitRun: vi.fn().mockResolvedValue(job("run-job", "queued")),
  };
}

describe("FirstForecast", () => {
  beforeEach(() => vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-10-24T12:00:00Z")));
  afterEach(() => vi.restoreAllMocks());
  it("uses the source's frozen snapshot and opens a run only after an explicit action", async () => {
    const api = client();
    const onRunReady = vi.fn();
    render(<FirstForecast client={api} registration={registration} onRunReady={onRunReady} />);
    const button = await screen.findByRole("button", { name: "Calcola la prima previsione" });
    expect(api.submitRun).not.toHaveBeenCalled();
    await userEvent.click(button);
    await waitFor(() => expect(onRunReady).toHaveBeenCalledWith("run-1"));
    expect(screen.getByLabelText("Previsione iniziale")).toHaveTextContent("3 count");
    expect(api.submitRun).toHaveBeenCalledWith(expect.objectContaining({
      kind: "run", graph: candidate.graph, snapshot_ids: { sales: "snapshot-1" }, as_of: snapshot.as_of,
    }));
    expect(screen.getByText(/non ancora valutata/i)).toBeVisible();
  });

  it.each(["submission", "polling"])("retries %s failures without issuing another forecast", async (failure) => {
    const api = client();
    if (failure === "submission") api.submitRun.mockRejectedValueOnce(new Error("response lost"));
    else {
      const getJob = api.getJob.getMockImplementation()!;
      let lost = false;
      api.getJob.mockImplementation(async (id: string) => {
        if (id === "run-job" && !lost) { lost = true; throw new Error("response lost"); }
        return getJob(id);
      });
    }
    render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    const calculate = await screen.findByRole("button", { name: "Calcola la prima previsione" });
    await userEvent.click(calculate);
    expect(await screen.findByRole("alert")).toHaveTextContent("response lost");
    await userEvent.click(calculate);
    expect(await screen.findByLabelText("Previsione iniziale")).toHaveTextContent("3 count");
    expect(api.submitRun.mock.calls[1][0].key).toBe(api.submitRun.mock.calls[0][0].key);
  });

  it("does not offer a forecast when discovery produced no snapshot", async () => {
    const api = client();
    api.getJob.mockResolvedValue(job("discovery-1", "completed", { candidate_ids: ["candidate-1"], source_snapshot_ids: [] }));
    render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    expect(await screen.findByText(/nessun dato pronto/i)).toBeVisible();
    expect(api.submitRun).not.toHaveBeenCalled();
  });

  it("does not run an unsupported candidate or a target already in the past", async () => {
    const api = client();
    api.getCandidate.mockResolvedValue({ ...candidate, executable: false });
    const view = render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    expect(await screen.findByText(/non è disponibile una previsione/i)).toBeVisible();
    view.unmount();
    const stale = client();
    stale.getSnapshot.mockResolvedValue({ ...snapshot, as_of: "2026-10-26T12:00:00Z" });
    render(<FirstForecast client={stale} registration={registration} onRunReady={vi.fn()} />);
    expect(await screen.findByText(/dati troppo vecchi/i)).toBeVisible();
    expect(stale.submitRun).not.toHaveBeenCalled();
  });

  it("reports a failed run instead of opening it", async () => {
    const api = client();
    api.getJob.mockImplementation(async (id: string) => id === "discovery-1"
      ? job(id, "completed", { candidate_ids: ["candidate-1"], source_snapshot_ids: ["snapshot-1"] })
      : job(id, "failed"));
    const onRunReady = vi.fn();
    render(<FirstForecast client={api} registration={registration} onRunReady={onRunReady} />);
    await userEvent.click(await screen.findByRole("button", { name: "Calcola la prima previsione" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/non è riuscito/i);
    expect(onRunReady).not.toHaveBeenCalled();
  });

  it("does not treat a completed job with a failed run as a forecast", async () => {
    const api = client();
    api.getRun.mockResolvedValue(makeRun({ state: "failed", as_of: snapshot.as_of }));
    const onRunReady = vi.fn();
    render(<FirstForecast client={api} registration={registration} onRunReady={onRunReady} />);
    await userEvent.click(await screen.findByRole("button", { name: "Calcola la prima previsione" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/non ha prodotto/i);
    expect(onRunReady).not.toHaveBeenCalled();
  });

  it("starts a new attempt after a confirmed terminal job failure", async () => {
    const api = client();
    const getJob = api.getJob.getMockImplementation()!;
    let failed = false;
    api.getJob.mockImplementation(async (id: string) => {
      if (id === "run-job" && !failed) { failed = true; return job(id, "failed"); }
      return getJob(id);
    });
    render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    const calculate = await screen.findByRole("button", { name: "Calcola la prima previsione" });
    await userEvent.click(calculate);
    expect(await screen.findByRole("alert")).toHaveTextContent(/non è riuscito/i);
    await userEvent.click(calculate);
    expect(await screen.findByLabelText("Previsione iniziale")).toHaveTextContent("3 count");
    expect(api.submitRun.mock.calls[1][0].key).not.toBe(api.submitRun.mock.calls[0][0].key);
  });

  it("rejects a candidate belonging to another source", async () => {
    const api = client();
    api.getCandidate.mockResolvedValue({ ...candidate, source_ids: ["other"] });
    render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    expect(await screen.findByText(/non è disponibile una previsione/i)).toBeVisible();
    expect(api.submitRun).not.toHaveBeenCalled();
  });

  it("does not label a different model as the baseline", async () => {
    const api = client();
    api.getCandidate.mockResolvedValue({ ...candidate, graph: { ...candidate.graph, nodes: candidate.graph.nodes.map((node) =>
      node.node_id === "forecast" ? { ...node, config: { ...node.config, provider: "timestral" } } : node) } });
    render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    expect(await screen.findByText(/non è disponibile una previsione/i)).toBeVisible();
    expect(api.submitRun).not.toHaveBeenCalled();
  });

  it("does not present a historical target as a future forecast", async () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-10-26T12:00:00Z"));
    const api = client();
    render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    expect(await screen.findByText(/dati troppo vecchi/i)).toBeVisible();
    expect(api.submitRun).not.toHaveBeenCalled();
  });

  it("refreshes the source explicitly and prepares a new snapshot", async () => {
    const api = client();
    api.getJob.mockImplementation(async (id: string) => id === "discovery-1"
      ? job(id, "completed", { candidate_ids: ["old-candidate"], source_snapshot_ids: ["old-snapshot"] })
      : job(id, "completed", { candidate_ids: ["candidate-2"], source_snapshot_ids: ["snapshot-1"] }));
    api.getCandidate.mockImplementation(async (id: string) => id === "old-candidate"
      ? candidate : { ...candidate, candidate_id: "candidate-2", epoch_id: "epoch-2" });
    api.getSnapshot.mockImplementation(async (id: string) => id === "old-snapshot"
      ? { ...snapshot, snapshot_id: id, as_of: "2026-10-26T12:00:00Z" } : snapshot);
    render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    expect(await screen.findByText(/dati troppo vecchi/i)).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Aggiorna dati" }));
    expect(await screen.findByRole("button", { name: "Calcola la prima previsione" })).toBeVisible();
    expect(api.refreshSource).toHaveBeenCalledWith("sales", expect.any(String));
    expect(api.submitRun).not.toHaveBeenCalled();
  });

  it("reuses the refresh key when retrying after an ambiguous response", async () => {
    const api = client();
    api.refreshSource.mockRejectedValueOnce(new Error("connection lost after submission"));
    render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    const refresh = await screen.findByRole("button", { name: "Aggiorna dati" });
    await userEvent.click(refresh);
    expect(await screen.findByRole("alert")).toHaveTextContent("connection lost after submission");
    await userEvent.click(refresh);
    await waitFor(() => expect(api.refreshSource).toHaveBeenCalledTimes(2));
    expect(api.refreshSource.mock.calls[1][1]).toBe(api.refreshSource.mock.calls[0][1]);
  });

  it("ignores discovery responses from a source that has been replaced", async () => {
    const api = client();
    let finishOld: (value: JobView) => void = () => {};
    api.getJob.mockImplementation((id: string) => id === "discovery-1"
      ? new Promise<JobView>((resolve) => { finishOld = resolve; })
      : Promise.resolve(job(id, "completed", { candidate_ids: [], source_snapshot_ids: [] })));
    const view = render(<FirstForecast client={api} registration={registration} onRunReady={vi.fn()} />);
    await waitFor(() => expect(api.getJob).toHaveBeenCalledWith("discovery-1"));
    view.rerender(<FirstForecast client={api} registration={{ ...registration, source_id: "other", job_id: "new-job", epoch_id: "new-epoch" }} onRunReady={vi.fn()} />);
    expect(await screen.findByText(/nessun dato pronto/i)).toBeVisible();
    await act(async () => finishOld(job("discovery-1", "completed", { candidate_ids: ["candidate-1"], source_snapshot_ids: ["snapshot-1"] })));
    expect(api.getCandidate).not.toHaveBeenCalled();
  });

  it("does not poll or open a run after its source panel is removed", async () => {
    const api = client();
    let finishSubmit: (value: JobView) => void = () => {};
    api.submitRun.mockImplementation(() => new Promise<JobView>((resolve) => { finishSubmit = resolve; }));
    const onRunReady = vi.fn();
    const view = render(<FirstForecast client={api} registration={registration} onRunReady={onRunReady} />);
    await userEvent.click(await screen.findByRole("button", { name: "Calcola la prima previsione" }));
    view.unmount();
    await act(async () => finishSubmit(job("run-job", "queued")));
    expect(api.getJob).not.toHaveBeenCalledWith("run-job");
    expect(onRunReady).not.toHaveBeenCalled();
  });
});
