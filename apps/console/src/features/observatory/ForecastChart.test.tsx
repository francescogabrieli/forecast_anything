import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { makeRun } from '../../test/fixtures';
import { ForecastChart } from './ForecastChart';
import { RunDetails } from './RunDetails';

it('keeps missing observations as gaps and excludes incompatible or future observations', () => {
  const observation = (event_time: string, value: number | null, unit = 'count', series_id = 'sales') => ({event_time, value, unit, series_id, available_at: '2026-10-20T00:00:00Z', revision: '1'});
  const { container } = render(<ForecastChart result={makeRun().results.forecast} origin={makeRun().as_of} observations={[observation('2026-10-20', 3), observation('2026-10-21', null), observation('2026-10-22', 5), observation('2026-10-23', 8, 'EUR'), observation('2026-10-23', 9, 'count', 'other'), observation('2026-10-25', 10)]} />);
  const chart = screen.getByRole('img', {name: /sales.*count/i});
  expect(chart).toHaveTextContent('Data (UTC)');
  expect(chart).toHaveTextContent('Origine');
  expect(chart.querySelectorAll('[data-observation]').length).toBe(0);
  expect(chart.querySelector('[data-observed-path]')?.getAttribute('d')?.match(/M/g)).toHaveLength(2);
  expect(container.querySelector('[data-uncertainty]')).toBeNull();
});

it('uses rounded whole-count ticks and leaves headroom above the largest value', () => {
  const run = makeRun();
  run.results.forecast.point = [[0, 3]];
  const { container } = render(<RunDetails run={run} evaluations={[]} />);
  const ticks = [...container.querySelectorAll('[data-y-tick]')].map(tick => tick.textContent);
  expect(ticks).toEqual(['0', '2', '4']);
});
