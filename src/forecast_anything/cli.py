"""Local CSV-to-ledger CLI; stdout is a RunRecord, stderr structured errors."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

from pydantic import ValidationError

from .connectors.csv import load_csv
from .contracts import DomainError, GraphSpec
from .graph import SourceConfig, parse_node_config
from .providers.baseline import SeasonalNaiveProvider
from .runtime import Runtime
from .store import Ledger
from .temporal import freeze


def _run(args):
    origin = datetime.fromisoformat(args.as_of)
    if origin.tzinfo is None or origin.utcoffset() is None:
        raise DomainError('naive_timestamp', {'field': 'as_of'})
    origin = origin.astimezone(timezone.utc)
    spec = GraphSpec.model_validate_json(args.graph.read_text(encoding='utf-8'))
    sources = [parse_node_config(node) for node in spec.nodes if node.kind == 'source']
    # A single --data file has no source discriminator. Require one unambiguous
    # declared binding rather than silently assigning a file to several sources.
    if len(sources) != 1 or not isinstance(sources[0], SourceConfig):
        raise DomainError('ambiguous_csv_binding', {'reason': '--data requires exactly one source node'})
    snapshot = freeze(load_csv(args.data), origin)
    snapshots = {sources[0].source_id: snapshot}
    content = {'graph': spec.model_dump(mode='json'), 'as_of': origin.isoformat(),
               'snapshots': {name: value.model_dump(mode='json') for name, value in snapshots.items()}}
    key = sha256(json.dumps(content, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return Runtime(Ledger(args.db), {'seasonal_naive': SeasonalNaiveProvider(period=1)},
                   {}, lambda: datetime.now(timezone.utc)).run(spec, snapshots, origin, key)


def main() -> int:
    parser = argparse.ArgumentParser(prog='forecast-anything')
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='Freeze CSV observations and emit a forecast')
    run.add_argument('graph', type=Path)
    run.add_argument('--data', type=Path, required=True)
    run.add_argument('--as-of', required=True, help='ISO 8601 origin with timezone')
    run.add_argument('--db', type=Path, required=True)
    show = commands.add_parser('show', help='Read a stored immutable emission')
    show.add_argument('run_id')
    show.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()
    try:
        record = _run(args) if args.command == 'run' else Ledger(args.db).get_run(args.run_id)
        print(record.model_dump_json())
        return 0 if record.state == 'completed' else 1
    except DomainError as error:
        print(error.model_dump_json(), file=sys.stderr)
    except ValidationError as error:
        print(json.dumps({'code': 'validation_error', 'details': {
            'errors': error.errors(include_context=False, include_url=False)}}), file=sys.stderr)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps({'code': 'input_error', 'details': {'message': str(error)}}), file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
