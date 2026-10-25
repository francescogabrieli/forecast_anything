"""Real installed entrypoint, point-in-time emissions and strict CSV boundary."""
import csv
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ['series_id', 'event_time', 'available_at', 'revision', 'value', 'unit']


def cli(*args):
    return subprocess.run(['forecast-anything', *map(str, args)], capture_output=True, text=True)


def test_cli_exposes_run_command():
    result = cli('run', '--help')
    assert result.returncode == 0
    assert '--as-of' in result.stdout and '--db' in result.stdout


def test_cli_two_emissions(tmp_path):
    graph = ROOT / 'examples/minimal/graph.json'
    data = tmp_path / 'data.csv'
    data.write_text('series_id,event_time,available_at,revision,value,unit\n'
        'demand,2026-10-21T00:00:00Z,2026-10-21T00:00:00Z,1,10,kWh\n'
        'demand,2026-10-22T00:00:00Z,2026-10-22T00:00:00Z,1,20,kWh\n'
        'demand,2026-10-23T00:00:00Z,2026-10-23T00:00:00Z,1,30,kWh\n'
        'demand,2026-10-23T00:00:00Z,2026-10-25T00:00:00Z,2,99,kWh\n')
    db = tmp_path / 'runs.db'
    def run(origin):
        result = cli('run', graph, '--data', data, '--as-of', origin, '--db', db)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    first = run('2026-10-24T00:00:00Z')
    assert first['state'] == 'completed'
    assert first['actual_provider'] == {'forecast': 'seasonal_naive'}
    assert first['results']['forecast']['point'] == [[20, 30, 20]]
    assert len(first['snapshot_ids']) == 1
    assert run('2026-10-24T02:00:00+02:00') == first
    second = run('2026-10-25T00:00:00Z')
    assert second['run_id'] != first['run_id']
    assert second['snapshot_ids'] != first['snapshot_ids']
    assert second['results']['forecast']['point'] == [[20, 99, 20]]
    shown = cli('show', first['run_id'], '--db', db)
    assert shown.returncode == 0
    assert json.loads(shown.stdout) == first


@pytest.mark.parametrize(('field', 'missing_header'), [
    (field, missing_header) for field in FIELDS for missing_header in [False, True]
    if field != 'value' or missing_header
])
def test_csv_missing_semantics(tmp_path, field, missing_header):
    from forecast_anything.connectors.csv import load_csv
    from forecast_anything.contracts import DomainError
    row = dict(zip(FIELDS, ['demand', '2026-10-23T00:00:00Z', '2026-10-23T00:00:00Z', '1', '1', 'kWh']))
    names = [name for name in FIELDS if name != field] if missing_header else FIELDS
    row[field] = ''
    path = tmp_path / 'bad.csv'
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=names, extrasaction='ignore')
        writer.writeheader()
        writer.writerow(row)
    with pytest.raises(DomainError):
        load_csv(path)


@pytest.mark.parametrize('replacement', ['NaN', 'Infinity', 'abc'])
def test_csv_rejects_invalid_values(tmp_path, replacement):
    from forecast_anything.connectors.csv import load_csv
    from forecast_anything.contracts import DomainError
    path = tmp_path / 'bad.csv'
    path.write_text(','.join(FIELDS) + '\ndemand,2026-10-23T00:00:00Z,2026-10-23T00:00:00Z,1,' + replacement + ',kWh\n')
    with pytest.raises(DomainError):
        load_csv(path)


def test_cli_errors_and_failed_run(tmp_path):
    graph = ROOT / 'examples/minimal/graph.json'
    data = tmp_path / 'data.csv'
    data.write_text(','.join(FIELDS) + '\ndemand,2026-10-23T00:00:00Z,2026-10-23T00:00:00Z,1,,kWh\n')
    args = ('run', graph, '--data', data, '--db', tmp_path / 'runs.db')
    invalid = cli(*args, '--as-of', '2026-10-24')
    assert invalid.returncode != 0
    assert json.loads(invalid.stderr)['code'] == 'naive_timestamp'
    failed = cli(*args, '--as-of', '2026-10-24T00:00:00Z')
    assert failed.returncode == 1
    assert json.loads(failed.stdout)['state'] == 'failed'
    missing = cli('show', 'absent', '--db', tmp_path / 'runs.db')
    assert missing.returncode != 0
    assert json.loads(missing.stderr)['code'] == 'not_found'
