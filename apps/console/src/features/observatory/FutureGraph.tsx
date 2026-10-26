import { useState } from "react";
import type { GraphSpec, Node } from "../../api/schema.generated";

type Props = {
  graph: GraphSpec;
  modifiedNodeIds: ReadonlySet<string>;
  onSelectNode?: (nodeId: string) => void;
};

const kindLabels: Record<Node["kind"], string> = {
  source: "Fonte",
  forecast: "Previsione",
  transform: "Trasformazione",
  event: "Evento",
};

function topologicalOrder(nodes: Node[]): Node[] {
  const remaining = [...nodes];
  const known = new Set(nodes.map((node) => node.node_id));
  const placed = new Set<string>();
  const ordered: Node[] = [];
  while (remaining.length > 0) {
    const readyIndex = remaining.findIndex((node) => node.inputs.every((input) => !known.has(input) || placed.has(input)));
    const [next] = remaining.splice(readyIndex < 0 ? 0 : readyIndex, 1);
    ordered.push(next);
    placed.add(next.node_id);
  }
  return ordered;
}

export function FutureGraph({ graph, modifiedNodeIds, onSelectNode }: Props) {
  const [selectedNodeId, setSelectedNodeId] = useState<string>();
  const nodes = topologicalOrder(graph.nodes);
  const nodePositions = new Map(nodes.map((node, index) => [node.node_id, { x: 92 + index * 172, y: 104 }]));
  const width = Math.max(340, 184 * nodes.length);
  const selected = nodes.find((node) => node.node_id === selectedNodeId);

  function select(nodeId: string) {
    setSelectedNodeId(nodeId);
    onSelectNode?.(nodeId);
  }

  return (
    <section className="graph-card" aria-labelledby="future-graph-title">
      <div className="section-heading"><div><p className="kicker">FUTURE GRAPH</p><h2 id="future-graph-title">Come si compone il futuro</h2></div><span className="graph-version">v{graph.version}</span></div>
      <p className="muted">Le etichette indicano fonti, previsioni, trasformazioni ed eventi.</p>
      <div className="graph-scroll" tabIndex={0} aria-label="Grafo navigabile">
        <svg role="img" aria-label="Grafo del futuro" viewBox={`0 0 ${width} 208`} width={width} height="208">
          {nodes.flatMap((node) => node.inputs.map((input) => {
            const from = nodePositions.get(input);
            const to = nodePositions.get(node.node_id);
            return from && to ? <line key={`${input}-${node.node_id}`} className="graph-edge" x1={from.x + 52} y1={from.y} x2={to.x - 58} y2={to.y} /> : null;
          }))}
          {nodes.map((node) => {
            const position = nodePositions.get(node.node_id)!;
            const modified = modifiedNodeIds.has(node.node_id);
            return (
              <g
                key={node.node_id}
                className={`graph-node graph-node-${node.kind}${modified ? " is-modified" : ""}`}
                data-node-id={node.node_id}
                data-modified={String(modified)}
                role="button"
                tabIndex={0}
                aria-label={`${node.node_id}, ${kindLabels[node.kind].toLowerCase()}${modified ? ", modificato" : ""}`}
                transform={`translate(${position.x - 57} ${position.y - 35})`}
                onClick={() => select(node.node_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    select(node.node_id);
                  }
                }}
              >
                <rect width="114" height="70" rx="11" />
                <text className="graph-kind" x="12" y="22">{kindLabels[node.kind]}</text>
                <text className="graph-name" x="12" y="43">{node.node_id}</text>
                {modified && <text className="graph-change" x="12" y="60">Modificato</text>}
              </g>
            );
          })}
        </svg>
      </div>
      <p className="graph-order"><span>Ordine dipendenze</span> {nodes.map((node) => kindLabels[node.kind].toLowerCase()).join(" → ")}</p>
      {selected && <p className="node-selection" role="status">Selezionato: {selected.node_id} · {kindLabels[selected.kind].toLowerCase()}</p>}
    </section>
  );
}
