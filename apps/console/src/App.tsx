import { useEffect, useRef, useState } from "react";
import { ApiClient, ApiError } from "./api/client";
import { ConnectSource } from "./features/sources/ConnectSource";
import { FirstForecast } from "./features/sources/FirstForecast";
import { ObservatoryBoard } from "./features/observatory/ObservatoryBoard";
import { Home } from "./features/home/Home";
import { SourcesCatalog } from "./features/home/SourcesCatalog";
import { ContextView } from "./features/context/ContextView";
import { Questions } from "./features/questions/Questions";
import type { SourceRegistration } from "./api/schema.generated";

type Page = "home" | "sources" | "questions" | "observatory" | "workspace";
const pages: { id: Page; label: string; path: string }[] = [
  { id: "home", label: "Home", path: "M3 10 10 4l7 6v8H5v-8m3 8v-6h4v6" },
  { id: "sources", label: "Fonti", path: "M4 5h12v12H4zM1 8h3m12 0h3M1 13h3m12 0h3" },
  { id: "questions", label: "Domande", path: "M4 4h12v12H4zM7 8h6M7 12h4" },
  { id: "observatory", label: "Osservatorio", path: "M2 16h16M3 12l4-4 4 3 6-8" },
  { id: "workspace", label: "Workspace", path: "M3 5h14v12H3zM7 5V3h6v2M3 10h14" },
];
type Resource = { workspaceId: string; kind: "run" | "question" | "report" | "backtest"; id: string; extended: boolean };
function readResource(hash: string): Resource | undefined {
  const match = /^\/w\/([a-f0-9]{32})\/(run|question|report|backtest)\/([^/]+)(\/full)?$/.exec(hash);
  if (!match) return undefined;
  try {
    const id = decodeURIComponent(match[3]);
    if (!id || id.includes("/") || id === "." || id === "..") return undefined;
    return { workspaceId: match[1], kind: match[2] as Resource["kind"], id, extended: Boolean(match[4]) };
  } catch { return undefined; }
}
const SESSION_KEY = "forecast-anything.workspace-session.v1";
function isEvidenceHash(value: string) { return value.startsWith("snapshot-") || value.startsWith("evaluation-") || value === "run-details-title"; }
function readPage(): Page { const value = window.location.hash.slice(1); return readResource(value) || isEvidenceHash(value) ? "observatory" : pages.some((page) => page.id === value) ? value as Page : "home"; }
function Brand() { return <a className="wordmark" href="#home" aria-label="Forecast Anything home"><img width="28" height="28" src="./mark.svg" alt=""/><span>Forecast Anything</span></a>; }
export function App() {
  const [page, setPage] = useState<Page>(readPage);
  const [routeHash, setRouteHash] = useState(() => window.location.hash.slice(1));
  const [menuOpen, setMenuOpen] = useState(false);
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [token, setToken] = useState("");
  const [sourceId, setSourceId] = useState("sales");
  const [workspace, setWorkspace] = useState<{ client: ApiClient; id: number; url: string; workspaceId: string }>();
  const [error, setError] = useState<string>();
  const [health, setHealth] = useState<{ status: string; worker: string; worker_model: string | null }>();
  const [modelStatus, setModelStatus] = useState<string>();
  const [hasStoredSession, setHasStoredSession] = useState(false);
  const connectionAttempt = useRef(0);
  const menuButton = useRef<HTMLButtonElement>(null);
  const firstNav = useRef<HTMLAnchorElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    function change() {
      const hash = window.location.hash.slice(1);
      if (pages.some((item) => item.id === hash) || readResource(hash) || isEvidenceHash(hash) || !hash) { setRouteHash(hash); setPage(readPage()); setMenuOpen(false); }
    }
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    if (!isEvidenceHash(routeHash)) { heading.current?.focus(); return; }
    function focusEvidence() {
      const target = document.getElementById(routeHash);
      if (!target) return false;
      const focusTarget = target.querySelector<HTMLElement>("h1, h2, h3, h4") ?? target;
      focusTarget.setAttribute("tabindex", "-1");
      focusTarget.focus({ preventScroll: true });
      focusTarget.scrollIntoView?.({ block: "start" });
      return true;
    }
    if (focusEvidence()) return;
    const observer = new MutationObserver(() => { if (focusEvidence()) observer.disconnect(); });
    observer.observe(document.getElementById("main-content")!, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [page, routeHash]);
  useEffect(() => { if (menuOpen) firstNav.current?.focus(); }, [menuOpen]);
  const resource = readResource(routeHash);
  const connected = workspace && (!resource || workspace.workspaceId === resource.workspaceId) ? workspace : undefined;
  const compact = !!resource && !resource.extended;
  useEffect(() => {
    let active = true;
    const attempt = ++connectionAttempt.current;
    async function restore() {
      try {
        const stored = localStorage.getItem(SESSION_KEY);
        if (active && attempt === connectionAttempt.current) setHasStoredSession(stored !== null);
        const saved = JSON.parse(stored || "null") as { url?: unknown; token?: unknown } | null;
        if (!saved || typeof saved.url !== "string" || typeof saved.token !== "string") return;
        const client = new ApiClient(saved.url, saved.token);
        const capabilities = await client.getCapabilities();
        const [identity, state] = await Promise.all([client.getWorkspace(), client.getHealth()]);
        if (!active || attempt !== connectionAttempt.current) return;
        const target = readResource(window.location.hash.slice(1));
        if (target && target.workspaceId !== identity.workspace_id) {
          setError("Il link appartiene a un workspace diverso.");
          return;
        }
        setHealth(state);
        setModelStatus(capabilities.model_status?.status ?? (capabilities.required_provider ? "sconosciuto" : "non richiesto"));
        setWorkspace((current) => ({ client, id: (current?.id ?? 0) + 1, url: saved.url as string, workspaceId: identity.workspace_id }));
      } catch { if (active && attempt === connectionAttempt.current) setError("Impossibile verificare la sessione del workspace."); }
    }
    void restore();
    return () => { active = false; };
  }, []);
  useEffect(() => {
    function sessionChanged(event: StorageEvent) {
      if (event.storageArea !== localStorage || event.key !== SESSION_KEY) return;
      connectionAttempt.current += 1;
      setHasStoredSession(event.newValue !== null);
      setWorkspace(undefined); setHealth(undefined); setModelStatus(undefined); setToken("");
      setError("La sessione del browser è cambiata. Collega il workspace per continuare.");
    }
    window.addEventListener("storage", sessionChanged);
    return () => window.removeEventListener("storage", sessionChanged);
  }, []);
  function disconnect() {
    connectionAttempt.current += 1;
    localStorage.removeItem(SESSION_KEY);
    setHasStoredSession(false);
    setWorkspace(undefined); setHealth(undefined); setModelStatus(undefined); setToken(""); setError(undefined);
  }
  async function connect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const attempt = ++connectionAttempt.current;
    try {
      const url = new URL(apiUrl);
      if (!token.trim()) throw new Error("Completa il token workspace.");
      if (!["http:", "https:"].includes(url.protocol)) throw new Error("Usa un indirizzo HTTP o HTTPS.");
      const client = new ApiClient(url.toString(), token);
      setError(undefined);
      const capabilities = await client.getCapabilities();
      const [identity, state] = await Promise.all([client.getWorkspace(), client.getHealth()]);
      if (attempt !== connectionAttempt.current) return;
      const target = readResource(window.location.hash.slice(1));
      if (target && target.workspaceId !== identity.workspace_id) {
        setError("Il link appartiene a un workspace diverso.");
        return;
      }
      setHealth(state);
      setModelStatus(capabilities.model_status?.status ?? (capabilities.required_provider ? "sconosciuto" : "non richiesto"));
      localStorage.setItem(SESSION_KEY, JSON.stringify({ url: url.toString().replace(/\/+$/, ""), token }));
      setHasStoredSession(true);
      setWorkspace((current) => ({ client, id: (current?.id ?? 0) + 1, url: url.origin, workspaceId: identity.workspace_id }));
      setToken("");
      if (!target) window.location.hash = "sources";
    } catch (reason) { if (attempt !== connectionAttempt.current) return; setError(reason instanceof ApiError && reason.status === 401 ? "Token workspace non valido." : "Impossibile verificare la connessione al workspace."); }
  }
  return <div className={`app-frame${menuOpen ? " menu-open" : ""}${compact ? " compact-route" : ""}`}>
    <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); heading.current?.focus(); }}>Vai al contenuto</a>
    {!compact && <aside className="app-sidebar"><Brand/><nav id="main-navigation" aria-label="Navigazione principale" onKeyDown={(event) => {
      if (event.key === "Escape") { setMenuOpen(false); menuButton.current?.focus(); }
      if (menuOpen && event.key === "Tab") {
        const links = event.currentTarget.querySelectorAll("a");
        if (event.shiftKey && document.activeElement === links[0]) { event.preventDefault(); links[links.length - 1]?.focus(); }
        else if (!event.shiftKey && document.activeElement === links[links.length - 1]) { event.preventDefault(); links[0]?.focus(); }
      }
    }}>{pages.map((item, index) => <a key={item.id} ref={index === 0 ? firstNav : undefined} href={`#${item.id}`} aria-current={page === item.id ? "page" : undefined} onClick={() => { setMenuOpen(false); heading.current?.focus(); }}><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true"><path d={item.path}/></svg>{item.label}</a>)}</nav><div className="sidebar-scope"><span>Core indipendente</span><p>Dati, ipotesi e futuri<br/>restano distinguibili.</p></div></aside>}
    <header className="app-topbar">{!compact && <button ref={menuButton} className="menu-toggle" aria-label="Apri navigazione" aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen((value) => !value)}><svg width="20" height="20" viewBox="0 0 20 20" stroke="currentColor" aria-hidden="true"><path d="M3 5h14M3 10h14M3 15h14"/></svg></button>}<span className="topbar-product">Forecast Anything</span><a href="#workspace" className="workspace-status"><span className={connected ? "connection-dot connected" : "connection-dot"}/>{connected ? connected.url : "Workspace da configurare"}</a></header>
    <main id="main-content" className="app-sheet">{resource && <a className="context-mode" href={`#/w/${resource.workspaceId}/${resource.kind}/${encodeURIComponent(resource.id)}${resource.extended ? "" : "/full"}`}>{resource.extended ? "Vista compatta" : "Vista estesa"}</a>}<div className="page-heading"><div><h1 ref={heading} tabIndex={-1}>{pages.find((item) => item.id === page)?.label}</h1><p>{page === "home" ? "Prepara una previsione o riapri un risultato." : page === "sources" ? "Collega e interpreta i dati prima di attivarli." : page === "observatory" ? "Previsioni, evidenze e dipendenze dei tuoi dati." : "La connessione al tuo core di forecasting."}</p></div>{page === "home" && workspace && <a className="button button-outline" href="#sources">Collega una fonte <span aria-hidden="true">＋</span></a>}</div>
      {(page === "workspace" || (!!resource && !connected)) && <section className="workspace-settings" aria-labelledby="connection-title"><div><h2 id="connection-title">Il tuo workspace</h2><p className="muted">Usa l’indirizzo del core e il suo token. La sessione resta disponibile nelle schede di questo profilo browser finché non la scolleghi.</p>{connected && health && <ul aria-label="Stato workspace"><li>API disponibile</li><li>Autenticazione valida</li><li>Worker: {health.worker}</li><li>Disponibilità modello: {modelStatus ?? "sconosciuta"}</li><li>Modello caricato dal worker: {health.worker_model ?? "sconosciuto"}</li></ul>}{hasStoredSession && <button type="button" onClick={disconnect}>Scollega questo browser</button>}</div><form onSubmit={connect}><label>Indirizzo API<input type="url" value={apiUrl} onChange={(event) => setApiUrl(event.target.value)}/></label><label>Token workspace<input type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)}/></label>{error && <p role="alert">{error}</p>}<button className="button button-dark" type="submit">Apri il workspace <span aria-hidden="true">↗</span></button></form></section>}
      {connected ? <ConnectedWorkspace key={connected.id} client={connected.client} page={page} sourceId={sourceId} onSourceIdChange={setSourceId} resource={resource} workspaceId={connected.workspaceId}/> : page === "home" ? <Home onRunReady={() => undefined}/> : page !== "workspace" && <div className="disconnected-state"><h2>Apri il workspace per continuare</h2><p className="muted">Le fonti e le previsioni appartengono al tuo core.</p><a className="button button-dark" href="#workspace">Configura il workspace</a></div>}
      <footer className="app-footer"><span>Forecast Anything</span><span>Osservazioni → previsioni → verifica</span></footer>
    </main>
  </div>;
}
function ConnectedWorkspace({ client, page, sourceId, onSourceIdChange, resource, workspaceId }: { workspaceId: string; client: ApiClient; page: Page; sourceId: string; onSourceIdChange: (value: string) => void; resource?: Resource }) {
  const [registration, setRegistration] = useState<SourceRegistration>();
  const [requestedRunId, setRequestedRunId] = useState<string>();
  const [requestedRunVersion, setRequestedRunVersion] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  function openRun(id: string) { setRequestedRunId(id); setRequestedRunVersion((value) => value + 1); setReloadKey((value) => value + 1); window.location.hash = "observatory"; }
  if (resource) return <ContextView key={`${resource.workspaceId}:${resource.kind}:${resource.id}`} client={client} workspaceId={resource.workspaceId} resource={resource} />;
  return <>
    {page === "questions" && <Questions client={client} workspaceId={workspaceId} />}
    <div hidden={page !== "home"}><Home client={client} reloadKey={reloadKey} active={page === "home"} onRunReady={openRun}/></div>
    <div hidden={page !== "sources"}>
      <SourcesCatalog client={client} reloadKey={reloadKey} onSelect={(id) => { onSourceIdChange(id); setRegistration(undefined); }}/>
      <div className="sources-heading"><label>ID della fonte<input value={sourceId} onChange={(event) => { onSourceIdChange(event.target.value); setRegistration(undefined); }}/></label><p className="muted">Usa un identificativo stabile per collegare o rivedere una fonte.</p></div>
      {sourceId.trim() ? <div className="source-panel"><ConnectSource key={sourceId.trim()} client={client} sourceId={sourceId.trim()} onActivated={(value) => { setRegistration(value); setReloadKey((current) => current + 1); }} onDraftChange={() => setRegistration(undefined)}/></div> : <p className="muted">Inserisci l’ID della fonte per continuare.</p>}
      {registration?.source_id === sourceId.trim() && <FirstForecast key={registration.job_id} client={client} registration={registration} onRunReady={openRun}/>}
    </div>
    <div hidden={page !== "observatory"}><ObservatoryBoard client={client} requestedRunId={requestedRunId} requestedRunVersion={requestedRunVersion}/></div>
  </>;
}
