import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { ApiClient } from "./api/client";
import { makeRun } from "./test/fixtures";
afterEach(() => vi.restoreAllMocks());
beforeEach(() => { window.location.hash = "home"; });
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
