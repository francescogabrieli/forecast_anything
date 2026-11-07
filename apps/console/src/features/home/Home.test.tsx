import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../../api/client";
import { Home } from "./Home";
import { makeRun } from "../../test/fixtures";
vi.mock("../sources/FirstForecast", () => ({ FirstForecast: ({ registration }: { registration: { source_id: string } }) => <p>Pronta: {registration.source_id}</p> }));
const source = { source_id: "sales", kind: "csv", revision: "r1", refresh_seconds: 60 };
const api = (extra = {}) => ({ getSources: vi.fn().mockResolvedValue([source]), getRecentRuns: vi.fn().mockResolvedValue([]), refreshSource: vi.fn().mockResolvedValue({ source_id: "sales", job_id: "job1" }), ...extra }) as unknown as ApiClient;
describe("Home", () => {
  it("refreshes a returning source explicitly before preparing its forecast and reuses ambiguous retry keys", async () => {
    const client = api({ refreshSource: vi.fn().mockRejectedValueOnce(new Error("network interrupted")).mockResolvedValue({ source_id: "sales", job_id: "job1" }) });
    render(<Home client={client} onRunReady={vi.fn()} />);
    await screen.findByRole("option", { name: "sales" });
    expect(client.refreshSource).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Prepara previsione" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("network interrupted");
    fireEvent.click(screen.getByRole("button", { name: "Prepara previsione" }));
    expect(await screen.findByText("Pronta: sales")).toBeInTheDocument();
    const calls = vi.mocked(client.refreshSource).mock.calls;
    expect(calls[0][1]).toBeTruthy();
    expect(calls[1][1]).toBe(calls[0][1]);
  });
  it("distinguishes failed source and history reads from empty lists", async () => {
    render(<Home client={api({ getSources: vi.fn().mockRejectedValue(new Error("sources offline")), getRecentRuns: vi.fn().mockRejectedValue(new Error("history offline")) })} onRunReady={vi.fn()} />);
    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(2));
    expect(screen.queryByText("Nessuna fonte collegata.")).not.toBeInTheDocument();
    expect(screen.queryByText("Nessuna previsione registrata.")).not.toBeInTheDocument();
  });
  it("ignores old workspace responses after the client changes", async () => {
    let resolve!: (value: unknown[]) => void;
    const first = api({ getSources: vi.fn().mockReturnValue(new Promise((done) => { resolve = done; })) });
    const { rerender } = render(<Home client={first} onRunReady={vi.fn()} />);
    rerender(<Home client={api({ getSources: vi.fn().mockResolvedValue([]) })} onRunReady={vi.fn()} />);
    await screen.findByText("Nessuna fonte collegata.");
    await act(async () => { resolve([source]); });
    expect(screen.queryByRole("option", { name: "sales" })).not.toBeInTheDocument();
  });
  it("preserves an ambiguous refresh key when navigating away and returning", async () => {
    const client = api({ refreshSource: vi.fn().mockRejectedValueOnce(new Error("interrupted")).mockResolvedValue({ source_id: "sales", job_id: "job1" }) });
    const ready = vi.fn();
    const { rerender } = render(<Home client={client} onRunReady={ready} active/>);
    await screen.findByRole("option", { name: "sales" });
    fireEvent.click(screen.getByRole("button", { name: "Prepara previsione" }));
    await screen.findByRole("alert");
    rerender(<Home client={client} onRunReady={ready} active={false}/>);
    rerender(<Home client={client} onRunReady={ready} active/>);
    await screen.findByRole("option", { name: "sales" });
    fireEvent.click(screen.getByRole("button", { name: "Prepara previsione" }));
    await screen.findByText("Pronta: sales");
    const calls = vi.mocked(client.refreshSource).mock.calls;
    expect(calls[1][1]).toBe(calls[0][1]);
  });
  it("suppresses a refresh registration returned by a replaced workspace", async () => {
    let resolve!: (value: unknown) => void;
    const first = api({ refreshSource: vi.fn().mockReturnValue(new Promise((done) => { resolve = done; })) });
    const ready = vi.fn();
    const { rerender } = render(<Home client={first} onRunReady={ready}/>);
    await screen.findByRole("option", { name: "sales" });
    fireEvent.click(screen.getByRole("button", { name: "Prepara previsione" }));
    rerender(<Home client={api({ getSources: vi.fn().mockResolvedValue([]) })} onRunReady={ready}/>);
    await screen.findByText("Nessuna fonte collegata.");
    await act(async () => { resolve({ source_id: "sales", job_id: "old-job" }); });
    expect(screen.queryByText("Pronta: sales")).not.toBeInTheDocument();
  });

});

it.each(["forecast", "model", "fallback"])("shows the primary %s result in recent forecasts", async (kind) => {
  const run = makeRun();
  const result = run.results.forecast;
  run.results = { baseline: { ...result, point: [[91]], series_ids: ["comparator"] }, model: { ...result, point: [[7]], series_ids: ["selected"] } };
  if (kind === "forecast") run.results.forecast = { ...result, point: [[5]], series_ids: ["legacy"] };
  if (kind === "fallback") delete run.results.model;
  render(<Home client={api({ getRecentRuns: vi.fn().mockResolvedValue([run]) })} onRunReady={vi.fn()} />);
  const expected = kind === "forecast" ? /legacy.*5/ : kind === "model" ? /selected.*7/ : /comparator.*91/;
  expect(await screen.findByRole("button", { name: expected })).toBeVisible();
});
