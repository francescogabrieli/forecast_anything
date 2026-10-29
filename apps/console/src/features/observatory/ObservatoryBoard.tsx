import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiClient } from "../../api/client";
import type { EventRecord, EvaluationRecord, GraphSpec, RunRecord, ScenarioRequest, Snapshot, Watch } from "../../api/schema.generated";
import { DiscoveryFeed } from "./DiscoveryFeed";
import { FutureGraph } from "./FutureGraph";
import { RunDetails } from "./RunDetails";
import { ScenarioCompare } from "./ScenarioCompare";

type Props = { client: ApiClient; requestedRunId?: string; requestedRunVersion?: number };

function mergeEvents(current: EventRecord[], incoming: EventRecord[]): EventRecord[] {
  const byCursor = new Map<number, EventRecord>();
  for (const event of [...current, ...incoming]) if (!byCursor.has(event.cursor)) byCursor.set(event.cursor, event);
  return [...byCursor.values()].sort((left, right) => left.cursor - right.cursor);
}

function nodeIdsFromRunEvent(events: EventRecord[], runId: string): Set<string> {
  const event = [...events].reverse().find((item) => item.run_id === runId && item.kind === "run_completed");
  const ids = event?.payload.node_ids;
  return Array.isArray(ids) ? new Set(ids.filter((id): id is string => typeof id === "string")) : new Set();
}

function sourceBindings(events: EventRecord[], runId: string): Record<string, string> {
  const event = events.find((item) => item.run_id === runId && item.kind === "run_started");
  const bindings = event?.payload.source_bindings;
  if (!bindings || typeof bindings !== "object" || Array.isArray(bindings)) return {};
  return Object.fromEntries(Object.entries(bindings).filter((entry): entry is [string, string] => typeof entry[1] === "string"));
}

export function ObservatoryBoard({ client, requestedRunId, requestedRunVersion }: Props) {
  const [watches, setWatches] = useState<Watch[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [run, setRun] = useState<RunRecord>();
  const [graph, setGraph] = useState<GraphSpec>();
  const [evaluations, setEvaluations] = useState<EvaluationRecord[]>([]);
  const [evaluationsUnavailable, setEvaluationsUnavailable] = useState(false);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [watch, setWatch] = useState<Watch>();
  const [baseRun, setBaseRun] = useState<RunRecord>();
  const [baseGraph, setBaseGraph] = useState<GraphSpec>();
  const [error, setError] = useState<string>();
  const [status, setStatus] = useState<string>();
  const [scenarioLabel, setScenarioLabel] = useState("Scenario modificato");
  const [scenarioOverridesText, setScenarioOverridesText] = useState("{}");
  const [scenarioBusy, setScenarioBusy] = useState(false);
  const watchesRef = useRef<Watch[]>([]);
  const eventsRef = useRef<EventRecord[]>([]);
  const runRef = useRef<RunRecord | undefined>(undefined);
  const openRunVersion = useRef(0);
  watchesRef.current = watches;
  eventsRef.current = events;

  const refreshWatches = useCallback(async () => {
    const values = await client.getWatches();
    watchesRef.current = values;
    setWatches(values);
    if (runRef.current) setWatch(values.find((item) => item.graph_id === runRef.current?.graph_id));
  }, [client]);

  const openRun = useCallback(async (runId: string) => {
    const version = ++openRunVersion.current;
    setError(undefined);
    try {
      const loaded = await client.getRun(runId);
      if (version !== openRunVersion.current) return;
      const [loadedGraph, [evaluationRead], loadedSnapshots] = await Promise.all([
        client.getGraph(loaded.graph_id, loaded.graph_version),
        Promise.allSettled([client.getRunEvaluations(loaded.run_id)]),
        Promise.allSettled(loaded.snapshot_ids.map((id) => client.getSnapshot(id))),
      ]);
      if (version !== openRunVersion.current) return;
      const loadedEvaluations = evaluationRead.status === "fulfilled" ? evaluationRead.value : [];
      if (evaluationRead.status === "rejected") {
        setError(evaluationRead.reason instanceof Error
          ? `Non è stato possibile caricare le valutazioni: ${evaluationRead.reason.message}`
          : "Non è stato possibile caricare le valutazioni del run.");
      }
      const inputSnapshots = loadedSnapshots.flatMap((result) => result.status === "fulfilled" ? [result.value] : []);
      setSnapshots(inputSnapshots);
      setBaseRun(undefined);
      setBaseGraph(undefined);
      runRef.current = loaded;
      setRun(loaded);
      setGraph(loadedGraph);
      setEvaluations(loadedEvaluations);
      setEvaluationsUnavailable(evaluationRead.status === "rejected");
      const actualsIds = loadedEvaluations.map((evaluation) => evaluation.actuals_snapshot_id);
      const actualsSnapshots = await Promise.allSettled(actualsIds.filter((id) => !loaded.snapshot_ids.includes(id)).map((id) => client.getSnapshot(id)));
      if (version !== openRunVersion.current) return;
      setSnapshots([
        ...inputSnapshots,
        ...actualsSnapshots.flatMap((result) => result.status === "fulfilled" ? [result.value] : []),
      ]);
      const bindings = sourceBindings(eventsRef.current, loaded.run_id);
      const overrides = Object.fromEntries(Object.entries(bindings).flatMap(([sourceId, snapshotId]) => {
        const snapshot = inputSnapshots.find((item) => item.snapshot_id === snapshotId);
        return snapshot ? [[sourceId, snapshot]] : [];
      }));
      setScenarioOverridesText(JSON.stringify(overrides, null, 2));
      setWatch(watchesRef.current.find((item) => item.graph_id === loaded.graph_id));
      if (loaded.scenario_id && loaded.parent_run_id) {
        const parent = await client.getRun(loaded.parent_run_id);
        if (version !== openRunVersion.current) return;
        const parentGraph = await client.getGraph(parent.graph_id, parent.graph_version);
        if (version !== openRunVersion.current) return;
        setBaseRun(parent);
        setBaseGraph(parentGraph);
      }
    } catch (reason) {
      if (version === openRunVersion.current) setError(reason instanceof Error ? reason.message : "Non è stato possibile aprire il run.");
    }
  }, [client]);

  useEffect(() => () => { openRunVersion.current += 1; }, [client]);

  useEffect(() => {
    if (requestedRunId) void openRun(requestedRunId);
  }, [requestedRunId, requestedRunVersion, openRun]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    async function start() {
      try {
        const [initialWatches, initialEvents] = await Promise.all([client.getWatches(), client.getEvents(0, 1000)]);
        if (!active) return;
        watchesRef.current = initialWatches;
        setWatches(initialWatches);
        setEvents(mergeEvents([], initialEvents));
        const cursor = initialEvents.reduce((latest, item) => Math.max(latest, item.cursor), 0);
        void client.streamEvents(cursor, (event) => {
          if (!active) return;
          setEvents((current) => mergeEvents(current, [event]));
          if (event.kind === "run_completed") {
            void openRun(event.run_id);
            void refreshWatches().catch((reason: unknown) => {
              if (active) setError(reason instanceof Error ? reason.message : "Non è stato possibile aggiornare la sorveglianza.");
            });
          }
          if (event.kind.includes("watch")) void refreshWatches().catch(() => undefined);
        }, controller.signal).catch((reason: unknown) => {
          if (active && !controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Connessione agli eventi interrotta.");
        });
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Non è stato possibile caricare l’osservatorio.");
      }
    }
    void start();
    return () => { active = false; controller.abort(); };
  }, [client, openRun, refreshWatches]);

  async function createScenario(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!run) return;
    setError(undefined);
    setStatus(undefined);
    let sourceOverrides: ScenarioRequest["source_overrides"];
    try {
      sourceOverrides = JSON.parse(scenarioOverridesText) as ScenarioRequest["source_overrides"];
      if (!sourceOverrides || typeof sourceOverrides !== "object" || Array.isArray(sourceOverrides) || Object.keys(sourceOverrides).length === 0) throw new Error();
    } catch {
      setError("Inserisci una mappatura JSON di snapshot valida per lo scenario.");
      return;
    }
    setScenarioBusy(true);
    try {
      const scenario = await client.createScenario({
        base_graph_id: run.graph_id,
        base_version: run.graph_version,
        label: scenarioLabel.trim() || "Scenario",
        source_overrides: sourceOverrides,
      });
      setStatus("Scenario inviato al worker. Il run originale resta invariato.");
      for (let attempt = 0; attempt < 40; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        const job = await client.getJob(scenario.job_id);
        if (job.state === "failed") throw new Error("Il worker non è riuscito a calcolare lo scenario.");
        const runId = job.result?.run_id;
        if (job.state === "completed" && typeof runId === "string") {
          await openRun(runId);
          setStatus("Scenario pronto. Il confronto usa soltanto timestamp e unità comuni.");
          return;
        }
      }
      setStatus("Scenario in coda. Apri il run quando il worker ha terminato.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Non è stato possibile creare lo scenario.");
    } finally {
      setScenarioBusy(false);
    }
  }

  async function toggleWatch(value: Watch) {
    try {
      await client.updateWatch(value.watch_id, { muted: !value.muted });
      await refreshWatches();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Non è stato possibile aggiornare la sorveglianza.");
    }
  }

  return (
    <div className="observatory-board">
      {error && <p role="alert" className="error-message">{error}</p>}
      {status && <p role="status">{status}</p>}
      {(graph || run) && <div className="detail-grid">
        {graph && <FutureGraph graph={graph} modifiedNodeIds={run ? nodeIdsFromRunEvent(events, run.run_id) : new Set()} />}
        {run && <RunDetails graph={graph} sourceBindings={sourceBindings(events, run.run_id)} run={run} evaluations={evaluations} evaluationsUnavailable={evaluationsUnavailable} snapshots={snapshots} watch={watch} />}
      </div>}
      <DiscoveryFeed watches={watches} events={events} onSelectRun={(id) => void openRun(id)} onToggleWatch={(value) => void toggleWatch(value)} />
      {run && !run.scenario_id && <section className="scenario-builder" aria-labelledby="scenario-builder-title">
        <div><h2 id="scenario-builder-title">Prova uno scenario</h2><p className="muted">Modifica lo snapshot JSON; l’originale resta immutato. Le assunzioni dello scenario restano etichettate come ipotesi.</p></div>
        <form onSubmit={(event) => void createScenario(event)}>
          <label>Nome scenario<input value={scenarioLabel} onChange={(event) => setScenarioLabel(event.target.value)} /></label>
          <label>Snapshot ipotetici per fonte<textarea rows={10} spellCheck={false} value={scenarioOverridesText} onChange={(event) => setScenarioOverridesText(event.target.value)} /></label>
          <button type="submit" disabled={scenarioBusy || scenarioOverridesText === "{}"}>{scenarioBusy ? "Calcolo scenario…" : "Crea scenario"}</button>
        </form>
      </section>}
      {baseRun && baseGraph && run && graph && <ScenarioCompare baseRun={baseRun} scenarioRun={run} baseGraph={baseGraph} scenarioGraph={graph} />}
    </div>
  );
}
