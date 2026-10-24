# Observatory Experience and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** rendere l’osservatorio provabile e comprensibile, poi preparare una release OSS riproducibile.

**Architecture:** la console legge e comanda lo stesso servizio del piano 03; grafici, spiegazioni e scenari mostrano risultati già registrati. Build, esempi e documentazione provano il percorso dell’utilizzatore.

**Tech Stack:** React, TypeScript, Vite, SVG per il grafo iniziale, Vitest, Playwright, Docker Compose; package Python del core.

**Spec:** [specifica](../specs/2026-10-24-forecast-anything-design.md). **Prerequisito:** [piano 03](2026-10-24-03-observatory-and-agents.md).

## Global Constraints

- “La prima interfaccia proposta è un osservatorio utilizzabile da persone non specialiste, accompagnato da un’API sullo stesso nucleo.”
- “I risultati distinguono sempre osservazioni, programmi, assunzioni e stime.”
- “La persona può capire perché una scoperta è stata evidenziata e perché altre candidate sono state scartate.”
- “La telemetria del prodotto self-hosted resta disattivata per default” è una scelta proposta nella roadmap.
- Nome, registry e URL pubblici vanno risolti prima di pubblicare: nessuna destinazione inventata nel codice o nel README.

## Review Focus

1. Fonte ambigua o non disponibile: percorso per correggere il significato senza perdere configurazione — U1.
2. Previsione scaduta, puntuale o sperimentale: niente bande/probabilità aggiunte dalla UI — U2.
3. Evento SSE ripetuto e reconnect: nessuna segnalazione duplicata o persa — U2.
4. Installazione senza chiave LLM e senza pesi: demo reale con baseline e limiti dichiarati — U3.
5. Pacchetto installato fuori dal checkout: esempi, licenze e risorse realmente incluse — U4.

---

## Mappa dei file

apps/console/package.json e lock; src/api/schema.generated.ts, client.ts; src/features/sources/ConnectSource.tsx; src/features/observatory/DiscoveryFeed.tsx, FutureGraph.tsx, RunDetails.tsx, ScenarioCompare.tsx; src/App.tsx. Test accanto alle feature e tests/e2e/observatory.spec.ts.

Root: Dockerfile, compose.yaml, compose.timestral.yaml, compose.agent.yaml, scripts/bootstrap_demo.py, README.md, LICENSE, NOTICE, CONTRIBUTING.md, SECURITY.md, docs/capabilities.md, docs/quickstart.md, docs/connectors.md, .github/workflows/ci.yml, release.yml.

## Task U1: client e collegamento guidato delle fonti

**Files:** creare apps/console/package.json, lock, tsconfig.json, vite.config.ts, src/api/client.ts, src/api/schema.generated.ts, src/features/sources/ConnectSource.tsx, ConnectSource.test.tsx, src/App.tsx; creare src/test/fixtures.ts. L’exporter del core è stato creato nel task A5.

**Interfaces:** consumare export_contracts e generare i tipi con uno script generate:types nel package basato su OpenAPI. La rigenerazione è deterministica. ApiClient(baseUrl: string, token: string); inspectSource(id: string): Promise<SourceProfile>; saveSource(value: SourceSpec): Promise<SourceSpec>. ConnectSource riceve client e sourceId; il client delle props espone solo inspectSource e saveSource. fixtures.ts definisce makeProfile(overrides: Partial<SourceProfile> = {}), makeRun(overrides: Partial<RunRecord> = {}) e makeWatch(overrides: Partial<Watch> = {}), con valori fissi conformi al contratto: una serie baseline con point=[[1,2]], quantiles=null e paths=null. Il chiarimento dell’unità mostra il testo «Unità da chiarire» e disabilita il pulsante «Attiva».

- [ ] **1. Test fallenti:** la fonte senza unità propone un chiarimento; un 401 non viene mostrato come dataset vuoto; un mapping corretto viene salvato e riletto dal servizio. Gli input dell’utente restano presenti dopo un errore.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~tsx
it("keeps ambiguous units inactive", async () => {
  const client = { inspectSource: vi.fn().mockResolvedValue(makeProfile({ unresolved: ["unit"] })),
                   saveSource: vi.fn() };
  render(<ConnectSource client={client} sourceId="s" />);
  expect(await screen.findByText("Unità da chiarire")).toBeVisible();
  expect(screen.getByRole("button", { name: "Attiva" })).toBeDisabled();
  expect(client.saveSource).not.toHaveBeenCalled();
});
~~~

- [ ] **2. Run dal package:** npm test -- --run src/features/sources/ConnectSource.test.tsx; deve fallire per feature mancante.
- [ ] **3. Implementare client e percorso di collegamento.** Mostrare interpretazione, assunzioni e campi irrisolti con parole comprensibili; impedire “attivo” quando il backend segnala ambiguità bloccanti. Il token di workspace è mantenuto in memoria e non inserito in URL, log o analytics.
- [ ] **4. Ripetere e generare i tipi:** uv run python scripts/export_contracts.py --output apps/console/src/api; npm run generate:types; npm run typecheck. Una CI verifica che la rigenerazione non lasci diff.
- [ ] **5. Commit dei file del task:** feat: connect sources through the observatory.

## Task U2: scoperte, grafo, evidenze e scenari

**Files:** creare apps/console/src/features/observatory/DiscoveryFeed.tsx, FutureGraph.tsx, RunDetails.tsx, ScenarioCompare.tsx e relativi test; creare tests/e2e/observatory.spec.ts.

**Interfaces:** DiscoveryFeed riceve Watch[] e EventRecord[]; FutureGraph riceve GraphSpec e il set di node_id modificati; RunDetails riceve run: RunRecord, evaluations: EvaluationRecord[] e watch opzionale: Watch; ScenarioCompare riceve le due emissioni e i loro GraphSpec. Il client aggiunge getRun, getGraph, getEvents, getEvaluation, getSnapshot, updateWatch e createScenario utilizzando le rotte A5.

- [ ] **1. Test:** test_deduplicates_replayed_cursor; test_point_only_has_no_uncertainty_band; test_stale_and_experimental_are_visible; test_scenario_keeps_assumption_labels. Un evidenceId è navigabile fino al run e agli input.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~tsx
it("does not draw uncertainty for a point-only forecast", () => {
  render(<RunDetails run={makeRun()} evaluations={[]} watch={makeWatch({ quality: "stale" })} />);
  expect(screen.getByText("Previsione scaduta")).toBeVisible();
  expect(screen.queryByLabelText("Intervallo previsto")).not.toBeInTheDocument();
});
~~~

- [ ] **2. Run:** npm test -- --run; fallimento atteso per feature mancanti.
- [ ] **3. Implementare una console con fonti, scoperte, grafo e dettaglio.** Grafo SVG navigabile anche da tastiera, con ordine topologico dal backend. I tipi di informazione hanno etichette testuali, non solo colori. RunDetails mostra «Previsione scaduta» quando watch.quality=stale; le bande presenti hanno nome accessibile «Intervallo previsto». Gli scenari chiamano POST scenarios e visualizzano differenze sui timestamp comuni; nessuna aritmetica probabilistica viene rifatta nel browser.
- [ ] **4. Verificare end-to-end:** npx playwright test tests/e2e/observatory.spec.ts. Collegare due fixture, far valutare una candidata, ricevere una segnalazione, cambiare una fonte e vedere i nodi interessati; disconnettere e riprendere gli eventi; confrontare uno scenario senza modificare il run base. Usare backend vero e provider deterministico dichiarato. Provare tastiera, viewport stretta e contrasto degli stati.
- [ ] **5. Commit:** feat: explore connected futures and their evidence.

## Task U3: installazione e tre esempi trasversali

**Files:** creare Dockerfile, compose.yaml, compose.timestral.yaml, compose.agent.yaml, .env.example, scripts/bootstrap_demo.py, examples/retail/, examples/energy/, examples/activity/, tests/integration/test_packaged_demo.py; modificare documentazione quickstart.

**Interfaces:** bootstrap_demo(workspace: Path) -> Path crea configurazione locale, token e percorso DB; mai chiavi inventate per servizi esterni. Modalità demo: core, worker e console; override agenti: Eve e relativo Postgres. Un worker per workspace.

- [ ] **1. Test:** test_bootstrap_never_overwrites_existing_workspace; test_demo_without_llm_or_weights; test_three_examples_use_same_core; test_restart_keeps_existing_run_ids. Le assunzioni sintetiche dei calendari rimangono visibili.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_bootstrap_keeps_existing_configuration(tmp_path):
    path = bootstrap_demo(tmp_path)
    before = path.read_bytes()
    assert bootstrap_demo(tmp_path).read_bytes() == before
~~~

- [ ] **2. Run:** uv run pytest tests/integration/test_packaged_demo.py -q; fallimento atteso per packaging mancante.
- [ ] **3. Implementare immagini e comando di avvio.** Immagine API leggera e worker con provider opzionali installabili; nessun peso incorporato. Il profilo demo usa baseline reale e discovery a template, dichiarandolo. compose.timestral.yaml sostituisce la configurazione dello stesso worker, scarica la revisione fissata alla prima scelta e riutilizza la cache; non avvia un secondo worker concorrente. L’override agenti richiede un provider configurato; il README distingue chiaramente demo, replay e agente LLM reale.
- [ ] **4. Verificare su ambiente pulito:** docker compose --profile demo up --build; seguire soltanto il quickstart. Ripetere con docker compose -f compose.yaml -f compose.timestral.yaml -f compose.agent.yaml --profile demo up --build e un LLM configurato; registrare smoke completo. Eseguire la prova con cinque persone della roadmap e correggere il percorso fino alla soglia proposta. Il core rimane utilizzabile anche da wheel Python senza Docker.
- [ ] **5. Commit:** build: package a reproducible forecasting observatory.

## Task U4: release candidata e progetto contribuibile

**Files:** creare README.md, LICENSE, NOTICE, CONTRIBUTING.md, SECURITY.md, docs/capabilities.md, docs/quickstart.md, docs/connectors.md, .github/ISSUE_TEMPLATE/bug.yml, .github/ISSUE_TEMPLATE/connector.yml, .github/workflows/ci.yml, .github/workflows/release.yml, scripts/check_release.py, tests/integration/test_release.py.

**Interfaces:** check_release(dist_dir: Path) -> dict con installazione, contenuti, licenze e smoke. Documentare ForecastProvider, Operator e SourceSpec già implementati, senza crearne varianti solo per gli esempi.

- [ ] **1. Scrivere il controllo di accettazione della release:** installare la wheel in un ambiente nuovo fuori dal repository, eseguire l’esempio minimo e verificare versione/schema, file inclusi e assenza di credenziali/pesi. Registrare il fallimento del controllo prima della preparazione dei contenuti mancanti.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_installed_release_has_passed_smoke():
    report = check_release(Path("dist"))
    assert report["installed_outside_checkout"] is True
    assert report["minimal_example_passed"] is True
    assert report["embedded_credentials"] == []
~~~

- [ ] **2. Build e verifica:** uv build; uv run python scripts/check_release.py --dist dist. Prima di completare il task falliscono gli elementi mancanti del pacchetto.
- [ ] **3. Preparare materiale pubblico e CI.** Licenza proposta Apache-2.0 per il nostro codice, attribution separata per dipendenze e dati. README con promessa, demo provabile, matrice capacità, quickstart e differenze dimostrate. CI: unit/integration, typecheck, build console, E2E con provider deterministico; smoke reali dei modelli in job dichiarati con artefatti. Esportare una release candidata; pubblicazione effettiva segue nome/owner/registry risolti e il passaggio 5 della roadmap.
- [ ] **4. Ripetere il controllo su wheel e immagini:** tutti i percorsi documentati sono provati. Ogni job saltato è visibile e non conta come test riuscito di un modello. Preparare tre issue iniziali contribuibili con fixture e accettazione: connettore, ricetta dati, operatore supportato.
- [ ] **5. Commit:** release: prepare the public forecasting infrastructure.

## Consegna

Release candidata installabile, osservatorio usabile, documentazione e demo riproducibili. Lancio, contatti, pubblicazione su canali e sponsorizzazioni seguono la roadmap generale; non sono eseguiti implicitamente da questo piano.
