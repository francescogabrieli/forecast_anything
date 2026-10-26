# Models, Composition and Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** collegare Timestral e rendere verificabili composizioni e query probabilistiche supportate.

**Architecture:** provider e operatori implementano i contratti del core; valutazioni e metodi sperimentali producono artefatti separati. L’incapacità di stimare un evento è un risultato esplicito, non una percentuale generata dal linguaggio.

**Tech Stack:** core Python, NumPy, Timestral/PyTorch opzionali, pytest; dataset scaricati e versionati con manifest.

**Spec:** [specifica](../specs/2026-10-24-forecast-anything-design.md). **Prerequisito:** [piano 01](2026-10-24-01-core.md).

## Global Constraints

- “Timestral è il primo candidato per le previsioni; baseline semplici sono parte obbligatoria del confronto.”
- “Una somma di quantili marginali non viene presentata come quantile della somma.”
- “Eventuali fallback dichiarano il modello effettivo che ha risposto.”
- “Le osservazioni future rendono progressivamente valutabili le emissioni passate.”
- Contratti e forme degli array del piano 01 restano vincolanti.

## Review Focus

1. Target futuri o covariate pubblicate dopo l’origine: rifiuto prima dell’inferenza — M1.
2. Gruppi di campioni indipendenti combinati per sbaglio: rifiuto — M2.
3. Probabilità cumulative dedotte da quantili marginali: unsupported — M2/M5.
4. Serie costanti, mancanti o esiti non maturati: metriche definite oppure stato esplicito — M3.
5. Selezione e valutazione sugli stessi dati, restituzioni negative e dati vintage assenti: separazione e assunzioni visibili — M3/M4.

---

## Mappa dei file

Creare providers/timestral.py; operators/temporal.py, operators/events.py; uncertainty/residual_panels.py; evaluation/splits.py, evaluation/metrics.py, evaluation/records.py; benchmarks/manifest.yaml, benchmarks/run.py, benchmarks/prepare.py. Sono sotto src/forecast_anything salvo benchmarks/, che è nella root.

Estendere contracts.py solo con i tipi sotto; creare i test elencati dai task.

## Task M1: provider Timestral isolato

**Files:** creare src/forecast_anything/providers/timestral.py, tests/unit/test_timestral_adapter.py, tests/model/test_timestral_parity.py, integrations/models.lock.json; modificare pyproject.toml.

**Interfaces:** TimestralProvider(checkpoint: str, revision: str, code_revision: str); implementa ForecastProvider del piano 01. Il lock registra repo, revisioni, licenze, versione Python e dipendenze risolte. Nessun peso nel repository.

- [ ] **1. Test fallenti:** test_target_after_origin_is_rejected; test_late_known_covariate_is_rejected; test_preserves_quantiles_and_real_provider; test_core_import_without_torch. Usare un forecaster fittizio che restituisce valori distinguibili per serie/orizzonte/quantile.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_timestral_declares_marginals_not_paths():
    provider = TimestralProvider(
        checkpoint="mistralai/Timestral-28M",
        revision="fixture",
        code_revision="fixture",
    )
    caps = provider.capabilities()
    assert "marginal_quantiles" in caps.representations
    assert "joint_paths" not in caps.representations
~~~

- [ ] **2. Run:** uv run pytest tests/unit/test_timestral_adapter.py -q; deve fallire per provider mancante.
- [ ] **3. Implementare l’adattatore.** Caricare il checkpoint una volta per worker; convertire maschere, target e covariate usando il contratto ufficiale della revisione fissata. Richiedere target event_time <= as_of e covariate available_at <= as_of. L’output iniziale dichiara point e marginal_quantiles, senza inventare paths.
- [x] **4. Verificare prima i test unitari, poi:** uv sync --extra timestral; uv run pytest tests/model/test_timestral_parity.py -q. Il test reale confronta mediane e quantili con la chiamata ufficiale sullo stesso piccolo input, con tolleranze esplicite 1e-5 assoluta/relativa su CPU fp32. Rilevare revisioni prima del download; registrare macchina, latenza warm/cold e memoria. Il gate del provider richiede un test reale eseguito, non saltato. Passato su macOS arm64/Python 3.14 il 2026-10-26; uso locale autorizzato dal proprietario.
- [ ] **5. Commit dei file del task e lock:** feat: add a provenance-preserving Timestral provider.

## Task M2: composizione tipizzata e operatori sugli eventi

**Files:** creare src/forecast_anything/operators/temporal.py, src/forecast_anything/operators/events.py, tests/unit/test_operators.py; modificare graph.py.

**Interfaces:** register_builtin_operators() -> dict[str, Operator]. Operatori: sum_aligned, cumulative_balance, any_exceed; implementano Operator. Config di cumulative_balance: initial_value: float, unit: str; input inflow/outflow nominati. Config di any_exceed: threshold: float, comparator: gt/lt.

- [ ] **1. Test:** su due cammini [2,0] e [0,2], any_exceed threshold=1 restituisce probability=1, non una probabilità ricostruita dai margini. test_quantiles_cannot_be_summed_probabilistically verifica unsupported_representation. test_independent_sample_groups rifiuta gruppi distinti. test_balance_point_and_paths verifica initial=10, inflow=[0,5], outflow=[3,4] → [7,8].
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_anytime_uses_complete_paths():
    t = datetime(2026, 10, 24, tzinfo=timezone.utc)
    result = ForecastResult(
        provider_id="fixture",
        provider_revision="1",
        series_ids=("s",),
        timestamps=(t, t + timedelta(hours=1)),
        units=("count",),
        point=((1, 1),),
        quantiles=None,
        paths=(((2, 0),), ((0, 2),)),
        sample_group_id="world",
        assumptions=(),
    )
    answer = register_builtin_operators()["any_exceed"].apply(
        {"value": result}, {"threshold": 1, "comparator": "gt"}
    )
    assert answer.point[0][0] == 1.0
~~~

- [ ] **2. Run:** uv run pytest tests/unit/test_operators.py -q; deve fallire per operatori mancanti.
- [ ] **3. Implementare gli operatori e i loro contract.** Risultati puntuali possono essere composti come scenari puntuali; probabilità su aggregati richiedono joint_paths coerenti. Una costante o un calendario deterministico non introduce nuovi campioni. Allineamento temporale o conversione di unità richiedono regole esplicite.
- [ ] **4. Ripetere e verificare nel grafo:** il piano compila solo con capacità sufficienti. Per any_exceed il risultato scalare usa una serie-evento, un solo timestamp di fine finestra e unit=probability; assumptions conserva evento e finestra. Point è la frequenza campionaria, quantiles e paths sono None.
- [ ] **5. Commit:** feat: compose typed forecasts and future events.

## Task M3: valutazione temporale e registro delle evidenze

**Files:** creare src/forecast_anything/evaluation/splits.py, metrics.py, records.py, tests/unit/test_evaluation.py; modificare contracts.py e store.py con migrazione 002_evaluations.sql.

**Interfaces:** EvaluationRecord(evaluation_id, run_id, actuals_snapshot_id, status, metrics: dict, origin_count: int, assumptions: tuple[str, ...]); TemporalSplit(exploration_end, selection_end, final_start, horizon, stride). build_splits(timestamps: tuple[datetime, ...], horizon: int) -> TemporalSplit; evaluate_run(run: RunRecord, actuals: Snapshot, graph: GraphSpec) -> EvaluationRecord; Ledger.append_evaluation(record: EvaluationRecord) -> str; Ledger.get_evaluation(evaluation_id: str) -> EvaluationRecord.

- [ ] **1. Test:** test_unmatured_is_not_failure; test_revised_actuals_create_new_evaluation; test_zero_denominator_metric_is_explicit; test_no_overlap_final_split. Confrontare un forecast perfetto, uno peggiore della baseline e una serie costante. Asserire che il riferimento all’emissione non cambi.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_final_split_is_separate():
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    split = build_splits(tuple(t + timedelta(days=i) for i in range(100)), horizon=5)
    assert split.exploration_end < split.selection_end < split.final_start
    assert split.stride == split.horizon == 5
~~~

- [ ] **2. Run:** uv run pytest tests/unit/test_evaluation.py -q; fallimento atteso per interfacce mancanti.
- [ ] **3. Implementare split e metriche.** Default: primi 50% per esplorazione/contesto, 25% successivi per selezione, 25% finali congelati; origine finale non sovrapposta con stride=horizon. Nessuna target window attraversa i confini. Se i dati non bastano, status=insufficient_evidence. Usare MAE, MAE relativo alla baseline, pinball loss e copertura/ampiezza dei livelli disponibili; denominatori nulli sono undefined. Per eventi: Brier score e numerosità, ricostruendo gli esiti con gli operatori del grafo. Scenari ipotetici non realizzati non ricevono una valutazione come se fossero esiti osservati.
- [ ] **4. Ripetere i test:** registrare confronto modello/baseline con stesse origini e input; nuove actuals producono una nuova evaluation_id e lasciano leggibile la precedente.
- [ ] **5. Commit:** feat: evaluate issued forecasts without temporal leakage.

## Task M4: benchmark e generalità riproducibili

**Files:** creare benchmarks/manifest.yaml, benchmarks/prepare.py, benchmarks/run.py, tests/integration/test_benchmark_contract.py. Il rapporto del sampler viene scritto nel successivo task M5.

**Interfaces:** prepare_suite(manifest: Path, destination: Path) -> dict[str, Path]; run_suite(manifest: Path, output: Path, providers: tuple[str, ...]) -> Path. Artefatti: report.json con datasets indicizzato da retail/energy/activity e risultati per provider; origins.csv, assumptions.json, environment.json. Creare le tre fixture tests/fixtures/benchmarks/retail.csv, energy.csv, activity.csv e il relativo manifest.yaml.

- [x] **1. Test:** test_same_contract_three_domains usa piccole fixture retail/energy/activity; test_returned_goods_and_missing_meter_reading applica una ricetta esplicita; test_no_vintage_claim_without_vintages verifica assumed_available_at visibile; test_synthetic_deliveries_are_labelled mantiene separati dati reali e scenario.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_benchmark_reports_all_domains(tmp_path):
    report_path = run_suite(
        Path("tests/fixtures/benchmarks/manifest.yaml"), tmp_path, ("baseline",)
    )
    report = json.loads(report_path.read_text())
    assert set(report["datasets"]) == {"retail", "energy", "activity"}
    assert (tmp_path / "assumptions.json").exists()
~~~

- [x] **2. Run:** `tests/integration/test_benchmark_contract.py` passa con fixture baseline e opt-in Timestral.
- [x] **3. Implementare manifest e preparazione.** Retail: UCI Online Retail II, quantità vendute positive e resi separati; frequenza giornaliera e calendario UTC con assunzione dichiarata quando il fuso originale non è documentato. Energia: UCI household power, aggregazione oraria e campioni mancanti espliciti. Attività: Wikimedia pageviews giornaliere aggregate per progetto/accesso, User-Agent identificabile. Scegliere e fissare le serie senza guardare il holdout; registrare URL, checksum, licenza, intervallo e ricetta. Per dataset privi di vintage il replay assume una disponibilità dichiarata e non certifica i tempi reali di pubblicazione.
- [x] **4. Eseguire prepare, poi run:** eseguito con split congelati e confronto baseline/Timestral sullo stesso insieme di origini finali; artefatto in `docs/research/timestral-benchmark.json`. Timestral non ha vinto su retail e questo non blocca l’accettazione.
- [x] **5. Commit di harness, manifest e rapporto senza pesi o dati grezzi voluminosi:** harness, report sintetico e test vengono versionati; pesi e dataset preparati restano fuori dal repository.
## Task M5: esperimento su traiettorie congiunte

**Files:** creare src/forecast_anything/uncertainty/residual_panels.py, experiments/joint_paths.py, tests/unit/test_joint_paths.py, docs/research/joint-paths.md.

**Interfaces:** ResidualPanel(origin: datetime, horizon: int, series_ids: tuple[str, ...], errors: list[list[float]], available_at: datetime); ResidualPanelSampler.sample(base: ForecastResult, panels: tuple[ResidualPanel, ...], as_of: datetime, draws: int, seed: int) -> ForecastResult.

- [ ] **1. Test fallenti:** test_excludes_unmatured_panels; test_shared_origin_preserves_cross_series_dependence; test_seed_and_draw_identity; test_missing_joint_support. Campioni artificiali con dipendenza positiva/negativa devono conservare l’ordinamento degli eventi aggregati, invece di equivalere a un campionamento indipendente.
Esempio di asserzione rappresentativa da includere nei test del task:

~~~python
def test_no_panels_cannot_create_joint_information():
    t = datetime(2026, 10, 24, tzinfo=timezone.utc)
    base = ForecastResult(
        provider_id="fixture",
        provider_revision="1",
        series_ids=("s",),
        timestamps=(t,),
        units=("count",),
        point=((1,),),
        quantiles=None,
        paths=None,
        sample_group_id=None,
        assumptions=(),
    )
    with pytest.raises(DomainError) as error:
        ResidualPanelSampler().sample(base=base, panels=(), as_of=t, draws=1000, seed=0)
    assert error.value.code == "insufficient_joint_support"
~~~

- [x] **2. Run:** `tests/unit/test_joint_paths.py` passa con la fixture deterministica e l’esperimento reale.
- [x] **3. Implementare un candidato sperimentale preciso:** campionare interi pannelli di errori di forecast storici completati, allineati per origine, serie e orizzonte; aggiungerli alla previsione corrente. Non campionare ogni cella indipendentemente. Usare seed=0 e 1.000 traiettorie nell’esperimento. Etichettare l’ipotesi di trasferibilità dei residui e lo stato experimental.
- [x] **4. Eseguire:** `experiments/joint_paths.py --seed 0 --draws 1000` è stato rieseguito sugli hash M4 congelati. Confronta campionamento indipendente e pannelli su processi congiunti sintetici noti e sui dati M4 con split M3; riporta Brier score, skill, calibrazione, numerosità e costo. Tutti i domini restano provisional perché il limite inferiore bootstrap non è positivo. Nessuna modifica al metodo o al holdout.
- [x] **5. Commit del codice e rapporto completo, inclusi insuccessi:** codice e report JSON versionati; tutte le soglie non raggiunte restano documentate.


## Consegna indipendente

La CLI del piano 01 può usare Timestral e operatori dichiarati. La suite esporta evidenze; operazioni non supportate rimangono identificabili. Lo stato experimental del sampler non viene eliminato per rendere più impressionante una demo.

## Fonti primarie

[Timestral](https://github.com/mistralai/timestral), [licenza pesi](https://huggingface.co/mistralai/Timestral-28M/blob/main/LICENSE), [UCI retail](https://archive.ics.uci.edu/dataset/502/online+retail+ii), [UCI energia](https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption), [Wikimedia API e licenza](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html).
