import { useEffect, useState } from "react";
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
    const readyIndex = remaining.findIndex((node) =>
      node.inputs.every((input) => !known.has(input) || placed.has(input)),
    );
    const [next] = remaining.splice(readyIndex < 0 ? 0 : readyIndex, 1);
    ordered.push(next);
    placed.add(next.node_id);
  }
  return ordered;
}

export function FutureGraph({ graph, modifiedNodeIds, onSelectNode }: Props) {
  const [selectedNodeId, setSelectedNodeId] = useState<string>();
  useEffect(
    () => setSelectedNodeId(undefined),
    [graph.graph_id, graph.version],
  );
  const nodes = topologicalOrder(graph.nodes);
  // Group dependencies by depth. Sources on the same level never imply an edge.
  const levels = new Map<string, number>();
  const rows: Node[][] = [];
  for (const node of nodes) {
    const level =
      Math.max(-1, ...node.inputs.map((id) => levels.get(id) ?? -1)) + 1;
    levels.set(node.node_id, level);
    (rows[level] ??= []).push(node);
  }
  const nodeStep = 148;
  const width = Math.max(210, ...rows.map((row) => row.length * nodeStep));
  const height = Math.max(98, rows.length * 98);
  const nodePositions = new Map(
    rows.flatMap((row, level) =>
      row.map(
        (node, i) =>
          [
            node.node_id,
            {
              x: width / 2 + (i - (row.length - 1) / 2) * nodeStep,
              y: 56 + level * 98,
            },
          ] as const,
      ),
    ),
  );
  const selected = nodes.find((node) => node.node_id === selectedNodeId);

  function select(nodeId: string) {
    setSelectedNodeId(nodeId);
    onSelectNode?.(nodeId);
  }

  return (
    <section className="graph-card" aria-labelledby="future-graph-title">
      <div className="section-heading">
        <div>
          <h2 id="future-graph-title">Come si compone il futuro</h2>
        </div>
        <span className="graph-version">v{graph.version}</span>
      </div>
      <p className="muted">
        Dalle fonti al risultato, in ordine di dipendenza.
      </p>
      <div className="graph-scroll" tabIndex={0} aria-label="Grafo navigabile">
        <svg
          role="group"
          aria-label="Grafo del futuro"
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
        >
          {rows.map((row, level) => {
            const kinds = [...new Set(row.map((node) => node.kind))];
            const group =
              kinds.length !== 1
                ? "Passaggio"
                : (
                    {
                      source: "Fonti",
                      forecast: "Previsioni",
                      transform: "Trasformazioni",
                      event: "Eventi",
                    } as const
                  )[kinds[0]];
            return (
              <text
                className="graph-level"
                key={level}
                x="14"
                y={14 + level * 98}
              >
                {String(level + 1).padStart(2, "0")} · {group}
              </text>
            );
          })}
          {nodes.flatMap((node) =>
            node.inputs.map((input) => {
              const from = nodePositions.get(input);
              const to = nodePositions.get(node.node_id);
              return from && to ? (
                <line
                  key={`${input}-${node.node_id}`}
                  className={
                    selectedNodeId === input || selectedNodeId === node.node_id
                      ? "graph-edge selected-edge"
                      : "graph-edge"
                  }
                  x1={from.x}
                  y1={from.y + 35}
                  x2={to.x}
                  y2={to.y - 35}
                />
              ) : null;
            }),
          )}
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
                aria-pressed={selectedNodeId === node.node_id}
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
                <text className="graph-kind" x="12" y="22">
                  {kindLabels[node.kind]}
                </text>
                <title>{node.node_id}</title>
                <text className="graph-name" x="12" y="43">
                  {node.node_id.length > 13
                    ? node.node_id.slice(0, 12) + "…"
                    : node.node_id}
                </text>
                {modified && (
                  <text className="graph-change" x="12" y="60">
                    Modificato
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      <p className="graph-order">
        Le righe mostrano i livelli; i collegamenti indicano gli input di ogni
        nodo.
      </p>
      {selected && (
        <p className="node-selection" role="status">
          <strong>Selezionato: {selected.node_id}</strong>
          <br />
          {selected.inputs.length
            ? "Input: " + selected.inputs.join(", ")
            : "Nessun nodo a monte."}
        </p>
      )}
    </section>
  );
}
