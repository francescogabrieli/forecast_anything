import type { GraphSpec, RunRecord } from "../../api/schema.generated";

type Props = {
  baseRun: RunRecord;
  scenarioRun: RunRecord;
  baseGraph: GraphSpec;
  scenarioGraph: GraphSpec;
};

type ComparisonRow = { nodeId: string; seriesId: string; timestamp: string; base: number; scenario: number; delta: number; unit: string };

function comparePointValues(baseRun: RunRecord, scenarioRun: RunRecord, baseGraph: GraphSpec, scenarioGraph: GraphSpec): ComparisonRow[] {
  const baseForecasts = new Set(baseGraph.nodes.filter((node) => node.kind === "forecast").map((node) => node.node_id));
  const scenarioForecasts = new Set(scenarioGraph.nodes.filter((node) => node.kind === "forecast").map((node) => node.node_id));
  const rows: ComparisonRow[] = [];
  for (const nodeId of baseForecasts) {
    if (!scenarioForecasts.has(nodeId)) continue;
    const base = baseRun.results[nodeId];
    const scenario = scenarioRun.results[nodeId];
    if (!base?.point || !scenario?.point) continue;
    const scenarioTimeIndex = new Map(scenario.timestamps.map((timestamp, index) => [timestamp, index]));
    const scenarioSeriesIndex = new Map(scenario.series_ids.map((seriesId, index) => [seriesId, index]));
    base.series_ids.forEach((seriesId, baseSeriesIndex) => {
      const scenarioSeries = scenarioSeriesIndex.get(seriesId);
      if (scenarioSeries === undefined || base.units[baseSeriesIndex] !== scenario.units[scenarioSeries]) return;
      base.timestamps.forEach((timestamp, baseTimeIndex) => {
        const scenarioTime = scenarioTimeIndex.get(timestamp);
        const baseValue = base.point?.[baseSeriesIndex]?.[baseTimeIndex];
        const scenarioValue = scenarioTime === undefined ? undefined : scenario.point?.[scenarioSeries]?.[scenarioTime];
        if (baseValue === undefined || scenarioValue === undefined) return;
        rows.push({ nodeId, seriesId, timestamp, base: baseValue, scenario: scenarioValue, delta: scenarioValue - baseValue, unit: base.units[baseSeriesIndex] });
      });
    });
  }
  return rows;
}

export function ScenarioCompare({ baseRun, scenarioRun, baseGraph, scenarioGraph }: Props) {
  const rows = comparePointValues(baseRun, scenarioRun, baseGraph, scenarioGraph);
  const baseAssumptions = Object.entries(baseRun.results).flatMap(([nodeId, result]) => result.assumptions.map((assumption) => ({ nodeId, assumption })));
  const scenarioAssumptions = Object.entries(scenarioRun.results).flatMap(([nodeId, result]) => result.assumptions.map((assumption) => ({ nodeId, assumption })));

  return (
    <section className="scenario-card" aria-labelledby="scenario-compare-title">
      <div className="section-heading"><div><h2 id="scenario-compare-title">Confronto sulle date comuni</h2></div><span className="scenario-id">{scenarioRun.scenario_id ?? "scenario"}</span></div>
      <p className="muted">Confronto puntuale tra {baseRun.run_id} e {scenarioRun.run_id}. Quantili e probabilità restano quelli registrati dai rispettivi run.</p>
      {rows.length === 0 ? <p className="muted">Nessun valore puntuale con serie, unità e timestamp comuni.</p> : <div className="table-scroll"><table><caption>Valori puntuali sui timestamp comuni</caption><thead><tr><th>Previsione</th><th>Serie</th><th>Timestamp</th><th>Base</th><th>Scenario</th><th>Differenza</th></tr></thead><tbody>
        {rows.map((row) => <tr key={`${row.nodeId}-${row.seriesId}-${row.timestamp}`}><td>{row.nodeId}</td><td>{row.seriesId} ({row.unit})</td><td>{new Date(row.timestamp).toLocaleDateString("it-IT")}</td><td>{row.base}</td><td>{row.scenario}</td><td>{row.delta > 0 ? "+" : ""}{row.delta}</td></tr>)}
      </tbody></table></div>}
      <div className="assumption-columns">
        <section><h3>Assunzioni — base</h3>{baseAssumptions.length === 0 ? <p className="muted">Nessuna assunzione registrata.</p> : <ul>{baseAssumptions.map(({ nodeId, assumption }) => <li key={`${nodeId}-${assumption}`}><span>{nodeId}</span>{assumption}</li>)}</ul>}</section>
        <section><h3>Assunzioni — scenario</h3>{scenarioAssumptions.length === 0 ? <p className="muted">Nessuna assunzione registrata.</p> : <ul>{scenarioAssumptions.map(({ nodeId, assumption }) => <li key={`${nodeId}-${assumption}`}><span>{nodeId}</span>{assumption}</li>)}</ul>}</section>
      </div>
    </section>
  );
}
