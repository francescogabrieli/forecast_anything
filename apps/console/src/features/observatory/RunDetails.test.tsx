import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeRun, makeWatch } from "../../test/fixtures";
import { RunDetails } from "./RunDetails";

describe("RunDetails", () => {
  it("does not draw uncertainty for a point-only forecast", () => {
    render(<RunDetails run={makeRun()} evaluations={[]} watch={makeWatch({ quality: "stale" })} />);
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
});
