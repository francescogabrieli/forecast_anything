import { useEffect, useRef, useState } from "react";
import type { ApiClient } from "../../api/client";
import type { Candidate, JobView, Snapshot, SourceRegistration } from "../../api/schema.generated";
import { formatUtc } from "../../format";

type Client = Pick<ApiClient, "getJob" | "getCandidate" | "getSnapshot" | "submitRun" | "getRun" | "refreshSource">;
type Props = { client: Client; registration: SourceRegistration; onRunReady: (runId: string) => void };
type Ready = { candidate: Candidate; snapshot: Snapshot; provider: string };
type Issued = { runId: string; series: string; value: number; unit: string; timestamp: string };

class FailedJobError extends Error {}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException("Aborted", "AbortError")); return; }
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, ms);
    function abort() { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); }
    signal.addEventListener("abort", abort, { once: true });
  });
}

async function completedJob(client: Client, jobId: string, signal: AbortSignal): Promise<JobView> {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    const job = await client.getJob(jobId);
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    if (job.state === "completed") return job;
    if (job.state === "failed") throw new FailedJobError("Il calcolo non è riuscito. Riprova.");
    await wait(500, signal);
  }
  throw new Error("Il calcolo richiede più tempo del previsto. Riprova più tardi.");
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : [];
}

function requestKey(prefix: string): string {
  const id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${id}`;
}

function targetIsFuture(candidate: Candidate, snapshot: Snapshot, sourceId: string): boolean {
  const forecast = candidate.graph.nodes.find((node) => node.node_id === "forecast" && node.kind === "forecast");
  const source = candidate.graph.nodes.find((node) => node.node_id === forecast?.config.history && node.kind === "source");
  const series = stringArray(source?.config.series_ids);
  const frequency = typeof forecast?.config.frequency === "string" ? /^(\d+)([hd])$/.exec(forecast.config.frequency) : null;
  const asOf = Date.parse(snapshot.as_of);
  const now = Date.now();
  if (!forecast || !source || source.config.source_id !== sourceId || !series.length || !frequency || !Number.isFinite(asOf)) return false;
  const amount = Number(frequency[1]);
  if (!Number.isSafeInteger(amount) || amount <= 0) return false;
  const step = amount * (frequency[2] === "d" ? 86_400_000 : 3_600_000);
  return series.every((id) => {
    const times = snapshot.observations.filter((observation) => observation.series_id === id).map((observation) => Date.parse(observation.event_time));
    if (!times.length || times.some((time) => !Number.isFinite(time))) return false;
    const latest = times.reduce((current, time) => Math.max(current, time), -Infinity);
    return latest <= asOf && latest + step > Math.max(asOf, now);
  });
}

export function FirstForecast({ client, registration, onRunReady }: Props) {
  const [currentRegistration, setCurrentRegistration] = useState(registration);
  const [ready, setReady] = useState<Ready>();
  const [status, setStatus] = useState("Cerco una proposta per questa fonte…");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const [canRefresh, setCanRefresh] = useState(false);
  const [issuedForecast, setIssuedForecast] = useState<Issued>();
  const active = useRef<AbortController | undefined>(undefined);
  const refreshKey = useRef<string | undefined>(undefined);
  const runKey = useRef<string | undefined>(undefined);

  useEffect(() => {
    setCurrentRegistration(registration);
  }, [registration.job_id, registration.epoch_id, registration.source_id, registration.revision]);

  useEffect(() => {
    const controller = new AbortController();
    active.current = controller;
    runKey.current = undefined;
    setReady(undefined);
    setIssuedForecast(undefined);
    setError(undefined);
    setBusy(false);
    setCanRefresh(false);
    setStatus("Cerco una proposta per questa fonte…");
    async function prepare() {
      try {
        const job = await completedJob(client, currentRegistration.job_id, controller.signal);
        setCanRefresh(true);
        const ids = stringArray(job.result?.candidate_ids);
        const snapshotIds = stringArray(job.result?.source_snapshot_ids);
        if (snapshotIds.length !== 1) { setStatus("Nessun dato pronto per questa fonte."); return; }
        const [snapshot, candidates] = await Promise.all([
          client.getSnapshot(snapshotIds[0]),
          Promise.all(ids.map((id) => client.getCandidate(id))),
        ]);
        if (controller.signal.aborted) return;
        const candidate = candidates.find((item) => item.template_id === "expected_deviation" && item.executable === true
          && item.epoch_id === currentRegistration.epoch_id && item.source_ids.length === 1 && item.source_ids[0] === currentRegistration.source_id
          && item.graph.nodes.some((node) => node.node_id === "forecast" && node.kind === "forecast" && typeof node.config.provider === "string" && node.config.horizon === 1));
        if (!candidate || snapshot.snapshot_id !== snapshotIds[0]) { setStatus("Non è disponibile una previsione per questa fonte."); return; }
        if (!targetIsFuture(candidate, snapshot, currentRegistration.source_id)) { setStatus("Dati troppo vecchi per una previsione futura: aggiorna la fonte e controlla l’orologio del dispositivo."); return; }
        const provider = candidate.graph.nodes.find((node) => node.node_id === "forecast")!.config.provider as string;
        setReady({ candidate, snapshot, provider });
        setStatus("Proposta pronta.");
      } catch (reason) {
        if (!controller.signal.aborted) {
          setStatus("Non è stato possibile preparare la previsione.");
          setCanRefresh(true);
          setError(reason instanceof Error ? reason.message : "Riprova più tardi.");
        }
      }
    }
    void prepare();
    return () => controller.abort();
  }, [client, currentRegistration.job_id, currentRegistration.epoch_id, currentRegistration.source_id, retry]);

  async function refresh() {
    if (busy || !active.current) return;
    const signal = active.current.signal;
    setBusy(true);
    setError(undefined);
    setStatus("Aggiornamento dei dati in corso…");
    try {
      const key = refreshKey.current ?? (refreshKey.current = requestKey("source-refresh"));
      const updated = await client.refreshSource(currentRegistration.source_id, key);
      if (signal.aborted) return;
      if (updated.source_id !== currentRegistration.source_id) throw new Error("Non è stato possibile aggiornare questa fonte.");
      refreshKey.current = undefined;
      setCurrentRegistration(updated);
    } catch (reason) {
      if (!signal.aborted) {
        setStatus("I dati non sono stati aggiornati.");
        setError(reason instanceof Error ? reason.message : "Riprova più tardi.");
      }
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  async function calculate() {
    if (!ready || busy || !active.current) return;
    const signal = active.current.signal;
    if (!targetIsFuture(ready.candidate, ready.snapshot, currentRegistration.source_id)) {
      setReady(undefined);
      setStatus("Dati troppo vecchi per una previsione futura: aggiorna la fonte e controlla l’orologio del dispositivo.");
      return;
    }
    setBusy(true);
    setError(undefined);
    setStatus("Calcolo della previsione in corso…");
    try {
      const submitted = await client.submitRun({
        kind: "run", key: runKey.current ?? (runKey.current = requestKey("first-forecast")), graph: ready.candidate.graph,
        snapshot_ids: { [currentRegistration.source_id]: ready.snapshot.snapshot_id }, as_of: ready.snapshot.as_of,
      });
      const finished = await completedJob(client, submitted.job_id, signal);
      const runId = finished.result?.run_id;
      if (typeof runId !== "string") throw new Error("Non è stato possibile registrare la previsione.");
      const run = await client.getRun(runId);
      if (signal.aborted) return;
      const forecast = run.results.forecast;
      const issued = Date.parse(run.as_of);
      const value = forecast?.point?.[0]?.[0];
      if (run.run_id !== runId || run.state !== "completed" || run.graph_id !== ready.candidate.graph.graph_id
        || !run.snapshot_ids.includes(ready.snapshot.snapshot_id) || issued !== Date.parse(ready.snapshot.as_of)
        || forecast?.provider_id !== ready.provider || forecast.series_ids.length !== 1 || forecast.units.length !== 1
        || forecast.timestamps.length !== 1 || forecast.point?.length !== 1 || forecast.point[0]?.length !== 1
        || typeof value !== "number" || !Number.isFinite(value) || !Number.isFinite(issued)
        || forecast.timestamps.some((time) => !Number.isFinite(Date.parse(time)) || Date.parse(time) <= Math.max(issued, Date.now()))) {
        throw new Error("Il calcolo non ha prodotto una previsione futura verificabile.");
      }
      setIssuedForecast({ runId, series: forecast.series_ids[0], value, unit: forecast.units[0], timestamp: forecast.timestamps[0] });
      setStatus("Previsione pronta: il dettaglio è nell’osservatorio qui sotto.");
      onRunReady(runId);
    } catch (reason) {
      if (!signal.aborted) {
        if (reason instanceof FailedJobError) runKey.current = undefined;
        setStatus("La previsione non è stata completata.");
        setError(reason instanceof Error ? reason.message : "Riprova più tardi.");
      }
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  return <section className="first-forecast" aria-labelledby="first-forecast-title">
    <div>
      <h2 id="first-forecast-title">La prima previsione</h2>
      <p>Una stima iniziale per il prossimo intervallo, calcolata dal modello indicato nella proposta. È provvisoria e non ancora valutata sui dati reali.</p>
      {ready && <p>Modello: {ready.provider}</p>}
      {ready && <p className="first-forecast-meta">Fonte {currentRegistration.source_id} · dati disponibili al {formatUtc(ready.snapshot.as_of)}</p>}
      {issuedForecast && <div className="first-forecast-result" role="group" aria-label="Previsione iniziale">
        <p className="first-forecast-value"><strong>{issuedForecast.value}</strong> {issuedForecast.unit}</p>
        <p>{issuedForecast.series} · {formatUtc(issuedForecast.timestamp)}</p>
      </div>}
    </div>
    <div className="first-forecast-action">
      <p role="status">{status}</p>
      {error && <p role="alert">{error}</p>}
      {!ready && error && <button type="button" className="button button-dark" onClick={() => setRetry((value) => value + 1)}>Riprova</button>}
      {ready && !issuedForecast && <button type="button" className="button button-dark" onClick={() => void calculate()} disabled={busy}>{busy ? "Calcolo in corso…" : "Calcola la prima previsione"}</button>}
      {canRefresh && <button type="button" className="first-forecast-refresh" onClick={() => void refresh()} disabled={busy}>Aggiorna dati</button>}
      {issuedForecast && <a href="#run-details-title" onClick={(event) => { event.preventDefault(); onRunReady(issuedForecast.runId); }}>Vai al dettaglio</a>}
    </div>
  </section>;
}
