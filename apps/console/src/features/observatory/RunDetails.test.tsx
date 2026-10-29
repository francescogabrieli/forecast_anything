import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeRun, makeWatch } from "../../test/fixtures";
import type { GraphSpec, Snapshot } from "../../api/schema.generated";
import { RunDetails } from "./RunDetails";

describe("RunDetails", () => {
  it("does not draw uncertainty for a point-only forecast", () => {
    render(<RunDetails run={makeRun()} evaluations={[]} watch={makeWatch({ quality: "stale" })} />);
    expect(screen.getByRole("heading", { name: "Risultato" })).toBeVisible();
    expect(screen.getByText("ID run: run-1")).toBeVisible();
    expect(screen.getByText("Previsione scaduta")).toBeVisible();
    expect(screen.queryByLabelText("Intervallo previsto")).not.toBeInTheDocument();
  });

  it("shows experimental state and links evidence to its run inputs", () => {
    const run = makeRun({ state: "experimental", evidence_ids: ["evaluation-1"] });
    const evaluation = {
      evaluation_id: "evaluation-1",
      run_id: "run-1",
      actuals_snapshot_id: "snapshot-actuals",
      status: "evaluated" as const,
      metrics: { mae: 0.5 },
      origin_count: 4,
      assumptions: ["Actuals were aligned by timestamp."],
      discovery: null,
    };
    render(<RunDetails run={run} evaluations={[evaluation]} />);

    expect(screen.getByText(/risultato sperimentale/i)).toBeVisible();
    expect(screen.getByRole("link", { name: "evaluation-1" })).toHaveAttribute("href", "#evaluation-evaluation-1");
    expect(screen.getByRole("link", { name: /snapshot-actuals/ })).toHaveAttribute("href", "#snapshot-snapshot-actuals");
  });

  it("shows the time and timezone for hourly forecast targets", () => {
    const run = makeRun();
    run.results.forecast.timestamps = ["2026-10-25T05:00:00Z", "2026-10-25T06:00:00Z"];
    render(<RunDetails run={run} evaluations={[]} />);
    fireEvent.click(screen.getByText("Dati e assunzioni del risultato"));
    expect(screen.getByRole("cell", { name: "25/10/2026, 05:00 UTC" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "25/10/2026, 06:00 UTC" })).toBeVisible();
  });
});

it("shows issued values before technical metadata and names unevaluated forecasts", () => {
  const { container } = render(<RunDetails run={makeRun()} evaluations={[]} />);
  expect(screen.getByText("Non ancora valutata")).toBeVisible();
  expect(screen.getByRole("img", { name: /sales.*count/i })).toBeVisible();
  expect(container.querySelector('.forecast-summary')!.compareDocumentPosition(screen.getByText('ID run: run-1')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
it("shows supplied evaluation metrics", () => {
  render(<RunDetails run={makeRun()} evaluations={[{ evaluation_id: 'e', run_id: 'run-1', actuals_snapshot_id: 'a', status: 'evaluated', metrics: { mae: 0.5 }, origin_count: 4, assumptions: [] }]} />);
  expect(screen.getByText('MAE')).toBeVisible();
  expect(screen.getByText('0.5')).toBeVisible();
});

it('selects forecast as the primary result and retains other nodes in technical disclosure', () => {
  const run = makeRun();
  run.results = { reference: { ...run.results.forecast, point: [[98, 99]], provider_id: 'reference_model' }, ...run.results };
  const { container } = render(<RunDetails run={run} evaluations={[]} />);
  expect(screen.getAllByRole('img')).toHaveLength(1);
  expect(container.querySelector('.forecast-summary')).toHaveTextContent('forecast · seasonal_naive');
  const disclosure = screen.getByText('Altri risultati del grafo').closest('details')!;
  expect(disclosure).not.toHaveAttribute('open');
  expect(disclosure).toHaveTextContent('reference_model');
  expect(disclosure).toHaveTextContent('98');
  expect(disclosure).toHaveTextContent('99');
});

it('renders recorded nested metrics with their node and preserves count/status', () => {
  render(<RunDetails run={makeRun()} evaluations={[{ evaluation_id: 'e', run_id: 'run-1', actuals_snapshot_id: 'a', status: 'evaluated', metrics: { forecast: { mae: 0.5, count: 1, status: 'evaluated' } }, origin_count: 1, assumptions: [] }]} />);
  expect(screen.getByText('forecast · MAE')).toBeVisible();
  expect(screen.getByText('forecast · count')).toBeVisible();
  expect(screen.getByText('forecast · status')).toBeVisible();
  expect(screen.queryByText('[object Object]')).not.toBeInTheDocument();
});
it('distinguishes failed evaluation reads from an unevaluated forecast', () => {
  render(<RunDetails run={makeRun()} evaluations={[]} evaluationsUnavailable />);
  expect(screen.getByText('Valutazioni non disponibili')).toBeVisible();
  expect(screen.queryByText('Non ancora valutata')).not.toBeInTheDocument();
});

const historyGraph: GraphSpec = { graph_id: "graph-1", version: 1, nodes: [
  { node_id: "source-a", kind: "source", inputs: [], config: { source_id: "a" } },
  { node_id: "source-b", kind: "source", inputs: [], config: { source_id: "b" } },
  { node_id: "forecast", kind: "forecast", inputs: ["source-a"], config: { history: "source-a" } },
] };
const historySnapshot = (id: string, value: number): Snapshot => ({ snapshot_id: id, as_of: "2026-10-24T00:00:00Z", assumptions: [], observations: [
  { series_id: "sales", unit: "count", value, event_time: "2026-10-23T00:00:00Z", available_at: "2026-10-23T00:00:00Z", revision: "1" },
] });
it("charts only the snapshot bound to the forecast history source", () => {
  const { container } = render(<RunDetails run={makeRun({ snapshot_ids: ["input-a", "input-b"] })} evaluations={[]}
    graph={historyGraph} sourceBindings={{ a: "input-a", b: "input-b" }} snapshots={[historySnapshot("input-a", 3), historySnapshot("input-b", 300)]} />);
  const path = container.querySelector("[data-observed-path]")!.getAttribute("d")!;
  expect(path.match(/M/g)).toHaveLength(1);
  expect(path).not.toContain("L");
  expect([...container.querySelectorAll("[data-y-tick]")].map(node => node.textContent)).toEqual(["0", "2", "4"]);
});
it.each(["missing graph", "missing binding", "outside run", "composite", "wrong graph"])("omits unproven source history: %s", (reason) => {
  const graph = structuredClone(historyGraph);
  if (reason === "composite") graph.nodes[0].kind = "transform";
  if (reason === "wrong graph") graph.version = 2;
  const { container } = render(<RunDetails run={makeRun({ snapshot_ids: ["input-a"] })} evaluations={[]}
    graph={reason === "missing graph" ? undefined : graph} sourceBindings={reason === "missing binding" ? {} : { a: reason === "outside run" ? "input-b" : "input-a" }} snapshots={[historySnapshot("input-a", 3), historySnapshot("input-b", 300)]} />);
  expect(container.querySelector("[data-observed-path]")).toHaveAttribute("d", "");
  expect(screen.getByText(/Storico osservato non disponibile/)).toBeVisible();
});

it("preserves nested interval and pinball metric leaves in a collapsed disclosure", () => {
  const { container } = render(<RunDetails run={makeRun()} evaluations={[{
    evaluation_id: "nested", run_id: "run-1", actuals_snapshot_id: "actuals", status: "evaluated", origin_count: 1, assumptions: [],
    metrics: { forecast: { mae: 0.5, count: 1, status: "evaluated", pinball: { "0.1": 0.1, "0.5": 0 }, intervals: { "0.1:0.9": { coverage: 1, width: 2, level: 0.8 }, unavailable: null } } },
  }]} />);
  expect(container).not.toHaveTextContent("[object Object]");
  const disclosure = screen.getByText("Altre metriche registrate").closest("details")!;
  expect(disclosure).not.toHaveAttribute("open");
  expect(disclosure).not.toContainElement(screen.getByText("forecast · MAE"));
  fireEvent.click(screen.getByText("Altre metriche registrate"));
  for (const [label, value] of [["forecast · pinball · 0.1", "0.1"], ["forecast · pinball · 0.5", "0"], ["forecast · intervals · 0.1:0.9 · COVERAGE", "1"], ["forecast · intervals · 0.1:0.9 · WIDTH", "2"], ["forecast · intervals · 0.1:0.9 · LEVEL", "0.8"], ["forecast · intervals · UNAVAILABLE", "—"]]) {
    expect(within(disclosure).getByText(label).nextElementSibling).toHaveTextContent(value);
  }
});
it("collapses raw result and snapshot data while retaining visible evidence targets", () => {
  const run = makeRun();
  run.results.forecast.assumptions = ["Recorded model assumption"];
  render(<RunDetails run={run} evaluations={[]} snapshots={[{ ...historySnapshot("snapshot-1", 3), assumptions: ["Recorded snapshot assumption"] }]} />);
  const result = screen.getByText("Dati e assunzioni del risultato").closest("details")!;
  expect(result).not.toHaveAttribute("open");
  expect(result).toHaveTextContent("Recorded model assumption");
  const heading = screen.getByRole("heading", { name: "Snapshot snapshot-1" });
  expect(heading).toBeVisible();
  expect(heading.closest("article")).toHaveAttribute("id", "snapshot-snapshot-1");
  const snapshotDetails = within(heading.closest("article")!).getByText("Osservazioni e assunzioni dello snapshot").closest("details")!;
  expect(snapshotDetails).not.toHaveAttribute("open");
  expect(snapshotDetails).toHaveTextContent("Recorded snapshot assumption");
});
