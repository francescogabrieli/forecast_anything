import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ApiClient } from "../../api/client";
import { ContextView } from "./ContextView";

it("shows the primary forecast with the aligned baseline and explicit truncation", async () => {
  const client = new ApiClient("http://localhost:8000", "token");
  vi.spyOn(client, "getForecastPresentation").mockResolvedValue({
    run_id: "run-a", primary_node_id: "model", baseline_node_id: "baseline", as_of: "2026-11-08T00:00:00Z", state: "completed",
    graph_id: "graph", graph_version: 1, snapshot_ids: [], snapshot_ids_truncated: false,
    providers: [{ node_id: "model", requested_provider: "timestral", actual_provider: "timestral" }, { node_id: "baseline", requested_provider: "seasonal_naive", actual_provider: "seasonal_naive" }], providers_truncated: false, total_point_count: 3, truncated: true,
    points: [
      { node_id: "model", series_id: "sales", timestamp: "2026-11-09T00:00:00Z", unit: "count", representation: "point", point: 23, quantiles: {}, quantiles_truncated: false, sample_count: 0 },
      { node_id: "baseline", series_id: "sales", timestamp: "2026-11-09T00:00:00Z", unit: "count", representation: "point", point: 22, quantiles: {}, quantiles_truncated: false, sample_count: 0 },
    ],
  });
  render(<ContextView client={client} workspaceId={"a".repeat(32)} resource={{ kind: "run", id: "run-a" }} />);
  expect(await screen.findByText("23")).toBeVisible();
  expect(screen.getByText("22")).toBeVisible();
  expect(screen.getByText(/risultati troncati/i)).toBeVisible();
});

it("renders saved question references and marks historical references", async () => {
  const client = new ApiClient("http://localhost:8000", "token");
  vi.spyOn(client, "getQuestionPresentation").mockResolvedValue({ question: { question_id: "q", title: "Domanda salvata", status: "open", muted: false, priority: 3, current_revision: 2, revision: { question_id: "q", revision: 2, meaning: "Prevedere", source_ids: [], selection: { provider: "timestral", horizon: 1 }, created_at: "2026-11-08T00:00:00Z" }, revision_count: 2, reference_count: 1, created_at: "2026-11-08T00:00:00Z", updated_at: "2026-11-08T00:00:00Z" }, references: [{ applies_to_current_revision: false, reference: { question_id: "q", revision: 1, reference_id: "ref", target_type: "run", target_id: "old", note: "", created_at: "2026-11-08T00:00:00Z" } }], next_offset: null, inbox_events: [], inbox_total_count: 0 });
  render(<ContextView client={client} workspaceId={"a".repeat(32)} resource={{ kind: "question", id: "q" }} />);
  expect(await screen.findByText("Domanda salvata")).toBeVisible();
  expect(screen.getByText(/riferimento storico/i)).toBeVisible();
  expect(screen.getByRole("link", { name: /old/ })).toHaveAttribute("href", `#/w/${"a".repeat(32)}/run/old`);
});

it("shows question controls and recent provisional or failed delivery updates", async () => {
  const client = new ApiClient("http://localhost:8000", "token");
  vi.spyOn(client, "getQuestionPresentation").mockResolvedValue({
    question: { question_id: "q", title: "Domanda salvata", status: "open", muted: true, priority: 0, current_revision: 1, revision: { question_id: "q", revision: 1, meaning: "Prevedere", source_ids: [], selection: { provider: "timestral", horizon: 1 }, created_at: "2026-11-08T00:00:00Z" }, revision_count: 1, reference_count: 0, created_at: "2026-11-08T00:00:00Z", updated_at: "2026-11-08T00:00:00Z" },
    references: [], next_offset: null, inbox_total_count: 1,
    inbox_events: [{ event_id: "event-1", question_id: "q", revision: 1, event_kind: "forecast_issued", transition_id: "run-1", run_id: "run-1", occurred_at: "2026-11-08T00:00:00Z", muted: false, summary: "La previsione resta provvisoria.", payload: { quality: "provisional" }, delivery_states: ["delivery_failed"] }],
  });
  render(<ContextView client={client} workspaceId={"a".repeat(32)} resource={{ kind: "question", id: "q" }} />);
  expect(await screen.findByText("Domanda salvata")).toBeVisible();
  expect(screen.getByText(/Notifiche: silenziate · Priorità: 0/)).toBeVisible();
  expect(screen.getByText(/Qualità provvisoria/)).toBeVisible();
  expect(screen.getByText("Consegna fallita")).toBeVisible();
});

it("shows backtest chart and equivalent table including excluded origins", async () => {
  const client = new ApiClient("http://localhost:8000", "token");
  vi.spyOn(client, "getReportPresentation").mockResolvedValue({ summary: { report_id: "report-1", backtest_id: "backtest-1", status: "completed", selection: { provider: "timestral", horizon: 1 }, interpretation_limit: "Solo dati registrati", partitions: [], final_origin_points: [ { ordinal: 1, target_start: "2026-11-01T00:00:00Z", target_end: "2026-11-01T00:00:00Z", status: "evaluated", model_mae: 2, baseline_mae: 3 }, { ordinal: 2, target_start: "2026-11-02T00:00:00Z", target_end: "2026-11-02T00:00:00Z", status: "excluded", model_mae: null, baseline_mae: null, reason_code: "missing_actuals" } ], assumptions: [], source_id: "sales", source_revision: "r" } } as unknown as Awaited<ReturnType<ApiClient["getReportPresentation"]>>);
  vi.spyOn(client, "getReportOrigins").mockResolvedValue({ backtest_id: "backtest-1", offset: 0, limit: 50, origins: [], next_offset: null });
  render(<ContextView client={client} workspaceId={"a".repeat(32)} resource={{ kind: "report", id: "report-1" }} />);
  expect(await screen.findByRole("img", { name: /grafico.*error/i })).toBeVisible();
  expect(screen.getByRole("table", { name: /errori per origine/i })).toHaveTextContent("missing_actuals");
  expect(screen.getByRole("table", { name: /errori per origine/i })).toHaveTextContent("3");
});

it("announces a new run while retaining the linked run", async () => {
  const client = new ApiClient("http://localhost:8000", "token");
  let emit!: (event: import("../../api/schema.generated").EventRecord) => void;
  vi.spyOn(client, "getEvents").mockResolvedValue([]);
  vi.spyOn(client, "streamEvents").mockImplementation(async (_cursor, onEvent) => { emit = onEvent; });
  vi.spyOn(client, "getForecastPresentation").mockResolvedValue({ run_id: "run-a", primary_node_id: "model", as_of: "2026-11-08T00:00:00Z", state: "completed", graph_id: "graph", graph_version: 1, snapshot_ids: [], snapshot_ids_truncated: false, providers: [], providers_truncated: false, total_point_count: 0, truncated: false, points: [] });
  render(<ContextView client={client} workspaceId={"a".repeat(32)} resource={{ kind: "run", id: "run-a" }} />);
  expect(await screen.findByText("ID run: run-a")).toBeVisible();
  await vi.waitFor(() => expect(emit).toBeTypeOf("function"));
  const { act } = await import("@testing-library/react");
  await act(async () => { emit({ cursor: 1, event_id: "new", kind: "run_completed", run_id: "run-b", payload: {} }); });
  expect(screen.getByText(/Nuovo risultato disponibile: run-b/)).toBeVisible();
  expect(screen.getByText("ID run: run-a")).toBeVisible();
});

it("uses the explicitly associated comparator even when another seasonal node is aligned", async () => {
  const client = new ApiClient("http://localhost:8000", "token");
  const point = (node_id: string, value: number) => ({ node_id, series_id: "sales", timestamp: "2026-11-09T00:00:00Z", unit: "count", representation: "point" as const, point: value, quantiles: {}, quantiles_truncated: false, sample_count: 0 });
  vi.spyOn(client, "getForecastPresentation").mockResolvedValue({ run_id: "run-a", primary_node_id: "model", baseline_node_id: "baseline", as_of: "2026-11-08T00:00:00Z", state: "completed", graph_id: "graph", graph_version: 1, snapshot_ids: [], snapshot_ids_truncated: false, providers: [{ node_id: "other", requested_provider: "seasonal_naive", actual_provider: "seasonal_naive" }, { node_id: "baseline", requested_provider: "seasonal_naive", actual_provider: "seasonal_naive" }], providers_truncated: false, total_point_count: 3, truncated: false, points: [point("model", 23), point("other", 99), point("baseline", 22)] });
  render(<ContextView client={client} workspaceId={"a".repeat(32)} resource={{ kind: "run", id: "run-a" }} />);
  expect(await screen.findByText("22")).toBeVisible();
  expect(screen.queryByText("99")).not.toBeInTheDocument();
});

it("does not infer a comparator when no baseline reference is present", async () => {
  const client = new ApiClient("http://localhost:8000", "token");
  const point = (node_id: string, value: number) => ({ node_id, series_id: "sales", timestamp: "2026-11-09T00:00:00Z", unit: "count", representation: "point" as const, point: value, quantiles: {}, quantiles_truncated: false, sample_count: 0 });
  vi.spyOn(client, "getForecastPresentation").mockResolvedValue({ run_id: "run-a", primary_node_id: "model", as_of: "2026-11-08T00:00:00Z", state: "completed", graph_id: "graph", graph_version: 1, snapshot_ids: [], snapshot_ids_truncated: false, providers: [{ node_id: "other", requested_provider: "seasonal_naive", actual_provider: "seasonal_naive" }], providers_truncated: false, total_point_count: 2, truncated: false, points: [point("model", 23), point("other", 99)] });
  render(<ContextView client={client} workspaceId={"a".repeat(32)} resource={{ kind: "run", id: "run-a" }} />);
  expect(await screen.findByText("Non disponibile o non confrontabile")).toBeVisible();
  expect(screen.queryByText("99")).not.toBeInTheDocument();
});

it("keeps a report readable when origin detail cannot be loaded", async () => {
  const client = new ApiClient("http://localhost:8000", "token");
  vi.spyOn(client, "getReportPresentation").mockResolvedValue({ summary: { report_id: "report-1", backtest_id: "backtest-1", status: "completed", selection: { provider: "timestral", horizon: 1 }, interpretation_limit: "Solo dati registrati", partitions: [], final_origin_points: [], assumptions: [], source_id: "sales", source_revision: "r" } } as unknown as Awaited<ReturnType<ApiClient["getReportPresentation"]>>);
  vi.spyOn(client, "getReportOrigins").mockRejectedValue(new Error("host tool unavailable"));
  render(<ContextView client={client} workspaceId={"a".repeat(32)} resource={{ kind: "report", id: "report-1" }} />);
  expect(await screen.findByText("ID report: report-1")).toBeVisible();
  expect(screen.getByText(/Dettaglio delle origini non disponibile/)).toBeVisible();
});
