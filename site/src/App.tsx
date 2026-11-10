import { Chart, Plot } from './Chart';
import { baseline, cutoff, date, day, forecast, journey, nextTarget, partitions, target, update, value } from './demo';

const github = 'https://github.com/francescogabrieli/forecast_anything';
const grid = 'grid gap-x-gutter md:grid-cols-6 lg:grid-cols-12';
const shell = 'mx-auto w-[calc(100%-2*var(--page-inset))] max-w-page';

function DateLabel({ time }: { time: string }) {
  return <time dateTime={day(time)}>{date(time)}</time>;
}

function Chapter({ number, children }: { number: string; children: string }) {
  return <p className="chapter"><span>{number}</span>{children}</p>;
}

function Header() {
  return <header className={shell}>
    <div className="flex min-h-16 items-center justify-between gap-3 border-b border-rule">
      <a className="wordmark" href="./">Forecast Anything</a>
      <nav className="flex items-center gap-5 text-sm sm:gap-8" aria-label="Main">
        <a className="hidden sm:inline" href="#demo">Demo</a>
        <a href="#install">Install</a>
        <a className="hidden sm:inline" href={github}>GitHub <span aria-hidden="true">↗</span></a>
      </nav>
    </div>
  </header>;
}

const photoSource = 'https://commons.wikimedia.org/wiki/File:Shelves_stocked_with_boxes_and_carts_in_a_spacious_warehouse_environment_during_daylight_hours.jpg';
const photoLicense = 'https://creativecommons.org/licenses/by/2.0/';

function HeroFigure() {
  return <figure className="hero-figure" aria-label="Recorded synthetic forecast in a warehouse setting">
    <div className="figure-composition">
      <div className="photo-plane" aria-hidden="true" />
      <div className="warehouse-photo" role="img" aria-label="Warehouse shelves stacked with boxes beside a row of carts" />
      <div className="figure-forecast">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <p className="font-semibold">Daily demand</p>
          <p className="annotation">Synthetic demo</p>
        </div>
        <div className="preview-plot"><Plot compact preview /></div>
        <dl className="preview-values">
          <div><dt><i className="legend-dot" />Timestral</dt><dd className="text-accent-ink">{value(forecast.value)}</dd></div>
          <div><dt><i className="legend-diamond" />Seasonal baseline</dt><dd>{value(baseline.value)}</dd></div>
        </dl>
      </div>
      <div className="figure-update">
        <p className="annotation">Next target</p>
        <p className="mt-0.5 font-semibold"><DateLabel time={nextTarget} /></p>
        <p className="figure-status mt-1 capitalize">{update.quality}</p>
      </div>
    </div>
    <figcaption className="photo-credit">
      Photo by <a href={photoSource}>Nenad Stojković</a> · <a href={photoLicense}>CC BY 2.0</a> · Cropped, monochrome
    </figcaption>
  </figure>;
}

function Hero() {
  return <section className="hero" aria-labelledby="hero-title">
    <div className="hero-copy">
      <p className="hero-kicker">Local forecasting</p>
      <h1 id="hero-title"><span>Forecast with</span>{' '}
        <em>your assistant.<svg viewBox="0 0 420 18" preserveAspectRatio="none" aria-hidden="true">
          <path d="M 4 13 Q 190 1 416 10" pathLength="1" />
        </svg></em>
      </h1>
      <p className="hero-intro">Connect a CSV and run Timestral locally through your assistant. Compare the forecast with a seasonal baseline and see what changes as new data arrives.</p>
      <div className="hero-actions flex flex-wrap items-center gap-x-5 gap-y-3">
        <a className="action" href="#install">Connect your assistant <span aria-hidden="true">↗</span></a>
        <a className="demo-action" href="#demo"><span aria-hidden="true">↓</span> See the demo</a>
      </div>
      <p className="hero-facts">Local Timestral <span>·</span> CSV input <span>·</span> MCP</p>
    </div>
    <HeroFigure />
  </section>;
}

function Demo() {
  return <section id="demo" className="chapter-section" aria-labelledby="demo-title">
    <div className="demo-heading mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div>
        <Chapter number="01">Same-target comparison</Chapter>
        <h2 id="demo-title" className="mt-2">{journey.question.title}</h2>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="annotation">Synthetic CSV <span aria-hidden="true">/</span> {journey.source.observation_count} observations</p>
        <button type="button" className="replay-button" hidden>
          <span aria-hidden="true">↻</span> Replay forecast
        </button>
      </div>
    </div>
    <div className={`${grid} gap-y-6`}>
      <Chart />
      <aside className="readout md:col-span-2 lg:col-span-4" aria-label="Recorded forecast values">
        <p className="annotation">Same target</p>
        <p className="target-date"><DateLabel time={target} /></p>
        <dl className="value-list">
          <div>
            <dt><i className="legend-dot" />Timestral</dt>
            <dd id="forecast-value" className="text-accent-ink">{value(forecast.value)} <small>{forecast.unit}</small></dd>
          </div>
          <div>
            <dt><i className="legend-diamond" />Seasonal baseline</dt>
            <dd id="baseline-value">{value(baseline.value)} <small>{baseline.unit}</small></dd>
          </div>
        </dl>
        <p className="readout-note">One day ahead · cutoff <DateLabel time={cutoff} /> UTC.</p>
      </aside>
    </div>
  </section>;
}

function Evidence() {
  const ids = [
    ['Question', journey.question.id],
    ['Original run', journey.forecast.run_id],
    ['Successor run', update.run_id],
    ['Original snapshot', journey.source.snapshot_id],
    ['Updated snapshot', update.source_snapshot_id],
    ['Backtest', journey.historical_comparison.backtest_id],
  ];
  return <details className="evidence md:col-span-6 lg:col-span-12">
    <summary>Backtest, provenance and record IDs</summary>
    <div className={`${grid} gap-y-6 pt-3 pb-6`}>
      <div className="min-w-0 md:col-span-3 lg:col-span-5">
        <p className="mb-3 text-sm">Mean absolute error in orders, measured at matched historical origins.</p>
        <table className="evidence-table">
          <thead><tr><th scope="col">Partition</th><th scope="col">Origins</th><th scope="col">Timestral</th><th scope="col">Baseline</th></tr></thead>
          <tbody>{partitions.map(p => <tr key={p.partition}>
            <th scope="row" className="capitalize">{p.partition}</th><td>{p.matched_count}</td>
            <td>{value(p.model_mae)}</td><td>{value(p.baseline_mae)}</td>
          </tr>)}</tbody>
        </table>
        <p className="mt-3 text-sm text-muted">The fixture is synthetic. These scores do not establish real-world accuracy.</p>
      </div>
      <div className="min-w-0 md:col-span-3 lg:col-span-6 lg:col-start-7 text-sm">
        <p>Timestral 28M ran locally on CPU. The seasonal-naive baseline is an independent comparator. The worker processed the update while the assistant was disconnected.</p>
        <dl className="record-ids mt-4">
          {[...ids, ['Weights revision', journey.provenance.weights_revision], ['Code revision', journey.provenance.code_revision],
            ['Fixture SHA-256', journey.source.fixture_sha256], ['Provisional reason', update.reason]].map(([label, id]) =>
            <div key={label}><dt>{label}</dt><dd><code>{id}</code></dd></div>)}
        </dl>
      </div>
    </div>
  </details>;
}

function Update() {
  return <section id="update" className={`${grid} chapter-section body-chapter gap-y-6`} aria-labelledby="update-title">
    <div className="md:col-span-3 lg:col-span-5">
      <Chapter number="02">Saved question</Chapter>
      <h2 id="update-title" className="mt-3">When new data arrives.</h2>
      <p className="mt-4">The worker picks up the new CSV row and issues another forecast for the saved question, even after the assistant disconnects.</p>
      <p className="mt-3">The target moves from <DateLabel time={target} /> to <DateLabel time={nextTarget} />. The two forecasts cover different days and aren’t directly comparable.</p>
      <a className="inline-link mt-4 inline-block" href="./docs/release-demo.md">Read the recorded demo guide <span aria-hidden="true">↗</span></a>
    </div>
    <div className="min-w-0 md:col-span-3 lg:col-span-6 lg:col-start-7">
      <table className="update-table">
        <caption>Worker update</caption>
        <tbody>
          <tr><th scope="row">New observation</th><td>{update.observation.value} {update.observation.unit} · <DateLabel time={update.observation.time} /></td></tr>
          <tr><th scope="row">New target</th><td><DateLabel time={nextTarget} /></td></tr>
          <tr><th scope="row">Status</th><td className="capitalize text-accent-ink">{update.quality}</td></tr>
        </tbody>
      </table>
      <p className="mt-3 text-sm text-muted">The update is provisional: there’s only {update.requalification_new_origins} new point to check against. The watch requires 30 new evaluation origins before it qualifies again.</p>
    </div>
    <Evidence />
  </section>;
}

const commands = [
  'uv sync --locked --extra mcp',
  '.venv/bin/forecast-anything setup \\',
  '  --workspace ~/forecast-workspace \\',
  '  --prepare-model',
  'codex mcp list',
].join('\n');

function Install() {
  return <section id="install" className={`${grid} chapter-section body-chapter gap-y-6`} aria-labelledby="install-title">
    <div className="md:col-span-3 lg:col-span-5">
      <Chapter number="03">Local setup</Chapter>
      <h2 id="install-title" className="mt-3">Connect your assistant</h2>
      <ol className="steps mt-4">
        <li>Install the locked runtime and MCP dependencies from a reviewed checkout.</li>
        <li>Review the <a className="inline-link" href="./docs/implementation/timestral.md">Timestral weights terms</a>. Run setup to prepare the model, start the local service and register it with Codex.</li>
        <li>Enable the registered MCP server in Codex and ask it to call <code>get_diagnostics</code>.</li>
      </ol>
      <a className="inline-link mt-5 inline-block" href="./docs/installation.md">Full installation guide <span aria-hidden="true">↗</span></a>
    </div>
    <div className="min-w-0 md:col-span-3 lg:col-span-6 lg:col-start-7">
      <p className="annotation mb-3">From the repository root</p>
      <p className="mb-4 text-sm text-muted">Requires macOS, Python 3.12+, uv, the Codex CLI on PATH, and a checkout kept at a stable path.</p>
      <pre className="command-block" tabIndex={0} aria-label="Local setup commands"><code>{commands}</code></pre>
    </div>
    <details className="evidence console-preview md:col-span-6 lg:col-span-12">
      <summary>Preview the optional console</summary>
      <figure className="pb-5">
        <div className="aspect-[36/25] overflow-hidden rounded-lg border border-rule">
          <img src="./console-preview.webp" width="1440" height="1946" loading="lazy"
            className="h-full w-full object-cover object-top"
            alt="Forecast Anything console showing a dependency graph and a recorded Timestral forecast." />
        </div>
        <figcaption className="mt-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 text-sm text-muted">
          <span>Timestral forecast on synthetic data in the local console.</span>
          <span className="flex flex-wrap gap-x-5 gap-y-1">
            <a className="inline-link" href="./console-preview.webp">Open full screenshot <span aria-hidden="true">↗</span></a>
            <a className="inline-link" href="./docs/quickstart.md">Console setup guide <span aria-hidden="true">↗</span></a>
          </span>
        </figcaption>
      </figure>
    </details>
  </section>;
}

function Footer() {
  return <footer className={shell}>
    <div className="footer-row flex flex-wrap items-baseline justify-between gap-x-10 gap-y-4 border-t border-rule">
      <a className="wordmark" href="./">Forecast Anything</a>
      <nav className="flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Footer">
        <a href="./docs/quickstart.md">Documentation</a>
        <a href={github}>Repository <span aria-hidden="true">↗</span></a>
        <a href="./LICENSE.txt">License</a>
      </nav>
    </div>
  </footer>;
}

export function App() {
  return <>
    <a className="skip-link" href="#main">Skip to content</a>
    <Header />
    <main id="main" className={shell} tabIndex={-1}>
      <Hero />
      <Demo />
      <Update />
      <Install />
    </main>
    <Footer />
  </>;
}
