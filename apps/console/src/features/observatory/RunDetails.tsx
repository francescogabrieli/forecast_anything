import type {
  EvaluationRecord,
  ForecastResult,
  GraphSpec,
  RunRecord,
  Snapshot,
  Watch,
} from "../../api/schema.generated";
import { ForecastChart } from "./ForecastChart";
import { formatUtc } from "../../format";

type Props = {
  run: RunRecord;
  evaluations: EvaluationRecord[];
  snapshots?: Snapshot[];
  watch?: Watch;
  evaluationsUnavailable?: boolean;
  graph?: GraphSpec;
  sourceBindings?: Record<string, string>;
};

type MetricLeaf = { path: string[]; value: unknown };
const metricLabels: Record<string, string> = {
  mae: "Errore assoluto medio · MAE",
  count: "Valori confrontati",
  status: "Esito",
  baseline_node_id: "Riferimento",
  relative_mae: "Errore relativo",
  relative_mae_reason: "Motivo",
  coverage: "Copertura",
  width: "Ampiezza",
  level: "Livello",
  pinball: "Pinball loss",
};
const metricValues: Record<string, string> = {
  evaluated: "Valutata",
  insufficient_evidence: "Evidenza insufficiente",
  pending: "In attesa",
  unmatched_baseline: "Baseline non abbinata",
  no_matched_cells: "Nessun valore abbinato",
  zero_baseline_mae: "Errore baseline pari a zero",
  ratio_unrepresentable: "Rapporto non rappresentabile",
};
const evaluationLabels: Record<EvaluationRecord["status"], string> = {
  evaluated: "Valutata",
  pending: "In attesa",
  insufficient_evidence: "Evidenza insufficiente",
};
function metricLabel(path: string[]) {
  return path
    .map((part, index) =>
      index === path.length - 1
        ? (metricLabels[part.toLowerCase()] ?? part.replaceAll("_", " "))
        : part,
    )
    .join(" · ");
}
function metricValue(value: unknown) {
  if (typeof value === "boolean") return value ? "Sì" : "No";
  if (typeof value === "string")
    return metricValues[value] ?? value.replaceAll("_", " ");
  return value == null ? "—" : String(value);
}
function metricLeaves(value: unknown, path: string[] = []): MetricLeaf[] {
  return value !== null && typeof value === "object"
    ? Object.entries(value).flatMap(([key, child]) =>
        metricLeaves(child, [...path, key]),
      )
    : [{ path, value }];
}
function renderMetrics(leaves: MetricLeaf[]) {
  return (
    <dl className="recorded-metrics">
      {leaves.map(({ path, value }) => {
        const label = metricLabel(path);
        return (
          <div key={JSON.stringify(path)}>
            <dt>{label}</dt>
            <dd>{metricValue(value)}</dd>
          </div>
        );
      })}
    </dl>
  );
}

export function RunDetails({
  run,
  evaluations,
  snapshots = [],
  watch,
  evaluationsUnavailable = false,
  graph,
  sourceBindings = {},
}: Props) {
  const stateLabel =
    watch?.quality === "stale"
      ? "Previsione scaduta"
      : run.state === "experimental" || watch?.quality === "provisional"
        ? "Risultato sperimentale"
        : watch?.quality === "degraded"
          ? "Previsione degradata"
          : "Run registrato";
  const recordedState =
    run.state === "completed"
      ? "Completato"
      : run.state === "experimental"
        ? "Sperimentale"
        : run.state.replaceAll("_", " ");
  const evaluationsById = new Map(
    evaluations.map((evaluation) => [evaluation.evaluation_id, evaluation]),
  );

  const entries = Object.entries(run.results);
  const primary =
    entries.find(([id]) => id === "forecast") ??
    entries.find(([id]) => id === "model") ??
    entries[0];
  const others = entries.filter(([id]) => id !== primary?.[0]);
  const primaryNode =
    graph?.graph_id === run.graph_id && graph.version === run.graph_version
      ? graph.nodes.find((node) => node.node_id === primary?.[0])
      : undefined;
  const historyNode =
    primaryNode?.kind === "forecast" &&
    typeof primaryNode.config.history === "string"
      ? graph?.nodes.find((node) => node.node_id === primaryNode.config.history)
      : undefined;
  const sourceId =
    historyNode?.kind === "source" &&
    typeof historyNode.config.source_id === "string"
      ? historyNode.config.source_id
      : undefined;
  const snapshotId = sourceId ? sourceBindings[sourceId] : undefined;
  const history =
    snapshotId && run.snapshot_ids.includes(snapshotId)
      ? snapshots.find((snapshot) => snapshot.snapshot_id === snapshotId)
      : undefined;

  const renderResult = (nodeId: string, result: ForecastResult) => (
    <section className="result-block" key={nodeId}>
      <h3>{nodeId}</h3>
      <p className="muted">
        Provider: {result.provider_id} · {result.provider_revision}
      </p>
      {result.point && (
        <div className="table-scroll">
          <table>
            <caption>Valori puntuali</caption>
            <thead>
              <tr>
                <th>Serie</th>
                <th>Timestamp</th>
                <th>Valore</th>
                <th>Unità</th>
              </tr>
            </thead>
            <tbody>
              {result.series_ids.flatMap((seriesId, seriesIndex) =>
                result.timestamps.map((timestamp, timeIndex) => (
                  <tr key={`${seriesId}-${timestamp}`}>
                    <td>{seriesId}</td>
                    <td>{formatUtc(timestamp)}</td>
                    <td>{result.point?.[seriesIndex]?.[timeIndex] ?? "—"}</td>
                    <td>{result.units[seriesIndex]}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}
      {result.quantiles && (
        <section
          role="group"
          aria-label="Intervallo previsto"
          className="quantile-block"
        >
          <h4>Intervallo previsto</h4>
          <p>I quantili sono riportati come forniti dal modello.</p>
          <dl>
            {Object.entries(result.quantiles).map(([quantile, values]) => (
              <div key={quantile}>
                <dt>Quantile {quantile}</dt>
                <dd>{values.flat().join(" · ")}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      {result.paths && (
        <p className="muted">
          Traiettorie congiunte: {result.paths.length} · gruppo{" "}
          {result.sample_group_id}
        </p>
      )}
      {result.assumptions.length > 0 && (
        <div className="assumption-list">
          <h4>Assunzioni</h4>
          <ul>
            {result.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );

  return (
    <section className="run-card" aria-labelledby="run-details-title">
      <div className="section-heading">
        <h2 id="run-details-title">Risultato</h2>
        <span className={`run-state ${watch?.quality ?? run.state}`}>
          {stateLabel}
        </span>
      </div>
      <div className="forecast-summary">
        {evaluationsUnavailable ? (
          <p>Valutazioni non disponibili</p>
        ) : (
          evaluations.length === 0 && <p>Non ancora valutata</p>
        )}
        {(primary ? [primary] : []).map(([nodeId, result]) => (
          <div key={nodeId}>
            <p className="forecast-model">
              {nodeId} · {result.provider_id}
            </p>
            <div className="forecast-issued">
              {result.series_ids.flatMap((series, seriesIndex) =>
                result.timestamps.map((time, timeIndex) => (
                  <p key={`${series}-${time}`}>
                    <span>
                      {series} · {formatUtc(time)}
                    </span>
                    <br />
                    <strong>
                      {result.point?.[seriesIndex]?.[timeIndex] ?? "—"}
                    </strong>{" "}
                    {result.units[seriesIndex]}
                  </p>
                )),
              )}
            </div>
            {!history && (
              <p className="muted">
                Storico osservato non disponibile: la provenienza dell’input non
                è risolta.
              </p>
            )}
            <ForecastChart
              result={result}
              origin={run.as_of}
              observations={history?.observations ?? []}
            />
          </div>
        ))}
      </div>
      <p className="run-id">ID run: {run.run_id}</p>
      <dl className="run-meta">
        <div>
          <dt>Emissione</dt>
          <dd>{formatUtc(run.as_of)}</dd>
        </div>
        <div>
          <dt>Stato</dt>
          <dd>{recordedState}</dd>
        </div>
        <div>
          <dt>Grafo</dt>
          <dd>
            {run.graph_id} · v{run.graph_version}
          </dd>
        </div>
      </dl>
      {primary && (
        <details className="technical-results">
          <summary>Dati e assunzioni del risultato</summary>
          {renderResult(primary[0], primary[1])}
        </details>
      )}
      {others.length > 0 && (
        <details className="technical-results">
          <summary>Altri risultati del grafo</summary>
          {others.map(([nodeId, result]) => renderResult(nodeId, result))}
        </details>
      )}
      <section className="evidence-block" aria-labelledby="evidence-title">
        <h3 id="evidence-title">Evidenze e input</h3>
        {run.evidence_ids.length === 0 && run.snapshot_ids.length === 0 ? (
          <p className="muted">
            Questo run non ha evidenze o snapshot associati.
          </p>
        ) : (
          <ul>
            {run.evidence_ids.map((id) => (
              <li key={id}>
                <a href={`#evaluation-${id}`}>{id}</a>
                {evaluationsById.has(id) ? " · valutazione" : " · evidenza"}
              </li>
            ))}
            {run.snapshot_ids.map((id) => (
              <li key={id}>
                <a href={`#snapshot-${id}`}>{id}</a> · snapshot usato nel run
              </li>
            ))}
          </ul>
        )}
        {evaluations.map((evaluation) => (
          <article
            className="evaluation-item"
            id={`evaluation-${evaluation.evaluation_id}`}
            key={evaluation.evaluation_id}
          >
            <h4>Valutazione {evaluation.evaluation_id}</h4>
            <div className="evaluation-heading">
              <span className={`evaluation-status ${evaluation.status}`}>
                {evaluationLabels[evaluation.status]}
              </span>
              <span>
                {evaluation.origin_count}{" "}
                {evaluation.origin_count === 1
                  ? "origine valutata"
                  : "origini valutate"}
              </span>
            </div>
            {renderMetrics(
              metricLeaves(evaluation.metrics).filter(
                (metric) => metric.path.length <= 2,
              ),
            )}
            {metricLeaves(evaluation.metrics).some(
              (metric) => metric.path.length > 2,
            ) && (
              <details className="technical-results">
                <summary>Altre metriche registrate</summary>
                {renderMetrics(
                  metricLeaves(evaluation.metrics).filter(
                    (metric) => metric.path.length > 2,
                  ),
                )}
              </details>
            )}
            <details className="evaluation-context">
              <summary>Input e metodo</summary>
              <p>
                <a href={`#snapshot-${evaluation.actuals_snapshot_id}`}>
                  Apri snapshot effettivi
                </a>
              </p>
              <code>{evaluation.evaluation_id}</code>
              {evaluation.assumptions.length > 0 && (
                <ul>
                  {evaluation.assumptions.map((assumption) => (
                    <li key={assumption}>{assumption}</li>
                  ))}
                </ul>
              )}
            </details>
          </article>
        ))}
        {snapshots.map((snapshot) => (
          <article
            className="snapshot-item"
            id={`snapshot-${snapshot.snapshot_id}`}
            key={snapshot.snapshot_id}
          >
            <h4>Snapshot {snapshot.snapshot_id}</h4>
            <p>Disponibile al {formatUtc(snapshot.as_of)}</p>
            <details>
              <summary>Osservazioni e assunzioni dello snapshot</summary>
              <ul>
                {snapshot.observations.map((observation, index) => (
                  <li
                    key={`${observation.series_id}-${observation.event_time}-${index}`}
                  >
                    {observation.series_id} ·{" "}
                    {formatUtc(observation.event_time)} ·{" "}
                    {observation.value ?? "valore mancante"} {observation.unit}
                  </li>
                ))}
              </ul>
              {snapshot.assumptions.length > 0 && (
                <ul>
                  {snapshot.assumptions.map((assumption) => (
                    <li key={assumption}>{assumption}</li>
                  ))}
                </ul>
              )}
            </details>
          </article>
        ))}
        {run.snapshot_ids
          .filter(
            (id) => !snapshots.some((snapshot) => snapshot.snapshot_id === id),
          )
          .map((id) => (
            <span className="sr-only" id={`snapshot-${id}`} key={id}>
              Snapshot {id}
            </span>
          ))}
      </section>
    </section>
  );
}
