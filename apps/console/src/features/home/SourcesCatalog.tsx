import { useEffect, useState } from "react";
import type { ApiClient } from "../../api/client";
import type { SourceView } from "../../api/schema.generated";
export function SourcesCatalog({ client, reloadKey, onSelect }: { client: ApiClient; reloadKey: number; onSelect: (id: string) => void }) {
  const [sources, setSources] = useState<SourceView[]>();
  const [error, setError] = useState<string>();
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setSources(undefined); setError(undefined);
    void client.getSources().then((values) => { if (active) setSources(values); }, (reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Riprova più tardi."); });
    return () => { active = false; };
  }, [client, reloadKey, retry]);
  return <section className="source-catalog" aria-labelledby="source-catalog-title"><h2 id="source-catalog-title">Fonti registrate</h2>
    {error ? <div><p role="alert">Fonti non disponibili: {error}</p><button className="text-button" onClick={() => setRetry((value) => value + 1)}>Riprova elenco fonti</button></div> : sources === undefined ? <p role="status">Caricamento delle fonti…</p> : sources.length === 0 ? <p className="muted">Nessuna fonte collegata. Inizia dal modulo qui sotto.</p> : <ul>{sources.map((source) => <li key={source.source_id}><div><strong>{source.source_id}</strong><span>{source.kind === "http_json" ? "HTTP JSON" : "CSV"} · ogni {source.refresh_seconds} s</span></div><button className="text-button" aria-label={`Apri ${source.source_id}`} onClick={() => onSelect(source.source_id)}>Apri <span aria-hidden="true">↗</span></button></li>)}</ul>}
  </section>;
}
