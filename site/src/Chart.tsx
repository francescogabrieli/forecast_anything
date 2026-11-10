import { baseline, cutoff, date, day, forecast, observed, target, value } from './demo';

export function Plot({ compact = false, preview = false }: { compact?: boolean; preview?: boolean }) {
  const width = compact ? 316 : 760;
  const height = preview ? 146 : compact ? 213 : 286;
  const left = compact ? 27 : 38;
  const right = width - 12;
  const bottom = height - 39;
  const top = 47;
  const suffix = preview ? 'preview' : compact ? 'small' : 'wide';
  const start = Date.parse(observed[0].time);
  const last = Date.parse(day(target));
  const x = (time: string) => left + (Date.parse(day(time)) - start) / (last - start) * (right - left - (compact ? 26 : 58));
  const y = (orders: number) => bottom - orders / 4 * (bottom - top);
  const cutoffX = x(cutoff);
  const targetX = x(target);

  return <svg className={preview ? 'chart-preview' : compact ? 'chart-small' : 'chart-wide'} viewBox={`0 0 ${width} ${height}`}
    role="img" aria-labelledby={`chart-title-${suffix} chart-desc-${suffix}`} data-forecast-chart>
    <title id={`chart-title-${suffix}`}>Daily orders at the forecast cutoff</title>
    <desc id={`chart-desc-${suffix}`}>
      {observed.length} observed daily values, {observed.map(point => point.value).join(', ')} orders, through {date(cutoff)} UTC.
      For {date(target)}, Timestral predicts {value(forecast.value)} orders and the seasonal baseline predicts {value(baseline.value)} orders.
    </desc>
    <text x={left} y="19" className="chart-unit">Orders</text>
    <rect x={cutoffX} y="29" width={right - cutoffX} height={bottom - 29} className="target-band" />
    {[0, 1, 2, 3, 4].map(tick => <g key={tick}>
      <line x1={left} y1={y(tick)} x2={right} y2={y(tick)} className={tick === 0 ? 'axis-rule' : 'chart-rule'} />
      <text x={left - 9} y={y(tick) + 4} textAnchor="end">{tick}</text>
    </g>)}
    <line x1={cutoffX} y1="29" x2={cutoffX} y2={bottom} className="cutoff-rule" />
    <text id={preview ? 'hero-cutoff' : compact ? undefined : 'cutoff-label'} x={cutoffX - 6} y="19" textAnchor="end" className="cutoff-label">
      {compact ? `${date(cutoff).slice(0, -5)} · cutoff` : `${date(cutoff)} · cutoff`}
    </text>
    <line x1={targetX} y1={top} x2={targetX} y2={bottom} className="target-rule" />
    <g data-series="observed">
      <polyline points={observed.map(point => `${x(point.time)},${y(point.value)}`).join(' ')} className="observed-line" />
      {observed.map(point => <circle key={point.time} cx={x(point.time)} cy={y(point.value)} r="3" />)}
    </g>
    <path data-series="seasonal" d={`M ${targetX} ${y(baseline.value) - 6} l 6 6 l -6 6 l -6 -6 Z`} className="baseline-point" />
    <circle data-series="timestral" cx={targetX} cy={y(forecast.value)} r="6" className="forecast-point" />
    <text x={left} y={bottom + 23}>{date(observed[0].time).slice(0, -5)}</text>
    {!compact && <text x={x(observed[4].time)} y={bottom + 23} textAnchor="middle">{date(observed[4].time).slice(0, -5)}</text>}
    <text x={targetX} y={bottom + 23} textAnchor="middle" className="target-label">{preview ? date(target) : date(target).slice(0, -5)}</text>
  </svg>;
}

export function Chart() {
  return <figure className="min-w-0 md:col-span-4 lg:col-span-8">
    <div className="chart-frame">
      <Plot />
      <Plot compact />
    </div>
    <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
      <span className="legend"><i className="legend-line" />Observed</span>
      <span className="legend"><i className="legend-dot" />Timestral</span>
      <span className="legend"><i className="legend-diamond" />Seasonal baseline</span>
      <span className="ml-auto hidden sm:inline">Daily buckets · UTC</span>
    </figcaption>
  </figure>;
}
