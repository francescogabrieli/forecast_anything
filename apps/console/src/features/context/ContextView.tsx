import { useEffect, useState } from "react";
import { ApiError, type ApiClient } from "../../api/client";
import type { BacktestPresentation, EvaluationRecord, ForecastPresentation, GraphSpec, OriginPage, QuestionPresentation, RunRecord } from "../../api/schema.generated";
import { formatUtc } from "../../format";
import { ForecastChart } from "../observatory/ForecastChart";
import { FutureGraph } from "../observatory/FutureGraph";
import { BacktestChart } from "./BacktestChart";

type Resource = { kind: "run" | "question" | "report" | "backtest"; id: string };
type Props = { client: ApiClient; workspaceId: string; resource: Resource };
type Result = { kind: "run"; value: ForecastPresentation } | { kind: "question"; value: QuestionPresentation } | { kind: "report"; value: BacktestPresentation };

export function ContextView({ client, workspaceId, resource }: Props) {
  const [result, setResult] = useState<Result>();
  const [error, setError] = useState<string>();
  const [offset, setOffset] = useState(0);
  const [origins, setOrigins] = useState<OriginPage>();
  const [details, setDetails] = useState<{ run: RunRecord; graph?: GraphSpec; evaluations?: EvaluationRecord[] }>();
  const [notice, setNotice] = useState<string>();
  useEffect(() => { setOffset(0); }, [resource.kind, resource.id]);
  useEffect(() => {
    let active = true;
    setResult(undefined); setError(undefined); setOrigins(undefined);
    const load = async () => {
      try {
        if (resource.kind === "run") {
          const value = await client.getForecastPresentation(resource.id);
          if (value.run_id !== resource.id) throw new Error("run identity mismatch");
          if (active) setResult({ kind: "run", value });
        } else if (resource.kind === "question") {
          const value = await client.getQuestionPresentation(resource.id, offset);
          if (value.question.question_id !== resource.id) throw new Error("question identity mismatch");
          if (active) setResult({ kind: "question", value });
        } else {
          const [value, page] = await Promise.all(resource.kind === "report" ? [client.getReportPresentation(resource.id), client.getReportOrigins(resource.id, offset).catch(() => undefined)] : [client.getBacktestPresentation(resource.id), client.getBacktestOrigins(resource.id, offset).catch(() => undefined)]);
          if ((resource.kind === "report" ? value.summary.report_id : value.summary.backtest_id) !== resource.id) throw new Error("report identity mismatch");
          if (active) { setResult({ kind: "report", value }); setOrigins(page); }
        }
      } catch (reason) {
        if (active) setError(reason instanceof ApiError && reason.status === 404 ? "Risorsa non trovata in questo workspace." : "Impossibile caricare il risultato.");
      }
    };
    void load();
    return () => { active = false; };
  }, [client, resource.kind, resource.id, offset]);
  useEffect(() => {
    if (resource.kind !== "run") return;
    let active = true;
    setDetails(undefined);
    void client.getRun(resource.id).then(async run => {
      if (run.run_id !== resource.id) throw new Error("run identity mismatch");
      const [graph, evaluations] = await Promise.allSettled([client.getGraph(run.graph_id, run.graph_version), client.getRunEvaluations(run.run_id)]);
      if (active) setDetails({ run, graph: graph.status === "fulfilled" ? graph.value : undefined, evaluations: evaluations.status === "fulfilled" ? evaluations.value : undefined });
    }).catch(() => { if (active) setDetails(undefined); });
    return () => { active = false; };
  }, [client, resource.kind, resource.id]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    void (async () => {
      let cursor = 0;
      for (;;) {
        const events = await client.getEvents(cursor, 1000);
        if (!active) return;
        const next = events.reduce((max, event) => Math.max(max, event.cursor), cursor);
        if (events.length === 0 || next <= cursor) break;
        cursor = next;
        if (events.length < 1000) break;
      }
      return client.streamEvents(cursor, event => {
        if (active && event.kind === "run_completed" && event.run_id !== resource.id)
          setNotice(`Nuovo risultato disponibile: ${event.run_id}. Il risultato aperto rimane selezionato.`);
      }, controller.signal);
    })().catch(() => undefined);
    return () => { active = false; controller.abort(); };
  }, [client, resource.kind, resource.id]);
  if (error) return <p role="alert">{error}</p>;
  if (!result) return <p role="status">Caricamento del risultato…</p>;
  if (result.kind === "question") {
    const { question, references, next_offset, inbox_events, inbox_total_count } = result.value;
    const deliveryStates = (event: typeof inbox_events[number]) => event.delivery_states ?? [];
    const deliveryLabels: Record<string, string> = {
      pending: "Consegna in attesa",
      delivering: "Consegna in corso",
      delivered: "Consegnata",
      delivery_failed: "Consegna fallita",
      delivery_suppressed_muted: "Consegna soppressa perché la domanda è silenziata",
    };
    return <section>{notice && <p role="status">{notice}</p>}<h2>{question.title}</h2><p>{question.revision.meaning}</p><p>Orizzonte: {question.revision.selection.horizon} · Stato: {question.status}</p><p>Notifiche: {question.muted ? "silenziate" : "attive"} · Priorità: {question.priority} (0 massima)</p><p>ID domanda: {question.question_id}</p><h3>Aggiornamenti recenti ({inbox_total_count})</h3>{inbox_events.length === 0 ? <p>Nessun aggiornamento registrato.</p> : <ul>{inbox_events.map(event => <li key={event.event_id}><p>{formatUtc(event.occurred_at)} · {event.summary}</p>{event.payload.quality === "provisional" && <p>Qualità provvisoria</p>}{event.muted && <p>Notifica silenziata al momento dell’evento</p>}{deliveryStates(event).length > 0 && <ul>{deliveryStates(event).map((state, index) => <li key={`${event.event_id}-${index}`}>{deliveryLabels[state] ?? state}</li>)}</ul>}</li>)}</ul>}<h3>Risultati collegati</h3>{references.length === 0 ? <p>Nessun risultato collegato.</p> : <ul>{references.map(({ reference, applies_to_current_revision }) => <li key={reference.reference_id}>{reference.target_type === "run" || reference.target_type === "backtest" ? <a href={`#/w/${workspaceId}/${reference.target_type === "run" ? "run" : "backtest"}/${encodeURIComponent(reference.target_id)}`}>{reference.target_type} {reference.target_id}</a> : <span>{reference.target_type} {reference.target_id}</span>}{!applies_to_current_revision && " · Riferimento storico: non applicabile alla revisione corrente"}</li>)}</ul>}{offset > 0 && <button onClick={() => setOffset(Math.max(0, offset - 3))}>Precedenti</button>}{next_offset != null && <button onClick={() => setOffset(next_offset)}>Altri risultati</button>}</section>;
  }
  if (result.kind === "report") {
    const { summary } = result.value;
    return <section>{notice && <p role="status">{notice}</p>}<h2>Confronto storico</h2><p>Stato: {summary.status} · Orizzonte: {summary.selection.horizon}</p><p>ID report: {summary.report_id}</p><p>{summary.interpretation_limit}</p><div className="table-scroll"><table><caption>Confronto e origini escluse</caption><thead><tr><th>Partizione</th><th>Valutate</th><th>Escluse</th><th>Fallite</th><th>MAE modello</th><th>MAE baseline</th></tr></thead><tbody>{summary.partitions.map(p => <tr key={p.partition}><td>{p.partition}</td><td>{p.evaluated ?? "—"}</td><td>{p.excluded ?? "—"}</td><td>{p.failed ?? "—"}</td><td>{p.model_mae ?? "Non disponibile"}</td><td>{p.baseline_mae ?? "Non disponibile"}</td></tr>)}</tbody></table></div><BacktestChart points={summary.final_origin_points} /><h3>Origini</h3>{!origins && <p>Dettaglio delle origini non disponibile; consulta il report nel browser.</p>}<ul>{origins?.origins.map(o => <li key={o.ordinal}>{formatUtc(o.target_start)} · {o.status}{o.reason_code ? ` · ${o.reason_code}` : ""}</li>)}</ul>{offset > 0 && <button onClick={() => setOffset(Math.max(0, offset - 50))}>Precedenti</button>}{origins?.next_offset != null && <button onClick={() => setOffset(origins.next_offset!)}>Altre origini</button>}<details><summary>Assunzioni e provenienza</summary><p>Fonte: {summary.source_id} · revisione {summary.source_revision}</p><ul>{summary.assumptions.map(a => <li key={a}>{a}</li>)}</ul></details></section>;
  }
  const value = result.value;
  const primary = value.points.filter(point => point.node_id === value.primary_node_id);
  const baselines = value.baseline_node_id ? value.points.filter(point => point.node_id === value.baseline_node_id) : [];
  const primaryResult = value.primary_node_id ? details?.run.results[value.primary_node_id] : undefined;
  return <section className="run-card">{notice && <p role="status">{notice}</p>}<h2>Previsione</h2><p>Risposta: {primary[0]?.point ?? "non disponibile"} {primary[0]?.unit ?? ""} · Orizzonte: {primaryResult?.timestamps.length ?? "non disponibile"} passi</p><p>Stato registrato: {value.state} · {details?.evaluations ? (details.evaluations.length ? `${details.evaluations.length} valutazioni storiche; applicabilità corrente non determinata` : "Non ancora valutata") : "Stato delle evidenze non disponibile"}</p><p>ID run: {value.run_id}</p>{value.truncated && <p>Risultati troncati: mostrati {value.points.length} di {value.total_point_count} punti.</p>}{primary.length === 0 ? <p>Valore principale non disponibile.</p> : <div className="table-scroll"><table><caption>Previsione e baseline allineata</caption><thead><tr><th>Serie</th><th>Data</th><th>Previsione</th><th>Baseline</th><th>Unità</th></tr></thead><tbody>{primary.map(p => { const b = baselines.find(x => x.series_id === p.series_id && x.timestamp === p.timestamp && x.unit === p.unit); return <tr key={`${p.series_id}-${p.timestamp}-${p.unit}`}><td>{p.series_id}</td><td>{formatUtc(p.timestamp)}</td><td>{p.point ?? "Non disponibile"}</td><td>{b?.point ?? "Non disponibile o non confrontabile"}</td><td>{p.unit}</td></tr>; })}</tbody></table></div>}{primaryResult && <ForecastChart result={primaryResult} origin={value.as_of} observations={[]} />}<details><summary>Assunzioni e provenienza</summary>{primaryResult?.assumptions.length ? <ul>{primaryResult.assumptions.map(a => <li key={a}>{a}</li>)}</ul> : <p>Assunzioni del modello non disponibili.</p>}<p>Emissione: {formatUtc(value.as_of)} · Grafo {value.graph_id} v{value.graph_version}</p><ul>{value.snapshot_ids.map(id => <li key={id}>Snapshot {id}</li>)}</ul>{value.snapshot_ids_truncated && <p>Elenco snapshot troncato.</p>}</details>{details?.graph ? <FutureGraph graph={details.graph} modifiedNodeIds={new Set()} /> : <p>Future Graph non disponibile.</p>}</section>;
}
