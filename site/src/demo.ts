import record from '../demo-data.json';
import csv from '../../examples/release-demo/observations.csv?raw';

type Point = { time: string; value: number; unit: string };
type Partition = { partition: string; matched_count: number; model_mae: number; baseline_mae: number };

export const journey = record.journey;
export const forecast: Point = journey.forecast.forecast[0];
export const baseline: Point = journey.forecast.baseline_forecast[0];
export const cutoff = journey.forecast.as_of;
export const target = forecast.time;
export const update = journey.worker_update;
export const nextTarget = update.change_summary.added_targets[0].timestamp;
export const partitions: Partition[] = journey.historical_comparison.partitions;
export const day = (time: string) => time.slice(0, 10);
export const date = (time: string) => new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
}).format(new Date(time));
export const value = (n: number) => n.toFixed(3);

export const observed: Point[] = csv.trim().split(/\r?\n/).slice(1)
  .map(row => {
    const [time, value, published] = row.split(',');
    return { time, value: Number(value), published, unit: forecast.unit };
  })
  .filter(point => point.time <= day(cutoff) && point.published <= day(cutoff))
  .slice(-8);
