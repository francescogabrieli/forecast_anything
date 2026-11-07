import { useLayoutEffect, useRef, useState } from "react";
import type { ForecastResult, Snapshot } from "../../api/schema.generated";
import { formatUtc } from "../../format";
import "./results.css";

type Datum = { time: number; value: number | null };
export function ForecastChart({
  result,
  origin,
  observations,
}: {
  result: ForecastResult;
  origin: string;
  observations: Snapshot["observations"];
}) {
  return (
    <div className="forecast-charts">
      {result.series_ids.map((series, index) => (
        <SeriesChart
          key={series + index}
          {...{ result, origin, observations, series, index }}
        />
      ))}
    </div>
  );
}

function SeriesChart({
  result,
  origin,
  observations,
  series,
  index,
}: {
  result: ForecastResult;
  origin: string;
  observations: Snapshot["observations"];
  series: string;
  index: number;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [width, setWidth] = useState(500);
  useLayoutEffect(() => {
    const svg = ref.current;
    if (!svg || !window.ResizeObserver) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0)
        setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(svg);
    return () => observer.disconnect();
  }, []);
  const originTime = Date.parse(origin);
  const unit = result.units[index];
  const history = observations
    .filter(
      (o) =>
        o.series_id === series &&
        o.unit === unit &&
        Date.parse(o.event_time) <= originTime &&
        Date.parse(o.available_at) <= originTime,
    )
    .sort((a, b) => Date.parse(a.event_time) - Date.parse(b.event_time));
  const observed: Datum[] = history.map((o) => ({
    time: Date.parse(o.event_time),
    value: o.value,
  }));
  const forecast: Datum[] = result.timestamps.map((time, i) => ({
    time: Date.parse(time),
    value: result.point?.[index]?.[i] ?? null,
  }));
  const all = [...observed, ...forecast];
  const times = [originTime, ...all.map((d) => d.time)].filter(Number.isFinite);
  const values = all.flatMap((d) =>
    d.value !== null && Number.isFinite(d.value) ? [d.value] : [],
  );
  const minTime = Math.min(...times),
    maxTime = Math.max(...times);
  const minimum = Math.min(...values, 0),
    maximum = Math.max(...values, 0);
  const rawStep = (maximum - minimum || 1) / 2;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const fraction = rawStep / magnitude;
  const step =
    (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10) *
    magnitude;
  const low = Math.floor(minimum / step) * step;
  const high = (Math.floor(maximum / step) + 1) * step;
  const ticks = Array.from(
    { length: Math.round((high - low) / step) + 1 },
    (_, i) => low + i * step,
  );
  const x = (time: number) =>
    32 + ((time - minTime) / (maxTime - minTime || 1)) * (width - 72);
  const y = (value: number) => 142 - ((value - low) / (high - low || 1)) * 118;
  const path = (data: Datum[]) => {
    let connected = false;
    return data
      .map((d) => {
        if (
          d.value === null ||
          !Number.isFinite(d.value) ||
          !Number.isFinite(d.time)
        ) {
          connected = false;
          return "";
        }
        const command = connected ? "L" : "M";
        connected = true;
        return `${command}${x(d.time)},${y(d.value)}`;
      })
      .join(" ");
  };
  return (
    <figure className="forecast-chart" key={`${series}-${index}`}>
      <figcaption>
        <span>
          {series} · {unit}
        </span>
        <span className="chart-key">
          <span>Osservato</span>
          <span>Previsto</span>
        </span>
      </figcaption>
      <svg
        ref={ref}
        role="img"
        aria-label={`${series} · ${unit}: osservazioni e previsione`}
        viewBox={`0 0 ${width} 181`}
      >
        <title>
          {series} · {unit}: osservazioni e previsione
        </title>
        <desc>
          Data (UTC). Osservazioni registrate prima dell'origine; previsione
          puntuale dopo l'origine. I valori mancanti interrompono la linea.
          Valori disponibili nella tabella.
        </desc>
        {ticks.map((value) => (
          <g key={value}>
            <line
              x1="32"
              x2={width - 28}
              y1={y(value)}
              y2={y(value)}
              stroke="var(--line)"
            />
            <text data-y-tick="" x="23" y={y(value) + 4} textAnchor="end">
              {Number(value.toPrecision(4))}
            </text>
          </g>
        ))}
        <rect
          x={x(originTime)}
          y="20"
          width={Math.max(0, width - 28 - x(originTime))}
          height="123"
          fill="var(--accent)"
          opacity=".06"
        />
        <line
          x1={x(originTime)}
          x2={x(originTime)}
          y1="20"
          y2="143"
          stroke="var(--muted)"
          strokeDasharray="4 4"
        >
          <title>Origine: {formatUtc(origin)}</title>
        </line>
        <path
          data-observed-path=""
          d={path(observed)}
          stroke="var(--muted)"
          strokeWidth="2"
          fill="none"
        />
        <path
          d={path(forecast)}
          stroke="var(--chart-ink, var(--ink))"
          strokeWidth="2"
          fill="none"
          strokeDasharray="5 3"
        />
        {forecast
          .filter((d) => d.value !== null && Number.isFinite(d.value))
          .map((d, i) => (
            <circle
              key={i}
              cx={x(d.time)}
              cy={y(d.value!)}
              r="4"
              fill="var(--chart-ink, var(--ink))"
            >
              <title>
                {formatUtc(new Date(d.time).toISOString())}: {d.value} {unit}
              </title>
            </circle>
          ))}
        <text x="32" y="167">
          {formatUtc(new Date(minTime).toISOString()).replace(" UTC", "")}
        </text>
        <text x={width - 28} y="167" textAnchor="end">
          {formatUtc(new Date(maxTime).toISOString()).replace(" UTC", "")}
        </text>
      </svg>
      <p className="forecast-origin">
        Origine della previsione: {formatUtc(origin)}
      </p>
      {!values.length && <p>Nessun valore puntuale disponibile.</p>}
    </figure>
  );
}
