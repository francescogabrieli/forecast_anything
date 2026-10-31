import type { EventRecord, Watch } from "../../api/schema.generated";

type Props = {
  watches: Watch[];
  events: EventRecord[];
  onSelectRun?: (runId: string) => void;
  onToggleWatch?: (watch: Watch) => void;
};

const lifecycleLabels: Record<Watch["lifecycle"], string> = {
  candidate: "Candidata",
  evaluating: "In verifica",
  active: "Sorvegliata",
  paused: "In pausa",
  unsupported: "Non supportata",
};

const qualityLabels: Record<Watch["quality"], string> = {
  provisional: "Provvisoria",
  usable: "Valutabile",
  stale: "Scaduta",
  degraded: "Degradata",
};

const templateTitles: Record<string, string> = {
  expected_deviation: "Scostamento dal comportamento atteso",
  forecast_change: "Cambiamento della previsione",
  declared_limit: "Possibile superamento del limite dichiarato",
};

function uniqueByCursor(events: EventRecord[]): EventRecord[] {
  const cursors = new Map<number, EventRecord>();
  for (const event of events) {
    if (!cursors.has(event.cursor)) cursors.set(event.cursor, event);
  }
  return [...cursors.values()].sort((left, right) => left.cursor - right.cursor);
}

export function DiscoveryFeed({ watches, events, onSelectRun, onToggleWatch }: Props) {
  const uniqueEvents = uniqueByCursor(events);
  return (
    <section className="feed-card" aria-labelledby="discovery-feed-title">
      <div className="section-heading">
        <div><h2 id="discovery-feed-title">Scoperte e aggiornamenti</h2></div>
        <span className="count-pill">{uniqueEvents.length} eventi unici</span>
      </div>
      <div className="feed-columns">
        <section aria-labelledby="watches-title">
          <h3 id="watches-title">Domande sorvegliate</h3>
          {watches.length === 0 ? <p className="muted">Le nuove domande compariranno qui dopo la verifica.</p> : (
            <ul className="watch-list">
              {watches.map((watch) => {
                const candidate = watch.candidate;
                const title = candidate ? templateTitles[candidate.template_id] : undefined;
                return (
                  <li key={watch.watch_id}>
                    <div className="watch-title"><strong>{title ?? candidate?.reason ?? watch.candidate_id}</strong><span className={`quality-chip quality-${watch.quality}`}>{qualityLabels[watch.quality]}</span></div>
                    {title && candidate?.reason && <p className="watch-reason">Motivo: {candidate.reason}</p>}
                    <p>{lifecycleLabels[watch.lifecycle]} · {qualityLabels[watch.quality]} · priorità {watch.priority}</p>
                    {onToggleWatch && <button type="button" className="text-button" onClick={() => onToggleWatch(watch)}>{watch.muted ? "Riattiva segnalazioni" : "Silenzia segnalazioni"}</button>}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
        <details className="event-history">
          <summary id="events-title">Cronologia</summary>
          {uniqueEvents.length === 0 ? <p className="muted">Nessun aggiornamento registrato.</p> : (
            <ol className="event-list">
              {uniqueEvents.map((event) => (
                <li key={event.cursor}>
                  <span className="event-marker" aria-hidden="true" />
                  <div><span className="event-kind">{event.kind.replaceAll("_", " ")}</span>
                    {onSelectRun ? <button type="button" className="text-button" onClick={() => onSelectRun(event.run_id)}>Apri run {event.run_id}</button> : <span>Run {event.run_id}</span>}
                  </div>
                  <time>{typeof event.payload.emitted_at === "string" ? new Date(event.payload.emitted_at).toLocaleString("it-IT") : `#${event.cursor}`}</time>
                </li>
              ))}
            </ol>
          )}
        </details>
      </div>
    </section>
  );
}
