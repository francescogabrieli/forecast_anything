import type { EvaluationRecord, RunRecord, Snapshot, Watch } from "../../api/schema.generated";
import { formatUtc } from "../../format";

type Props = { run: RunRecord; evaluations: EvaluationRecord[]; snapshots?: Snapshot[]; watch?: Watch };

export function RunDetails({ run, evaluations, snapshots = [], watch }: Props) {
  const stateLabel = watch?.quality === "stale"
    ? "Previsione scaduta"
    : run.state === "experimental" || watch?.quality === "provisional"
      ? "Risultato sperimentale"
      : watch?.quality === "degraded"
        ? "Previsione degradata"
        : "Run registrato";
  const evaluationsById = new Map(evaluations.map((evaluation) => [evaluation.evaluation_id, evaluation]));

  return (
    <section className="run-card" aria-labelledby="run-details-title">
      <div className="section-heading"><h2 id="run-details-title">Risultato</h2><span className={`run-state ${watch?.quality ?? run.state}`}>{stateLabel}</span></div>
      <p className="run-id">ID run: {run.run_id}</p>
      <dl className="run-meta"><div><dt>Emissione</dt><dd>{formatUtc(run.as_of)}</dd></div><div><dt>Stato</dt><dd>{run.state}</dd></div><div><dt>Grafo</dt><dd>{run.graph_id} · v{run.graph_version}</dd></div></dl>
      {Object.entries(run.results).map(([nodeId, result]) => (
        <section className="result-block" key={nodeId}>
          <h3>{nodeId}</h3>
          <p className="muted">Provider: {result.provider_id} · {result.provider_revision}</p>
          {result.point && <div className="table-scroll"><table><caption>Valori puntuali</caption><thead><tr><th>Serie</th><th>Timestamp</th><th>Valore</th><th>Unità</th></tr></thead><tbody>
            {result.series_ids.flatMap((seriesId, seriesIndex) => result.timestamps.map((timestamp, timeIndex) => <tr key={`${seriesId}-${timestamp}`}><td>{seriesId}</td><td>{formatUtc(timestamp)}</td><td>{result.point?.[seriesIndex]?.[timeIndex] ?? "—"}</td><td>{result.units[seriesIndex]}</td></tr>))}
          </tbody></table></div>}
          {result.quantiles && <section role="group" aria-label="Intervallo previsto" className="quantile-block"><h4>Intervallo previsto</h4><p>I quantili sono riportati come forniti dal modello.</p><dl>{Object.entries(result.quantiles).map(([quantile, values]) => <div key={quantile}><dt>Quantile {quantile}</dt><dd>{values.flat().join(" · ")}</dd></div>)}</dl></section>}
          {result.paths && <p className="muted">Traiettorie congiunte: {result.paths.length} · gruppo {result.sample_group_id}</p>}
          {result.assumptions.length > 0 && <div className="assumption-list"><h4>Assunzioni</h4><ul>{result.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul></div>}
        </section>
      ))}
      <section className="evidence-block" aria-labelledby="evidence-title">
        <h3 id="evidence-title">Evidenze e input</h3>
        {run.evidence_ids.length === 0 && run.snapshot_ids.length === 0 ? <p className="muted">Questo run non ha evidenze o snapshot associati.</p> : <ul>
          {run.evidence_ids.map((id) => <li key={id}><a href={`#evaluation-${id}`}>{id}</a>{evaluationsById.has(id) ? " · valutazione" : " · evidenza"}</li>)}
          {run.snapshot_ids.map((id) => <li key={id}><a href={`#snapshot-${id}`}>{id}</a> · snapshot usato nel run</li>)}
        </ul>}
        {evaluations.map((evaluation) => <article className="evaluation-item" id={`evaluation-${evaluation.evaluation_id}`} key={evaluation.evaluation_id}>
          <h4>Valutazione {evaluation.evaluation_id}</h4>
          <p>{evaluation.status} · {evaluation.origin_count} origini</p>
          <a href={`#snapshot-${evaluation.actuals_snapshot_id}`}>Input effettivi: {evaluation.actuals_snapshot_id}</a>
          {evaluation.assumptions.length > 0 && <ul>{evaluation.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>}
        </article>)}
        {snapshots.map((snapshot) => <article className="snapshot-item" id={`snapshot-${snapshot.snapshot_id}`} key={snapshot.snapshot_id}>
          <h4>Snapshot {snapshot.snapshot_id}</h4><p>Disponibile al {formatUtc(snapshot.as_of)}</p>
          <ul>{snapshot.observations.map((observation, index) => <li key={`${observation.series_id}-${observation.event_time}-${index}`}>{observation.series_id} · {formatUtc(observation.event_time)} · {observation.value ?? "valore mancante"} {observation.unit}</li>)}</ul>
          {snapshot.assumptions.length > 0 && <ul>{snapshot.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>}
        </article>)}
        {run.snapshot_ids.filter((id) => !snapshots.some((snapshot) => snapshot.snapshot_id === id)).map((id) => <span className="sr-only" id={`snapshot-${id}`} key={id}>Snapshot {id}</span>)}
      </section>
    </section>
  );
}
