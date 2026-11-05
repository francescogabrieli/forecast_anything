import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { GraphSpec } from "../../api/schema.generated";
import { FutureGraph } from "./FutureGraph";

const graph: GraphSpec = {
  graph_id: "graph-1",
  version: 1,
  nodes: [
    { node_id: "question", kind: "event", inputs: ["forecast"], config: {} },
    { node_id: "forecast", kind: "forecast", inputs: ["sales"], config: {} },
    { node_id: "sales", kind: "source", inputs: [], config: {} },
  ],
};

describe("FutureGraph", () => {
  it("renders nodes in dependency order and supports keyboard selection", () => {
    const onSelectNode = vi.fn();
    render(<FutureGraph graph={graph} modifiedNodeIds={new Set(["forecast"])} onSelectNode={onSelectNode} />);
    const node = screen.getByRole("button", { name: /forecast, previsione, modificato/i });

    expect(screen.getAllByRole("button").map((item) => item.getAttribute("data-node-id"))).toEqual(["sales", "forecast", "question"]);
    expect(node).toHaveAttribute("data-modified", "true");
    node.focus();
    fireEvent.keyDown(node, { key: "Enter" });

    expect(onSelectNode).toHaveBeenCalledWith("forecast");
    expect(screen.getByRole("button", { name: "sales, fonte" })).toBeVisible();
    expect(screen.getByRole("button", { name: "question, evento" })).toBeVisible();
    expect(screen.getByText(/le righe mostrano i livelli/i)).toBeVisible();
  });
});
