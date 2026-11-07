import { useEffect, useRef, useState } from "react";
import type { ApiClient } from "../../api/client";
import type { RunRecord, SourceRegistration, SourceView } from "../../api/schema.generated";
import { FirstForecast } from "../sources/FirstForecast";
import { formatUtc } from "../../format";

type Props = { client?: ApiClient; onRunReady: (id: string) => void; reloadKey?: number; active?: boolean };
const message = (reason: unknown) => reason instanceof Error ? reason.message : "Riprova più tardi.";

export function Home({ client, onRunReady, reloadKey = 0, active = true }: Props) {
  const [sources, setSources] = useState<SourceView[]>();
  const [runs, setRuns] = useState<RunRecord[]>();
  const [sourceError, setSourceError] = useState<string>();
  const [historyError, setHistoryError] = useState<string>();
  const [refreshError, setRefreshError] = useState<string>();
  const [selected, setSelected] = useState("");
  const [registration, setRegistration] = useState<SourceRegistration>();
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const refreshKey = useRef<{ source: string; key: string } | undefined>(undefined);
  useEffect(() => {
    generation.current += 1;
    setSources(undefined); setRuns(undefined); setSourceError(undefined); setHistoryError(undefined);
    setRegistration(undefined); setRefreshError(undefined); setSelected(""); setBusy(false); refreshKey.current = undefined;
    return () => { generation.current += 1; };
  }, [client]);
  useEffect(() => {
    let current = true;
    if (client && active) {
      setSourceError(undefined); setHistoryError(undefined);
      void client.getSources().then((values) => {
        if (current) { setSources(values); setSelected((previous) => values.some((source) => source.source_id === previous) ? previous : values[0]?.source_id ?? ""); }
      }, (reason: unknown) => { if (current) setSourceError(message(reason)); });
      void client.getRecentRuns(4).then((values) => {
        if (current) setRuns(values);
      }, (reason: unknown) => { if (current) setHistoryError(message(reason)); });
    }
    return () => { current = false; };
  }, [client, retry, reloadKey, active]);
  async function prepare() {
    if (!client || !selected || busy) return;
    const version = generation.current;
    const source = selected;
    if (refreshKey.current?.source !== source) refreshKey.current = { source, key: `source-refresh:${globalThis.crypto.randomUUID()}` };
    setBusy(true); setRefreshError(undefined); setRegistration(undefined);
    try {
      const value = await client.refreshSource(source, refreshKey.current.key);
      if (generation.current !== version) return;
      if (value.source_id !== source) throw new Error("La risposta non corrisponde alla fonte selezionata.");
      refreshKey.current = undefined; setRegistration(value);
    } catch (reason) { if (generation.current === version) setRefreshError(message(reason)); }
    finally { if (generation.current === version) setBusy(false); }
  }
  return <div className="home-content">
    <section className="forecast-start" aria-labelledby="start-title">
      <div className="section-heading"><h2 id="start-title">Nuova previsione</h2></div>

      {!client ? <div className="start-empty"><p>Collega il tuo core per iniziare a prevedere con i tuoi dati.</p><a className="button button-dark" href="#workspace">Configura il workspace <span aria-hidden="true">↗</span></a></div> : <>
        {sourceError ? <div><p role="alert">Fonti non disponibili: {sourceError}</p><button className="text-button" onClick={() => setRetry((value) => value + 1)}>Riprova caricamento</button></div> : sources === undefined ? <p role="status">Caricamento delle fonti…</p> : sources.length === 0 ? <div className="start-empty"><p>Nessuna fonte collegata.</p><a className="button button-dark" href="#sources">Collega una fonte <span aria-hidden="true">↗</span></a></div> : <div className="forecast-source-control">
          <label>Fonte registrata<select value={selected} disabled={busy} onChange={(event) => { setSelected(event.target.value); setRegistration(undefined); setRefreshError(undefined); refreshKey.current = undefined; }}>{sources.map((source) => <option key={source.source_id} value={source.source_id}>{source.source_id}</option>)}</select></label>
          <button className="button button-dark" disabled={busy || !selected} onClick={() => void prepare()}>{busy ? "Aggiornamento fonte…" : "Prepara previsione"}</button>
        </div>}
        {refreshError && <p role="alert">{refreshError}</p>}
        {!registration && sources && sources.length > 0 && <p className="muted">Potrai rivedere la proposta prima del calcolo.</p>}
      </>}
    </section>
    {client && registration && <FirstForecast key={registration.job_id} client={client} registration={registration} onRunReady={onRunReady} />}
    <div className="home-secondary">
      <section className="recent-forecasts" aria-labelledby="recent-title"><div className="section-heading"><h2 id="recent-title">Previsioni recenti</h2><a href="#observatory">Osservatorio <span aria-hidden="true">↗</span></a></div>
        {!client ? <p className="empty-copy">Le previsioni registrate nel workspace compariranno qui.</p> : historyError ? <div><p role="alert">Cronologia non disponibile: {historyError}</p><button className="text-button" onClick={() => setRetry((value) => value + 1)}>Riprova cronologia</button></div> : runs === undefined ? <p role="status">Caricamento della cronologia…</p> : runs.length === 0 ? <p className="empty-copy">Nessuna previsione registrata.</p> : <ul className="recent-run-list">{runs.map((run) => {
          const forecast = run.results.forecast ?? run.results.model ?? Object.values(run.results)[0];
          return <li key={run.run_id}><button className="run-row" data-run-id={run.run_id} onClick={() => onRunReady(run.run_id)}><span><strong>{forecast?.series_ids.join(", ") || run.run_id}</strong><span className="muted">{formatUtc(run.as_of)} · {run.scenario_id ? "Scenario" : "Valutazioni nel dettaglio"}</span></span><span className="run-row-value">{forecast?.point?.[0]?.[0] ?? "—"} <small>{forecast?.units[0]}</small><span aria-hidden="true"> ↗</span></span></button></li>;
        })}</ul>}
      </section>
      <aside className="method-note"><h2>Dal dato alla verifica</h2><ol><li><strong>Collega</strong><span>CSV accessibile al server o HTTP JSON.</span></li><li><strong>Prevedi</strong><span>Una prima stima stagionale, ancora provvisoria.</span></li><li><strong>Verifica</strong><span>Risultati, dati originali e Future Graph.</span></li></ol><a href="#sources">Gestisci le fonti <span aria-hidden="true">↗</span></a></aside>
    </div>
  </div>;
}
