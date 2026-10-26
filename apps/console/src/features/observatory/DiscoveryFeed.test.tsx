import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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

    expect(screen.getAllByRole("button", { name: /run-1/i })).toHaveLength(1);
    expect(screen.getByText(/1 eventi unici/i)).toBeVisible();
  });
});
