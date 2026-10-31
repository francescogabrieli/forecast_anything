import { useEffect, useRef, useState } from "react";
import { ApiClient } from "./api/client";
import { ConnectSource } from "./features/sources/ConnectSource";
import { FirstForecast } from "./features/sources/FirstForecast";
import { ObservatoryBoard } from "./features/observatory/ObservatoryBoard";
import { Home } from "./features/home/Home";
import { SourcesCatalog } from "./features/home/SourcesCatalog";
import type { SourceRegistration } from "./api/schema.generated";

type Page = "home" | "sources" | "observatory" | "workspace";
const pages: { id: Page; label: string; path: string }[] = [
  { id: "home", label: "Home", path: "M3 10 10 4l7 6v8H5v-8m3 8v-6h4v6" },
  { id: "sources", label: "Fonti", path: "M4 5h12v12H4zM1 8h3m12 0h3M1 13h3m12 0h3" },
  { id: "observatory", label: "Osservatorio", path: "M2 16h16M3 12l4-4 4 3 6-8" },
  { id: "workspace", label: "Workspace", path: "M3 5h14v12H3zM7 5V3h6v2M3 10h14" },
];
function isEvidenceHash(value: string) { return value.startsWith("snapshot-") || value.startsWith("evaluation-") || value === "run-details-title"; }
function readPage(): Page { const value = window.location.hash.slice(1); return isEvidenceHash(value) ? "observatory" : pages.some((page) => page.id === value) ? value as Page : "home"; }
function Brand() { return <a className="wordmark" href="#home" aria-label="Forecast Anything home"><svg className="product-mark" width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M3 23 10 17 16 19 23 8M16 19l12-1M16 19l10 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/><circle cx="16" cy="19" r="3" fill="var(--surface)" stroke="currentColor" strokeWidth="2"/><circle cx="23" cy="8" r="2" fill="currentColor"/><circle cx="28" cy="18" r="2" fill="currentColor"/></svg><span>Forecast<br/>Anything</span></a>; }
export function App() {
  const [page, setPage] = useState<Page>(readPage);
  const [routeHash, setRouteHash] = useState(() => window.location.hash.slice(1));
  const [menuOpen, setMenuOpen] = useState(false);
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [token, setToken] = useState("");
  const [sourceId, setSourceId] = useState("sales");
  const [workspace, setWorkspace] = useState<{ client: ApiClient; id: number; url: string }>();
  const [error, setError] = useState<string>();
  const menuButton = useRef<HTMLButtonElement>(null);
  const firstNav = useRef<HTMLAnchorElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    function change() {
      const hash = window.location.hash.slice(1);
      if (pages.some((item) => item.id === hash) || isEvidenceHash(hash) || !hash) { setRouteHash(hash); setPage(readPage()); setMenuOpen(false); }
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
  function connect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const url = new URL(apiUrl);
      if (!token.trim()) throw new Error("Completa il token workspace.");
      if (!["http:", "https:"].includes(url.protocol)) throw new Error("Usa un indirizzo HTTP o HTTPS.");
      setError(undefined); setWorkspace({ client: new ApiClient(url.toString(), token), id: (workspace?.id ?? 0) + 1, url: url.origin });
      window.location.hash = "sources";
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Controlla i dati di connessione."); }
  }
  return <div className={`app-frame${menuOpen ? " menu-open" : ""}`}>
    <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); heading.current?.focus(); }}>Vai al contenuto</a>
    <aside className="app-sidebar"><Brand/><nav id="main-navigation" aria-label="Navigazione principale" onKeyDown={(event) => {
      if (event.key === "Escape") { setMenuOpen(false); menuButton.current?.focus(); }
      if (menuOpen && event.key === "Tab") {
        const links = event.currentTarget.querySelectorAll("a");
        if (event.shiftKey && document.activeElement === links[0]) { event.preventDefault(); links[links.length - 1]?.focus(); }
        else if (!event.shiftKey && document.activeElement === links[links.length - 1]) { event.preventDefault(); links[0]?.focus(); }
      }
    }}>{pages.map((item, index) => <a key={item.id} ref={index === 0 ? firstNav : undefined} href={`#${item.id}`} aria-current={page === item.id ? "page" : undefined} onClick={() => { setMenuOpen(false); heading.current?.focus(); }}><svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true"><path d={item.path}/></svg>{item.label}</a>)}</nav><div className="sidebar-scope"><span>Core indipendente</span><p>Dati, ipotesi e futuri<br/>restano distinguibili.</p></div></aside>
    <header className="app-topbar"><button ref={menuButton} className="menu-toggle" aria-label="Apri navigazione" aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen((value) => !value)}><svg width="20" height="20" viewBox="0 0 20 20" stroke="currentColor" aria-hidden="true"><path d="M3 5h14M3 10h14M3 15h14"/></svg></button><span className="topbar-product">Forecast Anything</span><a href="#workspace" className="workspace-status"><span className={workspace ? "connection-dot connected" : "connection-dot"}/>{workspace ? workspace.url : "Workspace da configurare"}</a></header>
    <main id="main-content" className="app-sheet"><div className="page-heading"><div><h1 ref={heading} tabIndex={-1}>{pages.find((item) => item.id === page)?.label}</h1><p>{page === "home" ? "Le tue fonti, i prossimi futuri." : page === "sources" ? "Collega e interpreta i dati prima di attivarli." : page === "observatory" ? "Previsioni, evidenze e dipendenze dei tuoi dati." : "La connessione al tuo core di forecasting."}</p></div>{page === "home" && workspace && <a className="button button-outline" href="#sources">Collega una fonte <span aria-hidden="true">＋</span></a>}</div>
      {page === "workspace" && <section className="workspace-settings" aria-labelledby="connection-title"><div><h2 id="connection-title">Il tuo workspace</h2><p className="muted">Usa l’indirizzo del core e il suo token. Il token resta in memoria per questa sessione e non viene salvato nel browser.</p></div><form onSubmit={connect}><label>Indirizzo API<input type="url" value={apiUrl} onChange={(event) => setApiUrl(event.target.value)}/></label><label>Token workspace<input type="password" autoComplete="off" value={token} onChange={(event) => setToken(event.target.value)}/></label>{error && <p role="alert">{error}</p>}<button className="button button-dark" type="submit">Apri il workspace <span aria-hidden="true">↗</span></button></form></section>}
      {workspace ? <ConnectedWorkspace key={workspace.id} client={workspace.client} page={page} sourceId={sourceId} onSourceIdChange={setSourceId}/> : page === "home" ? <Home onRunReady={() => undefined}/> : page !== "workspace" && <div className="disconnected-state"><h2>Apri il workspace per continuare</h2><p className="muted">Le fonti e le previsioni appartengono al tuo core.</p><a className="button button-dark" href="#workspace">Configura il workspace</a></div>}
      <footer className="app-footer"><span>Forecast Anything</span><span>Osservazioni → previsioni → verifica</span></footer>
    </main>
  </div>;
}
function ConnectedWorkspace({ client, page, sourceId, onSourceIdChange }: { client: ApiClient; page: Page; sourceId: string; onSourceIdChange: (value: string) => void }) {
  const [registration, setRegistration] = useState<SourceRegistration>();
  const [requestedRunId, setRequestedRunId] = useState<string>();
  const [requestedRunVersion, setRequestedRunVersion] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  function openRun(id: string) { setRequestedRunId(id); setRequestedRunVersion((value) => value + 1); setReloadKey((value) => value + 1); window.location.hash = "observatory"; }
  return <>
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
