"""Run one included domain example through the shared Forecast Anything core."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from forecast_anything.connectors.csv import load_csv
from forecast_anything.contracts import GraphSpec
from forecast_anything.operators import register_builtin_operators
from forecast_anything.providers.baseline import SeasonalNaiveProvider
from forecast_anything.runtime import Runtime
from forecast_anything.store import Ledger
from forecast_anything.temporal import freeze

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = {name: ROOT / "examples" / name for name in ("retail", "energy", "activity")}


def run_example(name: str, database: Path):
    """Load a graph, observations, and declared assumptions; persist one run."""
    if name not in EXAMPLES:
        raise ValueError(f"unknown example {name!r}; choose {', '.join(EXAMPLES)}")
    directory = EXAMPLES[name]
    manifest = json.loads((directory / "assumptions.json").read_text(encoding="utf-8"))
    as_of = datetime.fromisoformat(manifest["as_of"].replace("Z", "+00:00"))
    graph = GraphSpec.model_validate_json((directory / "graph.json").read_text(encoding="utf-8"))
    observations = load_csv(directory / "observations.csv")
    source_nodes = [node for node in graph.nodes if node.kind == "source"]
    if len(source_nodes) != 1:
        raise ValueError("included examples require exactly one source node")
    source_id = source_nodes[0].config.get("source_id")
    if not isinstance(source_id, str):
        raise ValueError("example source node must declare source_id")
    snapshot = freeze(observations, as_of, tuple(manifest.get("assumptions", ())))
    snapshots = {source_id: snapshot}
    identity = json.dumps(
        {
            "graph": graph.model_dump(mode="json"),
            "snapshots": {source_id: snapshot.model_dump(mode="json")},
            "as_of": as_of.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    key = hashlib.sha256(identity.encode()).hexdigest()
    ledger = Ledger(database, clock=lambda: as_of)
    runtime = Runtime(
        ledger,
        {"seasonal_naive": SeasonalNaiveProvider(period=1)},
        register_builtin_operators(),
        lambda: as_of,
    )
    return runtime.run(graph, snapshots, as_of, key)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", choices=tuple(EXAMPLES))
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    result = run_example(args.example, args.db)
    print(result.model_dump_json(indent=2))
    return 0 if result.state == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
