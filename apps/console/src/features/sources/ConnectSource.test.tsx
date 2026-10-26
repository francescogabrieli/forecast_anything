import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConnectSource } from "./ConnectSource";

const profile = (overrides: Record<string, unknown> = {}) => ({
  source_id: "sales",
  source_revision: "rev-1",
  fields: { time: { data_type: "datetime", nullable: false }, value: { data_type: "number", nullable: false } },
  proposed_mapping: {
    event_time: "time",
    value: "value",
    available_at: { constant: "2026-10-23" },
    revision: { constant: "1" },
    series_id: { constant: "sales" },
    frequency: { constant: "1d" },
    timezone: { constant: "UTC" },
    calendar: { constant: "gregorian" },
    missing_values: { constant: [""] },
  },
  unresolved: [],
  assumptions: ["Field types describe a sample of at most 100 rows."],
  sample_rows: [{ time: "2026-10-23", value: 3 }],
  ...overrides,
});

const completeMapping = {
  event_time: "time",
  value: "value",
  available_at: { constant: "2026-10-23" },
  revision: { constant: "1" },
  series_id: { constant: "sales" },
  unit: { constant: "count" },
  frequency: { constant: "1d" },
  timezone: { constant: "UTC" },
  calendar: { constant: "gregorian" },
  missing_values: { constant: [""] },
};

describe("ConnectSource", () => {
  it("asks for a unit clarification and prevents activation while unresolved", async () => {
    const client = {
      inspectSource: vi.fn().mockResolvedValue(profile({ unresolved: ["unit"] })),
      previewSource: vi.fn(),
      saveSource: vi.fn(),
    };

    render(<ConnectSource client={client} sourceId="sales" />);

    expect(await screen.findByText("Unità da chiarire")).toBeVisible();
    expect(screen.getByRole("button", { name: "Attiva fonte" })).toBeDisabled();
    expect(client.saveSource).not.toHaveBeenCalled();
  });

  it("shows authentication errors without clearing entered source details", async () => {
    const client = {
      inspectSource: vi.fn().mockRejectedValue(new Error("unauthorized")),
      previewSource: vi.fn(),
      saveSource: vi.fn(),
    };

    render(<ConnectSource client={client} sourceId="sales" />);
    fireEvent.change(screen.getByLabelText("Percorso o URL"), { target: { value: "/data/sales.csv" } });

    expect(await screen.findByRole("alert")).toHaveTextContent(/sessione|token/i);
    expect(screen.getByLabelText("Percorso o URL")).toHaveValue("/data/sales.csv");
  });

  it("previews a corrected mapping, saves it, then reloads the persisted profile", async () => {
    const user = userEvent.setup();
    const savedProfile = profile();
    const client = {
      inspectSource: vi.fn().mockRejectedValueOnce(new Error("source_not_found")).mockResolvedValueOnce(savedProfile),
      previewSource: vi.fn().mockResolvedValue(savedProfile),
      saveSource: vi.fn().mockResolvedValue({ source_id: "sales", profile: savedProfile }),
    };

    render(<ConnectSource client={client} sourceId="sales" />);
    await user.type(screen.getByLabelText("Percorso o URL"), "/data/sales.csv");
    fireEvent.change(screen.getByLabelText("Mappatura JSON"), { target: { value: JSON.stringify(completeMapping) } });
    await user.click(screen.getByRole("button", { name: "Analizza fonte" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/profilo pronto/i);
    await user.click(screen.getByRole("button", { name: "Attiva fonte" }));

    await waitFor(() => expect(client.inspectSource).toHaveBeenCalledTimes(2));
    expect(client.previewSource).toHaveBeenCalledWith(expect.objectContaining({ source_id: "sales", mapping: completeMapping }));
    expect(client.saveSource).toHaveBeenCalledWith(expect.objectContaining({ source_id: "sales", mapping: completeMapping }));
    expect(await screen.findByText(/fonte attiva/i)).toBeVisible();
  });
});
