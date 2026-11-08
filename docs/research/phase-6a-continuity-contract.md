# Phase 6A: Contratto di Continuità, Qualifica e Controlli delle Domande

**Base di partenza:** `400239ccdda02a362c3b809b05650aa28afa481a` (`origin/main`, che unisce la PR #22 e contiene il commit di chiusura della fase 5 `617e8a948ae9bdc3afc79540cf9d56b66c5b9c53`).  
**Worktree e branch dedicati:** branch `codex/phase-6-continuity-updates` in `/private/tmp/forecast-phase6-continuity-updates`.  
**Stato:** Checkpoint 6A completato per revisione. Nessun codice della fase 6B implementato in anticipo.

---

## 1. Analisi dello stato attuale con riferimenti al codice

### 1.1 Ricostruzione del flusso quando il worker aggiorna la fonte di una domanda qualificata

Oggi l'esecuzione in background è gestita da `Worker` (`src/forecast_anything/worker.py`), che coordina lo scheduling delle fonti, l'ingestione, l'invalidazione dei watch e l'eventuale discovery provvisoria:

1. **Rilevamento e scheduling della fonte (`Worker._schedule_sources`, righe 307-356):**
   - Il worker controlla la tabella `watches` e identifica i watch in cui `next_due_at <= now` e che non siano superseded (`watch.watch_id in superseded`), non in lifecycle `unsupported` e privi di `migration_reason`.
   - Per ciascun `source_id` dipendente, calcola la scadenza minima (`due[source_id] = min(...)`).
   - Verifica la tabella `source_polling` e accoda un job `source_refresh` nella `JobQueue` con chiave di emissione idempotente `refresh/{source_id}/{registered.revision}/{deadline.isoformat()}`.

2. **Ingestione della fonte e cattura del nuovo snapshot (`Worker._refresh_source`, righe 381-462):**
   - Viene verificata la corrispondenza con la revisione registrata nel `SourceCatalog` (`catalog.get`).
   - Se il job non contiene già uno snapshot congelato, viene chiamato `ingest_source(registered.spec, ...)` per produrre un nuovo `Snapshot` immutabile e `inspect_source(...)` per derivare il `SourceProfile`.
   - Il nuovo snapshot viene persistito nel ledger (`ledger.put_snapshot`).
   - In caso di errore durante la lettura: il worker aggiorna `source_polling` impostando `available=False` e invoca `advance_watch` con evento `{"kind": "quality_degraded"}` per tutti i watch collegati a quella fonte (`worker.py:413-422`).
   - In caso di successo: il worker itera su tutti i watch collegati a `payload["source_id"]`. Se lo snapshot `snap.snapshot_id` non è già presente in `watch.source_snapshot_ids`, esegue:
     ```python
     ledger.advance_watch(
         watch.watch_id,
         {
             "kind": "source_revised",
             "source_id": payload["source_id"],
             "revision": snap.snapshot_id,
         },
         now,
         event_id=f"snapshot/{snap.snapshot_id}",
         lease_guard=job.guard,
     )
     ```

3. **Invalidazione immediata delle evidenze del watch (`advance_watch`, `src/forecast_anything/watches.py`, righe 153-187):**
   - L'evento `source_revised` ha un impatto profondo e distruttivo sullo stato di qualifica:
     ```python
     invalidated = tuple(
         dict.fromkeys(
             (
                 *watch.invalidated_evaluation_ids,
                 *(watch.eligibility_decision.evaluation_ids if watch.eligibility_decision else ()),
             )
         )
     )
     updates = dict(
         lifecycle=(watch.lifecycle if watch.lifecycle in {"unsupported", "paused"} else "evaluating"),
         quality="stale",
         evidence_applicable=False,
         reevaluation_required=True,
         invalidated_evaluation_ids=invalidated,
         candidate_invalidated=True,
         next_due_at=now,
     )
     ```
   - **Risultato:** anche se il watch era `operational` (qualificato con backtest su 30+ origini finali contro baseline), l'arrivo di un qualsiasi nuovo snapshot lo degrada istantaneamente a `evaluating`, `quality="stale"`, `evidence_applicable=False`, `candidate_invalidated=True` e sposta tutti gli `evaluation_ids` tra quelli invalidati.

4. **Accodamento e compilazione del successore (`Worker._discover_refresh`, righe 463-560):**
   - Subito dopo l'invalidazione, `_refresh_source` accoda un job `discover_refresh` (`worker.py:443-452`).
   - `_discover_refresh` calcola un nuovo `epoch_id = _digest({"predecessor": old.candidate_id, ..., "snapshot": snap.snapshot_id})`.
   - Compila una nuova proposta di candidato (`compile_proposal`) con un nuovo `candidate_id`.
   - Crea una nuova `DiscoveryEpoch` con `source_snapshot_ids=(snap.snapshot_id,)` e `final_origin_ids=()`. In ossequio ai principi anti-leakage di Plan 02/08, **le origini finali passate non vengono mai riutilizzate**.
   - Genera un nuovo ID per il watch successore: `watch_id = _digest({"predecessor": old.watch_id, "candidate": candidate.candidate_id})`.
   - Registra il successore tramite `create_watch` (`worker.py:519-531`), collegandolo all'antenato con `supersedes_watch_id=old.watch_id`.
   - Il nuovo watch nasce nello stato: `lifecycle="candidate"`, `quality="provisional"`, `evidence_applicable=False`, `eligibility_decision=None`.
   - Eredita i campi `muted` e `priority` dal predecessore. Se il predecessore era in pausa (`lifecycle="paused"`), il nuovo watch eredita lo stato di pausa.

5. **Emissione di un nuovo run (`Worker._discover_refresh`, righe 544-554):**
   - Se il candidato è eseguibile, il worker accoda un job `run`:
     ```python
     self.queue.enqueue(
         f"evaluate/{candidate.candidate_id}/{snap.snapshot_id}",
         {
             "kind": "run",
             "graph": candidate.graph.model_dump(mode="json"),
             "snapshots": {profile.source_id: snap.model_dump(mode="json")},
             "as_of": snap.as_of.isoformat(),
         },
         lease_guard=job.guard,
     )
     ```
   - All'esecuzione di questo job, `runtime.run(...)` calcola le previsioni sul nuovo orizzonte e produce un `RunRecord` immutabile.

6. **Assenza di riqualifica automatica (Gap attuale):**
   - **Il worker non accoda né esegue alcun backtest di riqualifica.**
   - Nel sistema attuale, la qualifica (`assess_candidate_backtest` in `src/forecast_anything/discovery/policy.py`, righe 179-270) avviene **unicamente** quando un operatore invoca esplicitamente il tool MCP `submit_backtest` (o API equivalente) indicando un `watch_id` (`src/forecast_anything/backtesting/service.py`, righe 241-277).
   - Di conseguenza, in assenza di un intervento manuale:
     - Il watch originale rimane permanentemente invalidato (`candidate_invalidated=True`, `evidence_applicable=False`).
     - Il watch successore rimane per sempre provvisorio (`lifecycle="candidate"`, `quality="provisional"`, `evidence_applicable=False`).
     - La qualifica operativa va persa al primo refresh dei dati.

7. **Scollegamento tra Question e Successore (Gap di Continuità):**
   - Il contratto `Question` (`src/forecast_anything/question_storage.py`, `migrations/011_persistent_questions.sql`) possiede un'identità stabile (`question_id`) e revisioni semantiche immutabili.
   - Tuttavia, i collegamenti operativi avvengono tramite `question_references` (`target_type="watch"`, `target_id=old_watch_id`).
   - Quando il worker crea il successore `new_watch_id` e il run `new_run_id`, non aggiorna alcun riferimento nella domanda. L'utente che interroga la domanda ritrova un riferimento a un watch ormai superato e invalidato.

### 1.2 Verifica dei controlli esistenti vs da implementare

| Controllo | Stato Attuale nel Codice | Gap da colmare in 6B |
| :--- | :--- | :--- |
| **Pausa (`paused`)** | Trattata in `advance_watch` (`watches.py:139-141`) e registrata su `questions.status` (`question_storage.py:7`). Se il vecchio watch era in pausa, il successore eredita `paused` (`worker.py:532-543`). | **Bug/Gap di scheduling:** `Worker._schedule_sources` (`worker.py:312-317`) controlla solo `superseded`, `unsupported`, `migration_reason` e `next_due_at > now`. **Non controlla `watch.lifecycle == "paused"`!** Se un watch è in pausa, il worker continua comunque a effettuare refresh schedulati della sua fonte. In 6B la pausa deve fermare la generazione di nuovo lavoro e, se la fonte non è condivisa con altre domande attive, sospendere il polling della fonte. |
| **Mute (`muted`)** | Booleano presente in `Watch` (`contracts.py:474`) e modificabile con patch (`watches.py:125-128`, `api/service.py:695-710`). Filtra l'emissione in `group_notifications` (`watches.py:202`). Ereditato dal successore (`worker.py:528`). | Oggi non esiste un'inbox durevole né un canale di consegna esterno. `muted` agisce solo su un helper di notifica in memoria. In 6B deve governare selettivamente le notifiche della domanda e la consegna webhook, lasciando inalterata l'esecuzione computazionale. |
| **Priorità (`priority`)** | Intero tra 0 e 5 (`contracts.py:475`), modificabile con evento `priority_changed` (`watches.py:129-130`). Ereditato dal successore (`worker.py:528`). Incluso nelle notifiche raggruppate (`watches.py:216`). | `JobQueue` oggi processa i job in ordine di enqueue (`claimed_at`, `created_at`), senza ordinamento per priorità. In 6B la priorità deve ordinare l'estrazione dalla coda e l'inbox, rimanendo rigorosamente scorrelata dalla qualifica (nessun abbassamento di soglia per domande ad alta priorità). |
| **Revoca del Grant / Fonti condivise** | In MCP (`mcp_adapter/server.py`), i tool verificano le fonti contro `FORECAST_ANYTHING_MCP_SOURCE_IDS`. | Disconnessione tra sessione e background: revocare una fonte in un client MCP non ferma il daemon locale del worker (`source_polling`), che continua autonomamente a scaricare dati. In 6B deve esserci una separazione esplicita tra autorizzazione della sessione assistente e sottoscrizione durevole del worker. |

---

## 2. Identità, gerarchia e tabella delle transizioni

### 2.1 Modello delle identità

Per garantire che la storia rimanga comprensibile e che la domanda ("Cosa è cambiato rispetto a ieri?") conservi stabilità nel tempo, separiamo rigorosamente cinque livelli di identità:

1. **ID stabile della domanda (`Question.question_id`):**  
   Identificatore immutabile generato alla creazione (derivato da hash deterministico o chiave cliente). Rappresenta l'oggetto di monitoraggio per l'utente, sopravvive a cambi di dati, versioni del modello e riavvii.
2. **Revisione semantica e metodologica (`QuestionRevision.revision`):**  
   Intero progressivo (1, 2, ...). Rappresenta l'intento esplicito dell'utente: significato, serie target, vincoli e metodo di selezione. Cambia **soltanto** con una modifica esplicita dell'utente tramite `revise_question`.
3. **Contenuto osservato e istante di cattura:**  
   - `SourceSpec` + `SourceRevision`: definizione della fonte, mapping e parametri di estrazione.  
   - `Snapshot` (`snapshot_id`, `as_of`, `content_hash`): congelamento immutabile dei record acquisiti a una precisa coordinata temporale.
4. **Lignaggio metodologico (`Candidate`):**  
   Grafo computazionale compilato (`GraphSpec`), provider (`timestral`, baseline), iperparametri, orizzonte e protocollo di valutazione (nodo target, nodo di riferimento, criterio MAE).
5. **Singolo Run (`RunRecord`):**  
   Istanza puntuale di calcolo di previsione (`run_id`), legata a specifici snapshot di input e all'istante `as_of`. Immutabile.

---

### 2.2 Tabella unificata delle transizioni di continuità

La seguente matrice copre tutti i casi operativi, specificando l'effetto sul prossimo lavoro, l'applicabilità delle evidenze, lo stato del sistema e la spiegazione per l'utente.

| Evento / Caso | Effetto sul prossimo lavoro | Applicabilità evidenze | Stato operativo (Lifecycle / Quality) | Spiegazione mostrata all'utente |
| :--- | :--- | :--- | :--- | :--- |
| **1. Refresh senza nuovi contenuti** (Hash dati o righe identiche) | Nessun nuovo run. Riprogramma la scadenza del polling a `now + refresh_seconds`. | **Valide e applicabili.** Le evidenze del backtest rimangono intatte. | `active` / `usable` | *"Dati invariati: la fonte è stata verificata ma non presenta nuove osservazioni. La qualifica e l'ultima previsione rimangono valide."* |
| **2. Avanzamento orizzonte / Scadenza intervallo** (`now >= next_due_at`) | Il worker accoda il job `source_refresh`. In attesa di lettura dati. | **Temporaneamente applicabili ma freschezza scaduta.** | `active` / `stale` (`reevaluation_required=True`) | *"Intervallo di aggiornamento scaduto: in attesa della nuova lettura programmata della fonte."* |
| **3. Append di osservazioni** (Nuovi timestamp futuri, passato immutato) | Ingestione nuovo `Snapshot`. Emette nuovo `RunRecord`. Se rientra nei criteri della *Continuity Policy* (v. Sezione 3), la qualifica viene mantenuta e viene programmata una verifica asincrona entro budget. | **Applicabili sotto policy di continuità** (o provvisorie se fuori budget/limite lease). | `active` / `usable` (con nota di continuità) oppure `evaluating` / `provisional` | *"Nuove osservazioni acquisite in coda: emessa nuova previsione. La qualifica operativa è mantenuta per continuità ed è stata verificata sui nuovi dati."* |
| **4. Dati tardivi** (Nuovi record inseriti retroattivamente in intervalli passati prima vuoti) | Ingestione nuovo snapshot. Verifica se i punti tardivi intersecano le finestre del backtest originale. Se sì, impone riqualifica. Emette previsione provvisoria. | **Sospese / Richiedono rivalutazione.** Non possono garantire l'assenza di lookahead leakage retroattivo. | `evaluating` / `provisional` | *"Dati storici pervenuti in ritardo: le serie temporali passate sono cambiate. La previsione corrente è provvisoria in attesa di rivalutazione."* |
| **5. Correzioni dei dati passati** (Valori modificati per timestamp già noti) | Ingestione nuovo snapshot. **Invalidazione obbligatoria** del candidato e delle evidenze storiche calcolate sui vecchi valori effettivi. Accoda nuovo backtest entro budget. | **Inapplicabili.** `candidate_invalidated=True`, `evidence_applicable=False`. | `evaluating` / `provisional` | *"Rettifica dei dati storici: valori passati modificati dalla fonte. La qualifica precedente è invalidata e richiede un nuovo backtest sui dati corretti."* |
| **6. Cancellazioni di dati passati** (Record rimossi retroattivamente) | Ingestione nuovo snapshot. Invalidazione completa delle evidenze e del candidato. Nuova previsione provvisoria solo se la serie minima è integra. | **Inapplicabili.** | `evaluating` / `provisional` | *"Dati storici cancellati o mancanti nella fonte: la qualifica precedente è invalidata e non può essere mantenuta."* |
| **7. Variazione di mapping, modello, orizzonte o policy** | Crea una **nuova revisione semantica** (`revision + 1`). Compila un nuovo `Candidate`. Richiede nuova qualifica completa su 30+ origini. | **Completamente inapplicabili** alla nuova revisione (rimangono archiviate e immutabili sulla vecchia revisione). | `candidate` / `provisional` | *"Modifica metodologica o di configurazione: creata la revisione {revision}. La domanda richiede una nuova qualifica iniziale prima di diventare attiva."* |
| **8. Fonte temporaneamente non disponibile** (Errore di rete, file bloccato, HTTP 5xx) | Registra fallimento in `source_polling` (`available=0`). Applica backoff esponenziale sui tentativi. Nessun nuovo run. | **Congelate all'ultimo stato noto.** Qualità degradata per mancata freschezza. | `active` / `degraded` (`reevaluation_required=True`) | *"Fonte non raggiungibile: conservata l'ultima previsione emessa, ma contrassegnata come degradata per mancato aggiornamento."* |
| **9. Errore durante l'esecuzione del modello** (Timestral OOM, timeout, crash binario) | Fallimento registrato nella `JobQueue`. Se transient riprova fino a max_attempts; se permanente, abortisce il run. **Nessun fallback silenzioso.** | Non applicabile al run fallito. Il watch degrada lo stato operativo. | `evaluating` (o `active`) / `degraded` con errore esplicito | *"Errore del provider di previsione (Timestral): {errore esplicito}. Nessuna previsione generata; la baseline dichiarata o l'errore restano visibili."* |

---

## 3. Preservazione della qualifica e proposta per la Continuity Policy

### 3.1 I tre esiti distinti da preservare
Per mantenere l'integrità scientifica ed evitare falsi positivi operativi, confermiamo la netta distinzione tra:
1. **Nuova emissione (`run`):**  
   Esecuzione del grafo su snapshot correnti. Produce proiezioni future (point, quantili, percorsi). **Non misura l'accuratezza e non qualifica il modello.**
2. **Backtest generico (`backtest` senza `watch_id`):**  
   Simulazione storica esplorativa per calcolare metriche e grafici. Non è vincolato a un candidato congelato e **non può attivare né qualificare un watch operativo.**
3. **Qualifica operativa (`assess_candidate_backtest` con `watch_id`):**  
   Valutazione fail-closed su almeno 30 finestre finali indipendenti e non sovrapposte. Esige che `mean_loss < mean_reference` (skill strettamente positiva rispetto alla baseline dichiarata). Solo questo esito consente lo stato `lifecycle="active"` e `quality="usable"`.

### 3.2 Inapplicabilità delle evidenze
Le evidenze diventano **immediatamente inapplicabili** nei seguenti casi:
- Qualsiasi correzione o cancellazione di osservazioni storiche utilizzate nelle partizioni di evaluation/final origin.
- Modifica del grafo computazionale, del provider (es. passaggio a Timestral senza adapter approvato), dell'orizzonte $H$ o dei parametri di baseline.
- Scadenza del periodo massimo di validità (lease temporale della qualifica).
- Evidenza empirica di perdita di skill rispetto alla baseline sulle osservazioni realizzate nel tempo corrente.

### 3.3 Proposta: `ContinuityPolicy` versionata (`continuity-v1`)

Per consentire che un append ordinario di osservazioni mantenga attiva una domanda senza obbligare l'utente a rifare un backtest manuale ogni giorno (o degradare istantaneamente il sistema a provvisorio), introduciamo la specifica della policy **`continuity-v1`**:

```
                                  APPEND RILEVATO
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
              [Passato Immutato?]               [Passato Alterato?]
               (Prefix Check OK)                (Correzioni/Drop)
                         │                             │
                         ▼                             ▼
              [Lease Qualifica Valido?]           [INVALIDA EVIDENZE]
               (< 30 giorni / N cicli)            Stato: provisional
                         │                        Re-evaluation immediata
                         ▼
             ┌───────────┴───────────┐
             ▼                       ▼
      [Budget Disponibile]    [Budget Esaurito]
             │                       │
             ▼                       ▼
    Accoda Verifica Auto     Mantieni Previsione
    su Nuova Origine         con Lease Residuo
    (Rolling Holdout)        (Stato: usable con nota)
```

#### Regole e condizioni formali di `continuity-v1`:
1. **Verifica di integrità del prefisso storico:**  
   Il worker confronta il contenuto storico: se il nuovo snapshot contiene tutte le osservazioni dello snapshot precedente con identico valore, timestamp e serie (puro append), il prefisso è valido.
2. **Condizioni di mantenimento:**  
   Se il prefisso è integro, il candidato non è variato e il tempo trascorso dall'ultimo backtest completo è inferiore a `max_qualification_age` (predefinito: 30 giorni o 30 append), il watch transita a `active` / `usable` con motivazione `continuity_v1_maintained`.
3. **Verifica automatica entro budget (`bounded_recheck`):**  
   - Non viene eseguito un intero backtest da zero a ogni refresh (per non saturare la CPU/GPU locale o sforare il budget Timestral).
   - Se sono trascorsi almeno $K$ intervalli e le nuove osservazioni permettono di valutare una previsione passata emessa per quell'istante, il worker valuta l'errore realizzato rispetto alla baseline.
   - Se la perdita cumulativa sul rolling window supera la baseline (`rolling_skill <= 0`), la continuità decade immediatamente: `kind="quality_degraded"`, `evidence_applicable=False`, `reevaluation_required=True`.
4. **Immutabilità delle decisioni passate:**  
   I record `EligibilityDecision` storici **non vengono mai sovrascritti o modificati**. Viene registrato un nuovo record di audit `ContinuityAssessment` collegato all'evento.

---

## 4. Definizione dei controlli e separazione dei grant

In 6B i controlli operano con confini precisi tra calcolo, consegna e autorizzazioni:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        LIVELLI DI CONTROLLO                           │
├────────────────────────────────────────────────────────────────────────┤
│ 1. PAUSA (Domanda / Watch)                                             │
│    └─ Governa la GENERAZIONE di nuovo lavoro computazionale.            │
│       - Arresta nuovi run, backtest e refresh non condivisi.          │
│       - Lavoro già in coda: completa la fase protetta senza chaining.  │
├────────────────────────────────────────────────────────────────────────┤
│ 2. MUTE (Notifiche / Consegna)                                         │
│    └─ Governa l'EMISSIONE di notifiche esterne ed eventi inbox.        │
│       - Il calcolo, i refresh e le previsioni proseguono normalmente.  │
│       - L'inbox registra con flag muted; i webhook non sparano.        │
├────────────────────────────────────────────────────────────────────────┤
│ 3. PRIORITÀ (Scheduling)                                               │
│    └─ Governa l'ORDINE di prelazione in coda e l'ordinamento UI.        │
│       - Zero impatto sulle soglie di qualifica scientifica.            │
├────────────────────────────────────────────────────────────────────────┤
│ 4. AUTORIZZAZIONI (Grant Sessione vs Sottoscrizione Worker)            │
│    ├─ MCP Session Grant: autorizza le letture dell'assistente.         │
│    └─ Durable Polling Subscription: autorizza il fetch autonomo daemon.│
└────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Pausa (`pause_question` / `pause_watch`)
- **Effetto sul nuovo lavoro:** nessun nuovo run, backtest o job di discovery viene accodato per la domanda o per il watch.
- **Effetto sul lavoro già accettato:** un job già preso in carico da un worker (`state='running'`, protetto da lease) viene lasciato completare per preservare la coerenza transazionale, ma non innesca i job successivi della catena (nessun `discover_refresh` o `run` a cascata).
- **Effetto sulle letture programmate e fonti condivise:**
  - Se la fonte dati è utilizzata anche da altre domande non in pausa, il worker continua a eseguire il `source_refresh` programmato per soddisfare le altre domande.
  - Se tutti i watch e le domande che dipendono da quella fonte sono in pausa, lo scheduling in `source_polling` viene sospeso.
- **Ripresa (`resume`):** la ripresa riesamina lo stato: se la fonte è cambiata durante la pausa, aggiorna il watch a `stale` o provvisorio ed esegue un refresh controllato.

### 4.2 Mute (`mute_question` / `mute_watch`)
- **Effetto:** governa unicamente la **consegna delle notifiche**.
- **Indipendenza computazionale:** il worker continua a monitorare la fonte, emettere previsioni qualificate, aggiornare la storia e monitorare la qualità.
- Gli eventi continuano a essere scritti nell'Inbox durevole del ledger, ma con stato `muted=True` (nessuna notifica push, nessun dispatch webhook).
- Alla riapertura della chat o all'ispezione della console, l'utente può ritrovare tutti gli eventi registrati.

### 4.3 Priorità (`priority`)
- Valore compreso tra 0 (massima priorità) e 5 (bassa).
- Assegna priorità di estrazione nella `JobQueue` (`ORDER BY priority ASC, run_after ASC, job_id ASC`).
- Determina l'ordinamento visivo nell'Inbox e nelle viste compatte/estese.
- **Invariante:** la priorità non ha alcun impatto sui criteri di qualifica (30 origini, MAE < baseline).

### 4.4 Distinzione tra Grant MCP e Sottoscrizione Programmata della Fonte
Oggi esiste ambiguità tra le fonti concesse al client MCP (`FORECAST_ANYTHING_MCP_SOURCE_IDS`) e le letture schedulate in background dal worker.  
In 6B questa distinzione viene resa formale ed esplicita nel core:
1. **MCP Session Grant:** autorizzazione concessa all'istanza dell'assistente/chat per leggere metadati, ispezionare preview e invocare tool su determinate fonti.
2. **Durable Source Subscription:** record formale nel ledger (`source_subscriptions`) che autorizza il worker daemon ad accedere periodicamente alla fonte (es. file system locale o endpoint HTTP autorizzato) anche ad assistente chiuso.
3. **Revoca del Grant:**
   - La revoca dell'accesso in chat impedisce all'assistente di consultare la fonte.
   - La cancellazione/revoca della sottoscrizione di background ferma immediatamente il polling in `source_polling`, rimuove i job pendenti e imposta lo stato dei watch dipendenti a `lifecycle="unsupported"` con motivazione esplicita `source_subscription_revoked`.

---

## 5. Piano di accettazione per la Fase 6B

### 5.1 Esempi Prima / Dopo

#### Scenario A: Append ordinario di un nuovo giorno di dati
- **Prima (Fase 5):** Il worker scarica il nuovo snapshot. `advance_watch` chiama `source_revised`, invalidando istantaneamente il candidato e le evidenze. Il successore rimane provvisorio senza evidenze. L'utente torna in chat, chiede *"Cosa è cambiato rispetto a ieri?"* e riceve una previsione non operativa con avviso di qualifica decaduta.
- **Dopo (Fase 6B):** Il worker scarica il nuovo snapshot. La `continuity-v1` rileva che il passato è integro e che il lease è valido. Emette il nuovo run con identità della domanda preservata, genera un evento durevole nell'Inbox (`"Aggiornamento giornaliero completato con evidenze confermate"`), aggiorna il puntatore della domanda al nuovo run e invia (se configurato) il webhook con ID stabile di deduplicazione.

#### Scenario B: Rettifica di un valore passato (es. correzione ISTAT o vendita rettificata)
- **Prima (Fase 5):** Generava un successore provvisorio senza spiegare all'utente perché i dati storici avevano causato l'invalidazione.
- **Dopo (Fase 6B):** La policy di continuità rileva la discrepanza sul prefisso storico. Segnala esplicitamente: *"Rettifica dati passati rilevata: 3 valori modificati tra il 2026-10-01 e il 2026-10-03. La qualifica precedente non è applicabile."* Accoda un job di backtest riqualificativo controllato da budget, lasciando lo stato provvisorio chiaramente motivato nell'Inbox e nelle viste.

---

### 5.2 Suite di prove previste per 6B

La fase 6B sarà verificata tramite una matrice rigorosa di test:

| Ambito di Prova | Tipologia | Descrizione del Test | Criterio di Successo |
| :--- | :--- | :--- | :--- |
| **1. Aggiornamento ordinario (Append)** | Deterministica (fixture `seasonal_naive`) | Ingestione di nuove righe con prefisso immutato. Applicazione di `continuity-v1`. | Question ID invariato, nuovo run collegato, qualifica attiva preservata, evento inbox emesso. |
| **2. Rettifica dati storici** | Deterministica | Modifica retroattiva di un valore passato in una partizione di test. | `evidence_applicable=False`, stato provvisorio esplicito, spiegazione dettagliata nell'inbox. |
| **3. Evidenza insufficiente** | Deterministica | Backtest automatico su meno di 30 origini o con dati mancanti. | Decisione `provisional`, `reason_codes=('insufficient_final_origins',)`, nessuna attivazione indebita. |
| **4. Perdita della qualifica** | Deterministica | Modello che ottiene MAE peggiore della baseline (`mean_loss >= mean_reference`). | Decisione `reject` con codice `nonpositive_final_skill`, stato watch `evaluating`/`provisional` visibile. |
| **5. Concorrenza e idempotenza** | Concorrente (multi-thread/process) | Due refresh concorrenti della stessa fonte e arrivo contemporaneo di job. | Una sola esecuzione vince tramite lease e emission key fencer; nessun duplicato nell'inbox. |
| **6. Retry, Crash e Riavvio** | Fault injection | Crash del processo worker durante l'ingestione o durante il calcolo del run; riavvio del daemon. | Il job viene ripreso tramite il lease fencer e completato senza perdita di eventi o duplicazione di stati. |
| **7. Controlli: Pausa, Mute, Priorità** | Deterministica | Mute su una domanda (webhook soppresso, inbox archiviata); Pausa (calcolo bloccato, ripresa ordinata); Priorità (ordine di esecuzione verificato). | Rispettati esattamente i contratti definiti nella Sezione 4. |
| **8. Webhook opt-in durevole** | Integrazione con mock HTTP receiver | Registrazione webhook locale di test. Invio con outbox durevole, gestione fallimento HTTP 500, retry esponenziale, deduplicazione con `X-Forecast-Event-Id`. | Tre tentativi con backoff, consegna confermata al ripristino del receiver; nessun payload perso. |
| **9. Inferenza reale Timestral** | Live model (Timestral locale pinned) | Esecuzione su fonte reale con pesi Timestral locali congelati. Confronto con baseline stagionale. | Inferenza reale completata o stato di errore/degradazione esplicito e verificabile se il modello fallisce. |
| **10. E2E Assistente Chiuso** | End-to-end su processi reali | Assistente spento. Aggiornamento esterno della fonte sintetica. Daemon worker (LaunchAgent/background) elabora autonomamente. Webhook riceve evento. Riapertura assistente / riconnessione MCP. | L'assistente legge la domanda tramite MCP, recupera l'evento dall'Inbox e risponde correttamente a *"Cosa è cambiato rispetto a ieri?"*. |
