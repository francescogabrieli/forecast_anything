import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SourceSpec } from "../../api/schema.generated";
import { SourceMappingForm } from "./SourceMappingForm";

function Editor({ initial = {} }: { initial?: NonNullable<SourceSpec["mapping"]> }) {
  const [mapping, setMapping] = useState(initial);
  return <><SourceMappingForm kind="http_json" mapping={mapping} onChange={setMapping} /><output aria-label="Mapping prodotto">{JSON.stringify(mapping)}</output></>;
}
function emitted() { return JSON.parse(screen.getByLabelText("Mapping prodotto").textContent ?? "{}"); }

describe("SourceMappingForm", () => {
  it("keeps an explicitly selected availability column independent of observation time", () => {
    render(<Editor />);
    fireEvent.change(screen.getByLabelText("Data osservazione — campo"), { target: { value: "date" } });
    expect(emitted()).toEqual({ event_time: "date" });
    fireEvent.change(screen.getByLabelText("Disponibile dal — campo"), { target: { value: "date" } });
    fireEvent.change(screen.getByLabelText("Data osservazione — campo"), { target: { value: "event_date" } });
    expect(emitted()).toEqual({ event_time: "event_date", available_at: "date" });
  });

  it("edits textual missing markers without losing numeric, boolean or null sentinels", () => {
    render(<Editor initial={{ missing_values: { constant: ["", -999, false, null, "NA"] }, custom: { retained: true } }} />);
    fireEvent.change(screen.getByLabelText("Altri marcatori testuali mancanti (uno per riga)"), { target: { value: "N/A\nmissing" } });
    expect(emitted()).toEqual({ missing_values: { constant: ["", -999, false, null, "N/A", "missing"] }, custom: { retained: true } });
    fireEvent.click(screen.getByLabelText("Null JSON come valore mancante"));
    expect(emitted().missing_values.constant).toEqual(["", -999, false, "N/A", "missing"]);
    fireEvent.click(screen.getByLabelText("Cella vuota come valore mancante"));
    expect(emitted().missing_values.constant).toEqual([-999, false, "N/A", "missing"]);
  });

  it("emits HTTP records path and declared cadence semantics while preserving explicit constants", () => {
    render(<Editor initial={{ revision: { constant: 0 }, value: { constant: null } }} />);
    fireEvent.change(screen.getByLabelText("Percorso dei record JSON"), { target: { value: "data.rows" } });
    fireEvent.change(screen.getByLabelText("Frequenza"), { target: { value: "2h" } });
    fireEvent.change(screen.getByLabelText("Fuso orario"), { target: { value: "Europe/Rome" } });
    fireEvent.change(screen.getByLabelText("Calendario"), { target: { value: "gregorian" } });
    expect(emitted()).toEqual({ revision: { constant: 0 }, value: { constant: null }, records_path: "data.rows", frequency: { constant: "2h" }, timezone: { constant: "Europe/Rome" }, calendar: { constant: "gregorian" } });
  });
});
