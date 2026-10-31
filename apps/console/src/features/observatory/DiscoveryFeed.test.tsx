import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Candidate } from "../../api/schema.generated";
import { makeWatch } from "../../test/fixtures";
import { DiscoveryFeed } from "./DiscoveryFeed";

const event = (cursor: number, eventId: string) => ({
  cursor,
  event_id: eventId,
  kind: "run_completed",
  run_id: "run-1",
  payload: {},
});

describe("DiscoveryFeed", () => {
  it("deduplicates events replayed at the same cursor", () => {
    render(<DiscoveryFeed watches={[]} events={[event(2, "event-2"), event(2, "event-2-replay")]} onSelectRun={vi.fn()} />);

    fireEvent.click(screen.getByText("Cronologia", { exact: true }));
    expect(screen.getAllByRole("button", { name: /run-1/i })).toHaveLength(1);
    expect(screen.getByText(/1 eventi unici/i)).toBeVisible();
  });

  it("shows an Italian question title and preserves the original reason", () => {
    const watch = makeWatch({
      candidate: {
        candidate_id: "candidate-1",
        epoch_id: "epoch-1",
        graph: { graph_id: "graph-1", nodes: [], version: 1 },
        protocol_id: "protocol-1",
        reason: "Registered expected_deviation question for study-sales.",
        source_ids: ["study-sales"],
        template_id: "expected_deviation",
      } as Candidate,
    });

    render(<DiscoveryFeed watches={[watch]} events={[]} />);

    expect(screen.getByText("Scostamento dal comportamento atteso")).toBeVisible();
    expect(screen.getByText("Motivo: Registered expected_deviation question for study-sales.")).toBeVisible();
  });
});
