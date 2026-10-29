import { useId } from "react";
import type { SourceSpec } from "../../api/schema.generated";

type Mapping = NonNullable<SourceSpec["mapping"]>;
type Props = { mapping: Mapping; kind: SourceSpec["kind"]; columns?: string[]; onChange: (mapping: Mapping) => void };
const roles = [
  ["event_time", "Data osservazione"], ["value", "Valore"], ["available_at", "Disponibile dal"],
  ["series_id", "Serie"], ["unit", "Unità"], ["revision", "Revisione"],
] as const;
function constant(value: unknown): unknown {
  return value && typeof value === "object" && "constant" in value ? value.constant : undefined;
}
function text(value: unknown): string {
  return value === undefined || value === null ? "" : String(value);
}

export function SourceMappingForm({ mapping, kind, columns = [], onChange }: Props) {
  const id = useId();
  function update(key: string, value: unknown) { onChange({ ...mapping, [key]: value }); }
  const missing = constant(mapping.missing_values);
  const markers = Array.isArray(missing) ? missing : [];
  return <div className="source-mapping">
    <fieldset>
      <legend>Interpreta le colonne</legend>
      <p>Indica una colonna oppure un valore costante per ogni ruolo. La disponibilità è il momento in cui il dato era conoscibile: scegli esplicitamente la colonna, anche quando coincide con la data osservata.</p>
      <datalist id={`${id}-columns`}>{columns.map((column) => <option key={column} value={column} />)}</datalist>
      <div className="mapping-grid">
        {roles.map(([key, label]) => {
          const mode = typeof mapping[key] === "string" || mapping[key] === undefined ? "column" : "constant";
          const value = mode === "column" ? mapping[key] : constant(mapping[key]);
          return <fieldset className="mapping-role" key={key}>
            <legend>{label}</legend>
            <label>{label} — origine
              <select value={mode} onChange={(event) => update(key, event.target.value === "column" ? "" : { constant: "" })}>
                <option value="column">Colonna</option><option value="constant">Costante</option>
              </select>
            </label>
            <label>{label} — campo
              <input autoComplete="off" list={mode === "column" ? `${id}-columns` : undefined} value={text(value)} placeholder={mode === "column" ? "Nome della colonna" : "Valore costante"} onChange={(event) => update(key, mode === "column" ? event.target.value : { constant: event.target.value })} />
            </label>
          </fieldset>;
        })}
      </div>
    </fieldset>
    <fieldset>
      <legend>Frequenza e significato dei dati</legend>
      <div className="mapping-grid">
        {([["frequency", "Frequenza", "1d"], ["timezone", "Fuso orario", "Europe/Rome"], ["calendar", "Calendario", "gregorian"]] as const).map(([key, label, placeholder]) => <label key={key}>{label}
          <input value={text(constant(mapping[key]))} placeholder={placeholder} onChange={(event) => update(key, { constant: event.target.value })} />
        </label>)}
      </div>
      <p>Frequenze supportate: D, H oppure intervalli come 1d o 2h. Usa un fuso IANA e il calendario gregorian.</p>
      <label className="mapping-checkbox"><input type="checkbox" checked={markers.includes("")} onChange={(event) => update("missing_values", { constant: event.target.checked ? [...markers.filter((marker) => marker !== ""), ""] : markers.filter((marker) => marker !== "") })} />Cella vuota come valore mancante</label>
      <label className="mapping-checkbox"><input type="checkbox" checked={markers.includes(null)} onChange={(event) => update("missing_values", { constant: event.target.checked ? [...markers.filter((marker) => marker !== null), null] : markers.filter((marker) => marker !== null) })} />Null JSON come valore mancante</label>
      <label>Altri marcatori testuali mancanti (uno per riga)
        <textarea rows={2} value={markers.filter((marker) => typeof marker === "string" && marker !== "").join("\n")} onChange={(event) => update("missing_values", { constant: [...markers.filter((marker) => typeof marker !== "string" || marker === ""), ...event.target.value.split("\n").filter((marker) => marker !== "")] })} />
      </label>
      <p>I marcatori si applicano solo al valore. I marcatori numerici o booleani restano disponibili nella mappatura avanzata.</p>
    </fieldset>
    {kind === "http_json" && <label>Percorso dei record JSON
      <input autoComplete="off" value={text(mapping.records_path)} placeholder="data.records (vuoto per un array alla radice)" onChange={(event) => update("records_path", event.target.value)} />
    </label>}
  </div>;
}
