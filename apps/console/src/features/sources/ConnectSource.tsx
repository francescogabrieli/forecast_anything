import { useEffect, useMemo, useState } from "react";
import type { ApiClient } from "../../api/client";
import { ApiError } from "../../api/client";
import type { SourceProfile, SourceSpec } from "../../api/schema.generated";

type SourceClient = Pick<ApiClient, "inspectSource" | "previewSource" | "saveSource">;
type Props = { client: SourceClient; sourceId: string; onActivated?: () => void };

const clarificationLabels: Record<string, string> = {
  event_time: "Data dell’osservazione da chiarire",
  value: "Valore da chiarire",
  available_at: "Disponibilità del dato da chiarire",
  revision: "Revisione del dato da chiarire",
  series_id: "Identità della serie da chiarire",
  unit: "Unità da chiarire",
  frequency: "Frequenza da chiarire",
  timezone: "Fuso orario da chiarire",
  calendar: "Calendario da chiarire",
  missing_values: "Valori mancanti da chiarire",
  operational_limit: "Limite operativo da chiarire",
};

const initialMapping = {
  event_time: "",
  value: "",
  available_at: { constant: "" },
  revision: { constant: "1" },
  series_id: { constant: "" },
  unit: { constant: "" },
  frequency: { constant: "1d" },
  timezone: { constant: "UTC" },
  calendar: { constant: "gregorian" },
  missing_values: { constant: [""] },
};

function errorCode(error: unknown): string {
  if (error instanceof ApiError) return error.code;
  if (error instanceof Error) return error.message;
  return "request_failed";
}

function errorMessage(error: unknown): string {
  const code = errorCode(error);
  if (code === "unauthorized") return "Sessione non valida: verifica il token del workspace.";
  if (code === "source_not_found" || code === "not_found") return "Fonte non ancora registrata.";
  if (code === "unresolved_source_mapping") return "Risolvi i campi indicati prima di attivare la fonte.";
  return "Non è stato possibile completare la richiesta. I dati inseriti sono ancora disponibili.";
}

export function ConnectSource({ client, sourceId, onActivated }: Props) {
  const [kind, setKind] = useState<SourceSpec["kind"]>("csv");
  const [location, setLocation] = useState("");
  const [refreshSeconds, setRefreshSeconds] = useState("3600");
  const [mappingText, setMappingText] = useState(JSON.stringify(initialMapping, null, 2));
  const [profile, setProfile] = useState<SourceProfile>();
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    client.inspectSource(sourceId).then((loaded) => {
      if (!active) return;
      setProfile(loaded);
      setMappingText(JSON.stringify(loaded.proposed_mapping, null, 2));
    }).catch((reason: unknown) => {
      if (!active || ["source_not_found", "not_found"].includes(errorCode(reason))) return;
      setError(errorMessage(reason));
    });
    return () => { active = false; };
  }, [client, sourceId]);

  const unresolved = profile?.unresolved ?? [];
  const parsedMapping = useMemo(() => {
    try {
      const value: unknown = JSON.parse(mappingText);
      if (!value || Array.isArray(value) || typeof value !== "object") throw new Error();
      return value as SourceSpec["mapping"];
    } catch {
      return undefined;
    }
  }, [mappingText]);
  const mappingError = parsedMapping ? undefined : "Inserisci una mappatura JSON valida.";

  function changeMapping(value: string) {
    setMappingText(value);
    setProfile(undefined);
    setMessage(undefined);
    setError(undefined);
  }

  function sourceSpec(): SourceSpec | undefined {
    const refresh = Number(refreshSeconds);
    if (!location.trim() || !Number.isInteger(refresh) || refresh <= 0 || !parsedMapping) return undefined;
    return {
      source_id: sourceId,
      kind,
      location: location.trim(),
      refresh_seconds: refresh,
      mapping: parsedMapping,
    };
  }

  async function preview() {
    const spec = sourceSpec();
    if (!spec) return;
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      setProfile(await client.previewSource(spec));
      setMessage("Profilo pronto per la revisione.");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function activate() {
    const spec = sourceSpec();
    if (!spec || !profile || profile.unresolved.length > 0) return;
    setBusy(true);
    setError(undefined);
    setMessage(undefined);
    try {
      await client.saveSource(spec);
      const persisted = await client.inspectSource(sourceId);
      setProfile(persisted);
      if (persisted.unresolved.length > 0) {
        setError("Il profilo salvato richiede ancora chiarimenti. La fonte non è pronta per l’uso.");
      } else {
        setMessage("Fonte attiva. Profilo riletto dal servizio.");
        onActivated?.();
      }
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="connect-source-title">
      <h2 id="connect-source-title">Collega una fonte</h2>
      <p>Controlla l’interpretazione dei dati prima di attivare gli aggiornamenti.</p>
      <form onSubmit={(event) => { event.preventDefault(); void preview(); }}>
        <label>
          Tipo di fonte
          <select value={kind} onChange={(event) => { setKind(event.target.value as SourceSpec["kind"]); setProfile(undefined); }}>
            <option value="csv">CSV</option>
            <option value="http_json">HTTP JSON</option>
          </select>
        </label>
        <label>
          Percorso o URL
          <input autoComplete="off" value={location} onChange={(event) => setLocation(event.target.value)} />
        </label>
        <label>
          Aggiorna ogni (secondi)
          <input inputMode="numeric" type="number" min="1" value={refreshSeconds} onChange={(event) => setRefreshSeconds(event.target.value)} />
        </label>
        <label>
          Mappatura JSON
          <textarea rows={12} spellCheck={false} value={mappingText} onChange={(event) => changeMapping(event.target.value)} />
        </label>
        {mappingError && <p role="alert">{mappingError}</p>}
        <button type="submit" disabled={busy || !sourceSpec()}>{busy ? "Elaborazione…" : "Analizza fonte"}</button>
      </form>

      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {profile && (
        <div aria-live="polite">
          <h3>Anteprima: {profile.source_id}</h3>
          {unresolved.length > 0 ? (
            <div>
              <h4>Chiarimenti necessari</h4>
              <ul>{unresolved.map((field) => <li key={field}>{clarificationLabels[field] ?? `${field} da chiarire`}</li>)}</ul>
            </div>
          ) : <p>Profilo pronto.</p>}
          <h4>Campi trovati</h4>
          {Object.keys(profile.fields).length === 0 ? <p>Nessun campo rilevato nel campione.</p> : (
            <ul>{Object.entries(profile.fields).map(([name, field]) => <li key={name}>{name} — {field.data_type}{field.nullable ? ", può mancare" : ""}</li>)}</ul>
          )}
          {profile.assumptions.length > 0 && <><h4>Assunzioni e limiti</h4><ul>{profile.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></>}
          {(profile.sample_rows?.length ?? 0) > 0 && <details><summary>Esempio di righe campionate</summary><pre>{JSON.stringify(profile.sample_rows ?? [], null, 2)}</pre></details>}
        </div>
      )}
      <button type="button" onClick={() => void activate()} disabled={busy || !profile || unresolved.length > 0 || !sourceSpec()}>
        {busy ? "Elaborazione…" : "Attiva fonte"}
      </button>
    </section>
  );
}
