# Autonomous Observatory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** un osservatorio headless che scopre domande candidate, aggiorna il Future Graph e pubblica segnalazioni ricostruibili.

**Architecture:** discovery e agenti producono proposte strutturate; policy e runtime sono autorità di esecuzione. SQLite conserva job ed eventi; il servizio Eve opzionale comunica solo con strumenti e API espliciti.

**Tech Stack:** Python/FastAPI/SQLite; Node 24, TypeScript, Eve e Zod nell’adattatore agenti. Le versioni vengono fissate nei lock.

**Spec:** [specifica](../specs/2026-10-24-forecast-anything-design.md). **Prerequisiti:** piani [01](2026-10-24-01-core.md) e [02](2026-10-24-02-models-and-evidence.md).

## Global Constraints

- “Il sistema deve scoprire autonomamente anche domande candidate da tenere sotto osservazione.”
- “Una somiglianza scoperta dall’agente è una relazione candidata, non una dipendenza causale acquisita.”
- “Ogni candidata ha una motivazione, requisiti di dati, metodo di valutazione e costo stimato.”
- “La persona può correggere priorità e rilevanza, senza dover scegliere algoritmi.”
- “La consegna proposta è almeno una volta con deduplicazione.”
- Il nucleo rimane utilizzabile senza un LLM; nessun valore numerico generato liberamente entra come evidenza.

## Review Focus

1. Campi ambigui o credenziali nei campioni: chiarimento esplicito e dati sensibili esclusi — A1.
2. Ricerca ripetuta che sceglie solo risultati fortunati: budget, storia degli scarti e protocolli separati — A2.
3. Evidenze insufficienti o diventate vecchie: stato provvisorio/scaduto, nessuna promozione implicita — A3.
4. Lease scaduta e worker riavviato: un vecchio worker non pubblica risultati fuori ordine — A4.
5. Istruzioni malevole nei dati e consumer disconnessi: strumenti controllati e recupero indipendente degli eventi — A6/A5.

---

## Mappa dei file

Sotto src/forecast_anything: sources/catalog.py, sources/profiling.py, discovery/candidates.py, discovery/policy.py, watches.py, jobs.py, worker.py, api/app.py, api/routes.py, api/scenarios.py; migrazioni 003_discovery.sql, 004_observatory.sql e 005_jobs.sql.

Adattatore separato: apps/agent/agent/instructions.md, agent.ts, tools/inspect_source.ts, propose_candidates.ts, explain_run.ts; apps/agent/src/client.ts, bridge.ts; tests e lock del relativo package.

## Task A1: catalogo e interpretazioni delle fonti

**Files:** creare src/forecast_anything/sources/catalog.py, profiling.py, connectors/http_json.py, tests/unit/test_sources.py; estendere contracts.py e CSV connector.

**Interfaces:** SourceSpec(source_id, kind: csv/http_json, location, secret_ref: str oppure None, mapping: dict, refresh_seconds: int); SourceProfile(source_id, fields: dict, proposed_mapping: dict, unresolved: tuple[str, ...], assumptions: tuple[str, ...]); inspect_source(spec: SourceSpec) -> SourceProfile; ingest_source(spec: SourceSpec, as_of: datetime) -> Snapshot.

- [ ] **1. Test:** test_ambiguous_timestamp_requires_resolution; test_unknown_unit_blocks_composition; test_credentials_never_enter_profile; test_duplicate_fetch_is_stable. Un 401 della sorgente produce source_unavailable, non un dataset vuoto.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_profile_does_not_invent_units(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text("date,value\n2026-10-24,1\n")
    source = SourceSpec(source_id="s", kind="csv", location=str(path), secret_ref=None,
                        mapping={}, refresh_seconds=60)
    assert "unit" in inspect_source(source).unresolved
~~~

- [ ] **2. Run:** uv run pytest tests/unit/test_sources.py -q; fallimento atteso per catalogo mancante.
- [ ] **3. Implementare CSV normalizzato e HTTP JSON con mapping esplicito.** Proporre ruoli dai campioni senza inventare unità o frequenze. Limitare il campione inviabile all’agente a 100 righe; risolvere secret_ref solo nell’adattatore di lettura e limitarne l’accesso alla fonte configurata.
- [ ] **4. Ripetere:** l’ingestione usa freeze; mapping e assunzioni hanno revisioni conservate nel catalogo. Il parser non esegue contenuti letti.
- [ ] **5. Commit:** feat: profile and ingest versioned sources.

## Task A2: domande candidate e protocolli di verifica

**Files:** creare src/forecast_anything/discovery/candidates.py, policy.py, migrations/003_discovery.sql, tests/unit/test_discovery.py; estendere contracts.py e store.py.

**Interfaces:** DiscoveryBudget(max_candidates: int = 10, max_tool_calls: int = 20); Candidate(candidate_id, template_id, source_ids, graph: GraphSpec, reason, protocol_id, epoch_id); DiscoveryEpoch(epoch_id, source_snapshot_ids, explored_candidate_ids, final_origin_ids); EligibilityDecision(action: activate/provisional/reject, reason_codes: tuple[str, ...]); propose_candidates(profiles: tuple[SourceProfile, ...], budget: DiscoveryBudget) -> tuple[Candidate, ...]; assess_candidate(candidate: Candidate, evidence: tuple[EvaluationRecord, ...], epoch: DiscoveryEpoch) -> EligibilityDecision.

- [ ] **1. Test:** test_no_undeclared_operational_limit; test_noise_candidate_is_not_promoted; test_holdout_cannot_be_reused_for_tuning; test_rejected_candidate_is_preserved; test_budget_is_enforced_outside_agent.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_discovery_without_sources_proposes_nothing():
    assert propose_candidates((), DiscoveryBudget()) == ()
~~~

- [ ] **2. Run:** uv run pytest tests/unit/test_discovery.py -q; fallimento atteso per discovery mancante.
- [ ] **3. Implementare tre template registrati:** deviazione dal comportamento atteso; cambiamento di previsione; superamento di limite dichiarato. I template referenziano operatori supportati. Registrare tutte le candidate e il loro protocollo, non solo le selezionate. Una domanda libera dell’agente deve essere compilabile in un template/operatore dichiarato oppure resta proposta non eseguibile.
- [ ] **4. Verificare la policy su suite sintetica congelata:** almeno 30 origini finali per la domanda, skill finale positivo sul criterio scelto e nessuna violazione temporale/semantica; probabilità-evento richiede anche il gate del piano 02. Il provider selezionato può essere una baseline: il criterio riguarda l’utilità della domanda rispetto al riferimento predefinito, non una vittoria obbligatoria di Timestral. Un protocollo esplorativo senza trattamento valido della selezione resta provisional. Le correzioni di selezione sono ammesse solo quando le assunzioni del metodo sono verificate; non attribuire a queste soglie un controllo globale dei falsi positivi. Ogni nuova configurazione consuma un nuovo blocco finale, mai il vecchio holdout riutilizzato.
- [ ] **5. Commit:** feat: discover and qualify predictive questions.

## Task A3: sorveglianze e rilevanza

**Files:** creare src/forecast_anything/watches.py, migrations/004_observatory.sql, tests/unit/test_watches.py; estendere contracts.py.

**Interfaces:** Watch(watch_id, candidate_id, lifecycle, quality, graph_id, graph_version, policy_version, next_due_at, muted: bool, priority: int = 3); priority va da 0 a 5. lifecycle=candidate/evaluating/active/paused/unsupported; quality=provisional/usable/stale/degraded. advance_watch(watch: Watch, event: dict, now: datetime) -> Watch; summarize_change(previous: RunRecord, current: RunRecord) -> dict.

- [ ] **1. Test:** test_insufficient_evidence_never_activates; test_stale_after_missing_refresh; test_revised_source_invalidates_dependent_evidence; test_shared_cause_is_grouped; test_muting_preserves_history.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_refresh_expired_is_visible():
    t = datetime(2026, 10, 24, tzinfo=timezone.utc)
    watch = Watch(watch_id="w", candidate_id="c", lifecycle="active", quality="usable",
                  graph_id="g", graph_version=1, policy_version="1", next_due_at=t, muted=False)
    assert advance_watch(watch, {"kind": "refresh_expired"}, t).quality == "stale"
~~~

- [ ] **2. Run:** uv run pytest tests/unit/test_watches.py -q; fallimento atteso per Watch mancante.
- [ ] **3. Implementare la macchina degli stati.** Gli eventi riconosciuti includono evidence_qualified, insufficient_evidence, refresh_expired, quality_degraded e muted. activate richiede EligibilityDecision appropriata; provisional rimane consultabile ma non è un allarme operativo. I report di cambiamento confrontano stesse entità/orizzonti, distinguendo l’avanzamento della finestra da una variazione sui timestamp comuni. Le spiegazioni derivano da dipendenze e nuovi dati, senza affermare causalità.
- [ ] **4. Ripetere:** quando più watch dipendono dallo stesso aggiornamento, conservarli individualmente e raggruppare la segnalazione per causa/origine. Una revisione può cambiare l’applicabilità corrente delle evidenze, senza riscrivere le valutazioni passate. Muting non elimina risultati o valutazioni.
- [ ] **5. Commit:** feat: maintain explainable predictive watches.

## Task A4: lavoro durevole, retry e aggiornamenti selettivi

**Files:** creare src/forecast_anything/jobs.py, worker.py, migrations/005_jobs.sql, tests/integration/test_worker.py; modificare store.py e runtime.py.

**Interfaces:** Job(job_id, key, payload, attempt, state, lease_token, lease_until); JobQueue(ledger: Ledger).enqueue(key: str, payload: dict) -> Job; JobQueue.claim(owner: str, now: datetime, ttl_seconds: int) -> Job oppure None; Worker(runtime: Runtime, queue: JobQueue).run_due(now: datetime, limit: int = 10) -> tuple[str, ...]. LeaseGuard(job_id, lease_token); append_run e Runtime.run accettano lease_guard opzionale.

- [ ] **1. Test:** test_restart_recovers_pending_job; test_expired_owner_cannot_commit; test_same_source_change_only_recomputes_descendants; test_retry_and_outbox_do_not_duplicate_completed_run.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_job_key_is_idempotent(tmp_path):
    queue = JobQueue(Ledger(tmp_path / "state.db"))
    assert queue.enqueue("refresh/s/1", {"source_id": "s"}).job_id == (
        queue.enqueue("refresh/s/1", {"source_id": "s"}).job_id)
~~~

- [ ] **2. Run:** uv run pytest tests/integration/test_worker.py -q; fallimento atteso per worker mancante.
- [ ] **3. Implementare job persistenti e fencing del writer.** Default un worker, lease 60 secondi con rinnovo ogni 20; un token scaduto non può fare commit. Usare key logico per job e key di emissione job_id/attempt: lo stesso tentativo ritentato recupera il risultato; un nuovo tentativo dopo fallimento conserva la storia. Il lavoro numerico avviene fuori dalla transazione.
- [ ] **4. Ripetere con fault injection prima/dopo il commit:** risultato ed evento restano atomici; il job può essere completato dopo un riavvio senza rigenerare l’emissione già committata. Budget persistente e polling rispettano next_due_at e indisponibilità della fonte.
- [ ] **5. Commit:** feat: resume predictive work after interruptions.

## Task A5: API, eventi e scenari

**Files:** creare src/forecast_anything/api/app.py, src/forecast_anything/api/routes.py, src/forecast_anything/api/scenarios.py, tests/integration/test_api.py, scripts/export_contracts.py; modificare cli.py per serve e worker.

**Interfaces:** create_app(ledger: Ledger, runtime: Runtime, workspace_token: str) -> FastAPI. Rotte v1: POST/GET sources; GET sources/{id}/profile; POST candidates; GET candidates/{id}; POST/GET watches; PATCH watches/{id} per muted/priority; POST jobs; GET jobs/{id}; GET runs/{id}; GET evaluations/{id}; GET snapshots/{id}; GET graphs/{id}?version=N; GET events?after=N; POST scenarios; GET capabilities. Gli ID sono opachi e gli schemi provengono da contracts.py. export_contracts(output: Path) -> None esporta schemas.json e openapi.json dal servizio per la generazione dei client nei package TypeScript.

POST scenarios consuma ScenarioRequest(base_graph_id, base_version, label, source_overrides: dict[str, Snapshot]) e produce graph_id/version di un nuovo grafo, scenario_id e parent_run_id. Le sostituzioni sono marcate assumed; non modificano le fonti base.

- [ ] **1. Test:** test_request_without_token_is_401; test_invalid_plan_does_not_enqueue; test_two_event_consumers_resume_independently; test_scenario_does_not_rewrite_base; test_domain_error_has_stable_code. Il cursore deve funzionare anche dopo reconnect.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_workspace_token_is_required(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    runtime = Runtime(ledger, {}, {}, lambda: datetime.now(timezone.utc))
    client = TestClient(create_app(ledger, runtime, workspace_token="test-token"))
    assert client.get("/v1/sources").status_code == 401
~~~

- [ ] **2. Run:** uv run pytest tests/integration/test_api.py -q; fallimento atteso per app mancante.
- [ ] **3. Implementare rotte thin sui servizi precedenti.** Default loopback; workspace token richiesto per dati/configurazione; dominio d’errore in JSON. Un nuovo profilo o una sua revisione accoda un job discovery con epoch_id; il default usa i template, l’adattatore A6 può proporre ulteriori candidate nello stesso contratto. Le risposte SSE hanno id=cursor e supportano Last-Event-ID; lo storico rimane leggibile via GET events. Nessuna coda per consumer che consumi gli eventi degli altri.
- [ ] **4. Run:** uv run pytest tests/integration -q; avviare serve e worker su due processi con DB locale, spegnere e riavviare worker durante un job. Verificare run, evidenceIds e cursori tramite HTTP.
- [ ] **5. Commit:** feat: expose the autonomous observatory API.
## Task A6: agente con strumenti e prova del framework

**Files:** creare apps/agent/package.json, lock, agent/agent.ts, agent/instructions.md, agent/tools/inspect_source.ts, propose_candidates.ts, explain_run.ts, src/client.ts, src/bridge.ts, src/schema.generated.ts, tests/agent.test.ts; creare src/forecast_anything/discovery/agent_gateway.py, tests/integration/test_agent_gateway.py, docs/decisions/agent-runtime.md. I path abbreviati dei file TypeScript sono relativi ad apps/agent.

**Interfaces proprie:** inspectSource(sourceId: string): Promise<SourceProfile>; proposeCandidates(sourceIds: string[], epochId: string): Promise<Candidate[]>; explainRun(runId: string): Promise<{text: string; evidenceIds: string[]}>; submitProposal(value: unknown): Promise<{candidateIds: string[]}>. Le forme JSON sono generate dagli schemi del core, non riscritte manualmente. submitProposal rifiuta input non conformi prima di una richiesta HTTP con code=invalid_proposal.

Il bridge espone POST /forecast/discover con epochId, sourceIds e idempotencyKey, restituendo sessionId; GET /forecast/discover/{sessionId} restituisce stato e candidate validate. Aggiungere src/forecast_anything/discovery/agent_gateway.py: AgentGateway.start(epoch_id: str, source_ids: tuple[str, ...], key: str) -> str; AgentGateway.poll(session_id: str) -> tuple[Candidate, ...] oppure None. Il job discovery conserva sessionId e riprende il polling dopo restart; le proposte sono deduplicate per epoch/identità canonica.

- [ ] **1. Test con risposte LLM controllate:** una colonna con istruzioni non autorizza strumenti aggiuntivi; una percentuale senza evidenceId viene rifiutata come evidenza; schema o provider non registrato resta errore; max_tool_calls è imposto dal bridge. La spiegazione cita solo evidenceIds presenti nel run.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~ts
it("does not accept a numeric answer as a candidate", async () => {
  await expect(submitProposal({ probability: 0.99 }))
    .rejects.toMatchObject({ code: "invalid_proposal" });
});
~~~

- [ ] **2. Run dal package:** npm test -- --run; fallimento atteso per bridge mancante.
- [ ] **3. Primo esperimento eseguibile del task:** fissare Eve e leggere la documentazione inclusa nel package prima di scrivere l’adattatore. Verificare self-hosting, persistenza dei workflow e chiamata a un provider configurato tramite SDK diretto o Gateway. Per il profilo self-hosted usare il Workflow World Postgres documentato; tenere separate le sue tabelle dal registro del core. Registrare versione e risultati in agent-runtime.md. Se il framework impone un servizio cloud obbligatorio, fermare questa integrazione e proporre una decisione tecnica alternativa senza alterare il core.
- [ ] **4. Implementare un solo agente, il gateway del job discovery e gli strumenti dichiarati, poi ripetere test e smoke reale.** LLM/model ID sono configurabili e registrati; credenziali solo nell’ambiente del servizio agenti. In CI usare ScriptedLLM dichiarato; uno smoke reale registra input consentiti, chiamate, latenza e costo, senza chiavi. Testare un restart della sessione e del worker: stesso job riprende lo stesso sessionId; il budget non riparte da zero. Rifiutare proposte dopo budget esaurito.
- [ ] **5. Commit:** feat: attach a bounded discovery agent.

Il framework Eve è una scelta del piano isolata dietro il bridge, non una parte del contratto pubblico Future Graph. Una baseline senza agenti continua a essere usabile.


## Consegna indipendente

Un client può collegare una fonte, ottenere proposte, seguirne la verifica e recuperare emissioni e segnalazioni. Il servizio gira su infrastruttura propria; nessuna UI è necessaria per provarne la semantica.

## Fonti primarie

[Eve](https://github.com/vercel/eve), [self-hosting e backend workflow](https://eve.dev/docs/guides/deployment/self-hosting), [SQLite WAL](https://www.sqlite.org/wal.html).
