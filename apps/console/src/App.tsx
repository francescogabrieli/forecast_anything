import { useState } from "react";
import { ApiClient } from "./api/client";
import { ConnectSource } from "./features/sources/ConnectSource";
import { FirstForecast } from "./features/sources/FirstForecast";
import { ObservatoryBoard } from "./features/observatory/ObservatoryBoard";
import type { SourceRegistration } from "./api/schema.generated";

export function App() {
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [token, setToken] = useState("");
  const [sourceId, setSourceId] = useState("sales");
  const [client, setClient] = useState<ApiClient>();
  const [registration, setRegistration] = useState<SourceRegistration>();
  const [requestedRunId, setRequestedRunId] = useState<string>();
  const [error, setError] = useState<string>();

  function connect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const url = new URL(apiUrl);
      if (!token.trim() || !sourceId.trim()) throw new Error("Completa token e ID della fonte.");
      if (!new Set(["http:", "https:"]).has(url.protocol)) throw new Error("Usa un indirizzo HTTP o HTTPS.");
      setError(undefined);
      setRegistration(undefined);
      setRequestedRunId(undefined);
      setClient(new ApiClient(url.toString(), token));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Controlla i dati di connessione.");
    }
  }

  return (
    <main className="shell">
      <header className="masthead">
        <a className="wordmark" href="/" aria-label="Forecast Anything home">
          <span className="mark" aria-hidden="true">F</span>
          <span>Forecast Anything</span>
        </a>
        <span className="eyebrow">Osservatorio predittivo</span>
      </header>
      <section className="intro">
        <p className="kicker">Dai dati ai futuri verificabili</p>
        <h1>Collega una fonte.</h1>
        <p className="lede">Rivedi il significato dei dati prima che il sistema inizi a seguirli.</p>
      </section>
      <div className="workspace-grid">
        <aside className="connection-card" aria-labelledby="connection-title">
          <div className="card-heading">
            <div>
              <p className="kicker">Connessione locale</p>
              <h2 id="connection-title">Il tuo workspace</h2>
            </div>
          </div>
          <p className="muted">Il token resta in memoria per questa sessione e non viene salvato nel browser.</p>
          <form onSubmit={connect}>
            <label>
              Indirizzo API
              <input type="url" value={apiUrl} onChange={(event) => setApiUrl(event.target.value)} />
            </label>
            <label>
              Token workspace
              <input type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)} />
            </label>
            <label>
              ID della fonte
              <input value={sourceId} onChange={(event) => { setSourceId(event.target.value); setRegistration(undefined); }} />
            </label>
            {error && <p role="alert" className="error-message">{error}</p>}
            <button className="button button-dark" type="submit">Apri il workspace <span aria-hidden="true">↗</span></button>
          </form>
        </aside>
        <section className="guide-card" aria-label="Percorso di collegamento">
          <div className="guide-topline"><span>Il percorso</span><span>4 passaggi</span></div>
          <ol className="steps">
            <li className={client ? "step complete" : "step current"}>
              <span className="step-dot" aria-hidden="true">1</span>
              <div><strong>Connetti</strong><p>Apri il workspace del tuo core.</p></div>
            </li>
            <li className={registration ? "step complete" : client ? "step current" : "step"}>
              <span className="step-dot" aria-hidden="true">2</span>
              <div><strong>Interpreta</strong><p>Controlla campi, unità e assunzioni.</p></div>
            </li>
            <li className={registration ? "step complete" : "step"}>
              <span className="step-dot" aria-hidden="true">3</span>
              <div><strong>Attiva</strong><p>Solo quando la mappatura è completa.</p></div>
            </li>
            <li className={registration ? "step current" : "step"}>
              <span className="step-dot" aria-hidden="true">4</span>
              <div><strong>Prevedi</strong><p>Calcola e rivedi la prima stima.</p></div>
            </li>
          </ol>
          <div className="guide-note"><span aria-hidden="true">↳</span><p>Le osservazioni, le assunzioni e le stime restano distinguibili in ogni passaggio.</p></div>
        </section>
      </div>
      {client && <div className="source-panel"><ConnectSource client={client} sourceId={sourceId.trim()} onActivated={setRegistration} onDraftChange={() => setRegistration(undefined)} /></div>}
      {client && registration?.source_id === sourceId.trim() && <FirstForecast key={registration.job_id} client={client} registration={registration} onRunReady={setRequestedRunId} />}
      {client && <ObservatoryBoard client={client} requestedRunId={requestedRunId} />}
      <footer><span>Forecast Anything</span><span>Il nucleo funziona anche senza un modello linguistico.</span></footer>
    </main>
  );
}
