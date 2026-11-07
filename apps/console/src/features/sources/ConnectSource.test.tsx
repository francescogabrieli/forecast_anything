import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client";
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
  it("previews and activates using explicit guided roles without JSON editing", async () => {
    const user = userEvent.setup();
    const client = {
      inspectSource: vi.fn().mockRejectedValueOnce(new Error("source_not_found")).mockResolvedValue(profile()),
      previewSource: vi.fn().mockResolvedValue(profile()),
      saveSource: vi.fn().mockResolvedValue({ source_id: "sales", profile: profile() }),
    };
    const activated = vi.fn();
    render(<ConnectSource client={client} sourceId="sales" onActivated={activated} />);
    await user.type(screen.getByLabelText("Percorso o URL"), "/data/sales.csv");
    fireEvent.change(screen.getByLabelText("Data osservazione — campo"), { target: { value: "time" } });
    fireEvent.change(screen.getByLabelText("Valore — campo"), { target: { value: "value" } });
    fireEvent.change(screen.getByLabelText("Revisione — campo"), { target: { value: "1" } });
    expect(screen.getByLabelText("Disponibile dal — campo")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("Disponibile dal — origine"), { target: { value: "constant" } });
    fireEvent.change(screen.getByLabelText("Disponibile dal — campo"), { target: { value: "2026-10-23" } });
    fireEvent.change(screen.getByLabelText("Serie — campo"), { target: { value: "sales" } });
    fireEvent.change(screen.getByLabelText("Unità — campo"), { target: { value: "count" } });
    fireEvent.change(screen.getByLabelText("Frequenza"), { target: { value: "1d" } });
    fireEvent.change(screen.getByLabelText("Fuso orario"), { target: { value: "UTC" } });
    await user.click(screen.getByRole("button", { name: "Analizza fonte" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/profilo pronto/i);
    expect(client.previewSource).toHaveBeenCalledWith(expect.objectContaining({ mapping: completeMapping }));
    await user.click(screen.getByRole("button", { name: "Attiva fonte" }));
    await waitFor(() => expect(activated).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("Unità — campo"), { target: { value: "EUR" } });
    expect(screen.getByRole("button", { name: "Attiva fonte" })).toBeDisabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("preserves advanced scalar constants and unknown keys through guided edits", async () => {
    const user = userEvent.setup();
    const client = { inspectSource: vi.fn().mockResolvedValue(profile()), previewSource: vi.fn().mockResolvedValue(profile()), saveSource: vi.fn() };
    render(<ConnectSource client={client} sourceId="sales" />);
    await screen.findByText("Profilo pronto.");
    fireEvent.change(screen.getByLabelText("Mappatura JSON"), { target: { value: JSON.stringify({ ...completeMapping, revision: { constant: 7 }, extension: { custom: true } }) } });
    fireEvent.change(screen.getByLabelText("Unità — campo"), { target: { value: "EUR" } });
    await user.type(screen.getByLabelText("Percorso o URL"), "/data/sales.csv");
    await user.click(screen.getByRole("button", { name: "Analizza fonte" }));
    await screen.findByRole("status");
    expect(client.previewSource).toHaveBeenCalledWith(expect.objectContaining({ mapping: expect.objectContaining({ revision: { constant: 7 }, extension: { custom: true }, unit: { constant: "EUR" } }) }));
  });

  it("keeps malformed advanced JSON editable and blocks preview and activation", async () => {
    const user = userEvent.setup();
    const client = { inspectSource: vi.fn().mockResolvedValue(profile()), previewSource: vi.fn(), saveSource: vi.fn() };
    render(<ConnectSource client={client} sourceId="sales" />);
    await screen.findByText("Profilo pronto.");
    await user.type(screen.getByLabelText("Percorso o URL"), "/data/sales.csv");
    fireEvent.change(screen.getByLabelText("Mappatura JSON"), { target: { value: "{broken" } });
    expect(screen.getByLabelText("Mappatura JSON")).toHaveValue("{broken");
    expect(screen.getByRole("button", { name: "Analizza fonte" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Attiva fonte" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(/JSON valida/);
  });

  it("clears the previous profile when switching source while the replacement is loading", async () => {
    const first = { inspectSource: vi.fn().mockResolvedValue(profile()), previewSource: vi.fn(), saveSource: vi.fn() };
    const second = { inspectSource: vi.fn().mockImplementation(() => new Promise(() => {})), previewSource: vi.fn(), saveSource: vi.fn() };
    const { rerender } = render(<ConnectSource client={first} sourceId="sales" />);
    await screen.findByText("Profilo pronto.");
    fireEvent.change(screen.getByLabelText("Percorso o URL"), { target: { value: "/data/sales.csv" } });
    // Reload a resolved profile for this draft before switching the workspace.
    first.previewSource.mockResolvedValue(profile());
    fireEvent.click(screen.getByRole("button", { name: "Analizza fonte" }));
    await screen.findByText("Profilo pronto.");
    rerender(<ConnectSource client={second} sourceId="other" />);
    expect(screen.queryByText("Anteprima: sales")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Attiva fonte" })).toBeDisabled();
  });

  it("ignores an old workspace unauthorized response while the current preview remains busy", async () => {
    let rejectOld: (reason: unknown) => void = () => {};
    let finishCurrent: (result: ReturnType<typeof profile>) => void = () => {};
    const oldClient = { inspectSource: vi.fn().mockRejectedValue(new Error("source_not_found")), previewSource: vi.fn().mockImplementation(() => new Promise((_, reject) => { rejectOld = reject; })), saveSource: vi.fn() };
    const currentClient = { inspectSource: vi.fn().mockRejectedValue(new Error("source_not_found")), previewSource: vi.fn().mockImplementation(() => new Promise((resolve) => { finishCurrent = resolve; })), saveSource: vi.fn() };
    const { rerender } = render(<ConnectSource client={oldClient} sourceId="sales" />);
    fireEvent.change(screen.getByLabelText("Percorso o URL"), { target: { value: "/data/sales.csv" } });
    fireEvent.click(screen.getByRole("button", { name: "Analizza fonte" }));
    rerender(<ConnectSource client={currentClient} sourceId="current" />);
    fireEvent.click(screen.getByRole("button", { name: "Analizza fonte" }));
    await act(async () => rejectOld(new ApiError(401, "unauthorized", {})));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Elaborazione…" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Elaborazione…" })[0]).toBeDisabled();
    await act(async () => finishCurrent(profile({ source_id: "current" })));
    expect(screen.getByText("Anteprima: current")).toBeVisible();
    expect(screen.getByRole("button", { name: "Analizza fonte" })).toBeEnabled();
  });

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

  it("does not activate an older source draft after the user edits it", async () => {
    const user = userEvent.setup();
    let finishSave: (value: unknown) => void = () => {};
    const api = {
      inspectSource: vi.fn().mockRejectedValueOnce(new Error("source_not_found")).mockResolvedValue(profile()),
      previewSource: vi.fn().mockResolvedValue(profile()),
      saveSource: vi.fn().mockImplementation(() => new Promise((resolve) => { finishSave = resolve; })),
    };
    const activated = vi.fn();
    const changed = vi.fn();
    render(<ConnectSource client={api} sourceId="sales" onActivated={activated} onDraftChange={changed} />);
    await user.type(screen.getByLabelText("Percorso o URL"), "/data/sales.csv");
    fireEvent.change(screen.getByLabelText("Mappatura JSON"), { target: { value: JSON.stringify(completeMapping) } });
    await user.click(screen.getByRole("button", { name: "Analizza fonte" }));
    await user.click(screen.getByRole("button", { name: "Attiva fonte" }));
    fireEvent.change(screen.getByLabelText("Percorso o URL"), { target: { value: "/data/other.csv" } });
    await act(async () => finishSave({ source_id: "sales", profile: profile(), job_id: "old-job" }));
    expect(changed).toHaveBeenCalled();
    expect(activated).not.toHaveBeenCalled();
    expect(screen.queryByText(/fonte attiva/i)).not.toBeInTheDocument();
  });
});
