import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ApiClient } from "../../api/client";
import type { EventRecord } from "../../api/schema.generated";
import { makeRun } from "../../test/fixtures";
import { ObservatoryBoard } from "./ObservatoryBoard";

it("opens the completed run and surfaces a failed watch refresh", async () => {
  const client = new ApiClient("http://localhost:8000", "test-token");
  let deliverEvent: ((event: EventRecord) => void) | undefined;
  vi.spyOn(client, "getWatches")
    .mockResolvedValueOnce([])
    .mockRejectedValueOnce(new Error("Watch refresh unavailable"));
  vi.spyOn(client, "getEvents").mockResolvedValue([
    { cursor: 1, event_id: "event-1", kind: "run_completed", run_id: "run-1", payload: { node_ids: ["forecast"] } },
  ]);
  vi.spyOn(client, "streamEvents").mockImplementation(async (_cursor, onEvent) => {
    deliverEvent = onEvent;
  });
  vi.spyOn(client, "getRun").mockImplementation(async (runId) => makeRun({ run_id: runId }));
  vi.spyOn(client, "getGraph").mockResolvedValue({ graph_id: "graph-1", version: 1, nodes: [] });
  vi.spyOn(client, "getRunEvaluations").mockResolvedValue([]);
  vi.spyOn(client, "getSnapshot").mockResolvedValue({
    snapshot_id: "snapshot-1", as_of: "2026-10-24T00:00:00Z", observations: [], assumptions: [],
  });
  const user = userEvent.setup();
  render(<ObservatoryBoard client={client} />);
  await waitFor(() => expect(deliverEvent).toBeTypeOf("function"));
  await user.click(await screen.findByRole("button", { name: "Apri run run-1" }));
  expect(await screen.findByRole("heading", { name: "run-1" })).toBeVisible();

  await act(async () => {
    deliverEvent!({ cursor: 2, event_id: "event-2", kind: "run_completed", run_id: "run-2", payload: { node_ids: ["forecast"] } });
  });

  expect(await screen.findByRole("heading", { name: "run-2" })).toBeVisible();
  expect(screen.queryByRole("heading", { name: "run-1" })).not.toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent("Watch refresh unavailable");
});
