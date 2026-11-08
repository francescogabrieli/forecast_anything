import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { ApiClient } from "./api/client";
import { makeRun } from "./test/fixtures";
afterEach(() => vi.restoreAllMocks());
beforeEach(() => { window.sessionStorage.clear(); window.location.hash = "home"; vi.spyOn(ApiClient.prototype, "getHealth").mockResolvedValue({ status: "ok", worker: "running", worker_model: "loaded" }); });
describe("product navigation", () => {
  it("opens setup from home and responds to browser hash navigation", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Configura il workspace" }));
    act(() => { window.location.hash = "workspace"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
    expect(screen.getByLabelText("Token workspace")).toBeInTheDocument();
    act(() => { window.location.hash = "home"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
    expect(screen.queryByLabelText("Token workspace")).not.toBeInTheDocument();
  });
  it("keeps the active workspace view when an evidence anchor changes", () => {
    render(<App />);
    act(() => { window.location.hash = "observatory"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
    expect(screen.getByRole("heading", { name: "Osservatorio" })).toBeInTheDocument();
    act(() => { window.location.hash = "snapshot-sales"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
    expect(screen.getByRole("heading", { name: "Osservatorio" })).toBeInTheDocument();
  });
  it("moves focus into the mobile menu and restores it on Escape", () => {
    render(<App />);
    const button = screen.getByRole("button", { name: "Apri navigazione" });
    fireEvent.click(button);
    expect(screen.getByRole("link", { name: "Home" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("navigation"), { key: "Escape" });
    expect(button).toHaveFocus();
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});

it("reopens the same Home run after selecting a different run in the observatory", async () => {
  vi.spyOn(ApiClient.prototype, "getCapabilities").mockResolvedValue({} as Awaited<ReturnType<ApiClient["getCapabilities"]>>);
  vi.spyOn(ApiClient.prototype, "getWorkspace").mockResolvedValue({ workspace_id: "a".repeat(32) });
  vi.spyOn(ApiClient.prototype, "getSources").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getRecentRuns").mockResolvedValue([makeRun({ run_id: "run-a" })]);
  vi.spyOn(ApiClient.prototype, "getWatches").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getEvents").mockResolvedValue([
    { cursor: 1, event_id: "event-b", kind: "run_completed", run_id: "run-b", payload: {} },
  ]);
  vi.spyOn(ApiClient.prototype, "streamEvents").mockResolvedValue();
  vi.spyOn(ApiClient.prototype, "getRun").mockImplementation(async (id) => makeRun({ run_id: id }));
  vi.spyOn(ApiClient.prototype, "getGraph").mockResolvedValue({ graph_id: "graph-1", version: 1, nodes: [] });
  vi.spyOn(ApiClient.prototype, "getRunEvaluations").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getSnapshot").mockResolvedValue({ snapshot_id: "snapshot-1", as_of: "2026-10-24T00:00:00Z", observations: [], assumptions: [] });
  render(<App />);
  const navigate = (page: string) => act(() => {
    window.location.hash = page;
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  navigate("workspace");
  fireEvent.change(screen.getByLabelText("Token workspace"), { target: { value: "test-token" } });
  fireEvent.click(screen.getByRole("button", { name: /Apri il workspace/ }));
  await waitFor(() => expect(window.location.hash).toBe("#sources"));
  navigate("home");
  fireEvent.click(await screen.findByRole("button", { name: /sales.*Valutazioni nel dettaglio/ }));
  navigate("observatory");
  expect(await screen.findByText("ID run: run-a")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Apri run run-b" }));
  expect(await screen.findByText("ID run: run-b")).toBeVisible();
  navigate("home");
  fireEvent.click(screen.getByRole("button", { name: /sales.*Valutazioni nel dettaglio/ }));
  navigate("observatory");
  expect(await screen.findByText("ID run: run-a")).toBeVisible();
  expect(screen.queryByText("ID run: run-b")).not.toBeInTheDocument();
});

it.each(["snapshot-input", "evaluation-record", "run-details-title"])("restores the Observatory for the evidence history target %s", (hash) => {
  render(<App />);
  const navigate = (value: string) => act(() => { window.location.hash = value; window.dispatchEvent(new HashChangeEvent("hashchange")); });
  navigate("observatory");
  navigate(hash);
  navigate("home");
  expect(screen.getByRole("heading", { name: "Home" })).toBeVisible();
  navigate(hash);
  expect(screen.getByRole("heading", { name: "Osservatorio" })).toBeVisible();
  expect(window.location.hash).toBe(`#${hash}`);
});

it("focuses the restored evidence target after the Observatory becomes visible", () => {
  render(<><App /><h4 id="snapshot-focus">Snapshot focus</h4></>);
  act(() => { window.location.hash = "snapshot-focus"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
  expect(screen.getByRole("heading", { name: "Snapshot focus" })).toHaveFocus();
});

it("does not declare the workspace connected when the credential is rejected", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "unauthorized" }), { status: 401 })));
  render(<App />);
  act(() => { window.location.hash = "workspace"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
  fireEvent.change(screen.getByLabelText("Token workspace"), { target: { value: "wrong" } });
  fireEvent.click(screen.getByRole("button", { name: /Apri il workspace/ }));
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(screen.getByText("Workspace da configurare")).toBeVisible();
  expect(window.location.hash).toBe("#workspace");
  vi.unstubAllGlobals();
});

it("ignores a rejected connection attempt after a newer connection succeeded", async () => {
  let rejectFirst!: (error: Error) => void;
  const first = new Promise<never>((_, reject) => { rejectFirst = reject; });
  vi.spyOn(ApiClient.prototype, "getCapabilities").mockReturnValueOnce(first).mockResolvedValueOnce({});
  vi.spyOn(ApiClient.prototype, "getWorkspace").mockResolvedValue({ workspace_id: "a".repeat(32) });
  vi.spyOn(ApiClient.prototype, "getSources").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getRecentRuns").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getWatches").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getEvents").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "streamEvents").mockResolvedValue();
  render(<App />);
  act(() => { window.location.hash = "workspace"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
  fireEvent.change(screen.getByLabelText("Token workspace"), { target: { value: "first" } });
  fireEvent.click(screen.getByRole("button", { name: /Apri il workspace/ }));
  fireEvent.change(screen.getByLabelText("Token workspace"), { target: { value: "second" } });
  fireEvent.click(screen.getByRole("button", { name: /Apri il workspace/ }));
  await waitFor(() => expect(window.location.hash).toBe("#sources"));
  await act(async () => { rejectFirst(new Error("late error")); });
  act(() => { window.location.hash = "workspace"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});


it("opens the linked run after connection and restores it from a browser session on reload", async () => {
  const workspaceId = "a".repeat(32);
  vi.spyOn(ApiClient.prototype, "getCapabilities").mockResolvedValue({});
  vi.spyOn(ApiClient.prototype, "getWorkspace").mockResolvedValue({ workspace_id: workspaceId });
  vi.spyOn(ApiClient.prototype, "getSources").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getRecentRuns").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getWatches").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getEvents").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "streamEvents").mockResolvedValue();
  vi.spyOn(ApiClient.prototype, "getRun").mockImplementation(async (id) => makeRun({ run_id: id }));
  vi.spyOn(ApiClient.prototype, "getGraph").mockResolvedValue({ graph_id: "graph-1", version: 1, nodes: [] });
  vi.spyOn(ApiClient.prototype, "getRunEvaluations").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getSnapshot").mockResolvedValue({ snapshot_id: "snapshot-1", as_of: "2026-10-24T00:00:00Z", observations: [], assumptions: [] });
  vi.spyOn(ApiClient.prototype, "getForecastPresentation").mockResolvedValue({ run_id: "run-a", as_of: "2026-10-24T00:00:00Z", graph_id: "graph-1", graph_version: 1, state: "completed", primary_node_id: "model", points: [], providers: [], providers_truncated: false, snapshot_ids: [], snapshot_ids_truncated: false, truncated: false, total_point_count: 0 });
  const hash = `#/w/${workspaceId}/run/run-a`;
  window.location.hash = hash;
  const view = render(<App />);
  fireEvent.change(screen.getByLabelText("Token workspace"), { target: { value: "token" } });
  fireEvent.click(screen.getByRole("button", { name: /Apri il workspace/ }));
  expect(await screen.findByText("ID run: run-a")).toBeVisible();
  expect(window.location.hash).toBe(hash);
  view.unmount();
  render(<App />);
  expect(await screen.findByText("ID run: run-a")).toBeVisible();
  expect(window.location.hash).toBe(hash);
});

it("does not open a linked resource from a different workspace", async () => {
  vi.spyOn(ApiClient.prototype, "getCapabilities").mockResolvedValue({});
  vi.spyOn(ApiClient.prototype, "getWorkspace").mockResolvedValue({ workspace_id: "b".repeat(32) });
  const getRun = vi.spyOn(ApiClient.prototype, "getRun");
  window.location.hash = `#/w/${"a".repeat(32)}/run/run-a`;
  render(<App />);
  fireEvent.change(screen.getByLabelText("Token workspace"), { target: { value: "token" } });
  fireEvent.click(screen.getByRole("button", { name: /Apri il workspace/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/workspace diverso/i);
  expect(getRun).not.toHaveBeenCalled();
});

it("shows API, authentication, worker and model readiness separately", async () => {
  vi.spyOn(ApiClient.prototype, "getCapabilities").mockResolvedValue({});
  vi.spyOn(ApiClient.prototype, "getWorkspace").mockResolvedValue({ workspace_id: "a".repeat(32) });
  vi.spyOn(ApiClient.prototype, "getHealth").mockResolvedValue({ status: "ok", worker: "running", worker_model: "loaded" });
  vi.spyOn(ApiClient.prototype, "getSources").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getRecentRuns").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getWatches").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "getEvents").mockResolvedValue([]);
  vi.spyOn(ApiClient.prototype, "streamEvents").mockResolvedValue();
  render(<App />);
  act(() => { window.location.hash = "workspace"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
  fireEvent.change(screen.getByLabelText("Token workspace"), { target: { value: "token" } });
  fireEvent.click(screen.getByRole("button", { name: /Apri il workspace/ }));
  await waitFor(() => expect(window.location.hash).toBe("#sources"));
  act(() => { window.location.hash = "workspace"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
  expect(screen.getByText("API disponibile")).toBeVisible();
  expect(screen.getByText("Autenticazione valida")).toBeVisible();
  expect(screen.getByText("Worker: running")).toBeVisible();
  expect(screen.getByText("Modello caricato dal worker: loaded")).toBeVisible();
  expect(screen.getByText("Disponibilità modello: non richiesto")).toBeVisible();
});
