import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeRun } from "../../test/fixtures";
import { ScenarioCompare } from "./ScenarioCompare";

const graph = {
  graph_id: "graph-1",
  version: 1,
  nodes: [{ node_id: "forecast", kind: "forecast" as const, inputs: ["sales"], config: {} }],
};

describe("ScenarioCompare", () => {
  it("keeps the assumptions attached to each compared forecast", () => {
    const baseRun = makeRun({ results: { forecast: { ...makeRun().results.forecast, assumptions: ["Base uses observed sales."] } } });
    const scenarioRun = makeRun({
      run_id: "run-scenario",
      scenario_id: "scenario-1",
      results: { forecast: { ...makeRun().results.forecast, point: [[2, 3]], assumptions: ["Scenario assumes a 10% demand increase."] } },
    });

    render(<ScenarioCompare baseRun={baseRun} scenarioRun={scenarioRun} baseGraph={graph} scenarioGraph={graph} />);

    expect(screen.getByText("Base uses observed sales.")).toBeVisible();
    expect(screen.getByText("Scenario assumes a 10% demand increase.")).toBeVisible();
    expect(screen.getByText(/timestamp comuni/i)).toBeVisible();
  });
});
