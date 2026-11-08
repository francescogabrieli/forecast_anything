# Phase 6A: Contratto di Continuità, Qualifica e Controlli delle Domande (Revisione 2)

**Base di partenza:** `400239ccdda02a362c3b809b05650aa28afa481a` (`origin/main`, che unisce la PR #22 e include il commit finale della fase 5 `617e8a948ae9bdc3afc79540cf9d56b66c5b9c53`).  
**Worktree e branch dedicati:** branch `codex/phase-6-continuity-updates` in `/private/tmp/forecast-phase6-continuity-updates`.  
**Stato:** Checkpoint 6A revisionato in base al feedback. Nessun codice della fase 6B implementato in anticipo.

---

## 1. Stato attuale del codice e ricostruzione del flusso

### 1.1 Ricostruzione del flusso quando il worker aggiorna la fonte di una domanda qualificata

L'esecuzione in background è gestita da `Worker` (`src/forecast_anything/worker.py`), che coordina lo scheduling delle fonti, l'ingestione, l'invalidazione dei watch e l'eventuale discovery provvisoria:

1. **Schedulazione della lettura (`Worker._schedule_sources`, righe 307-356):**
   - Il worker controlla la tabella `watches` per i watch in cui `next_due_at <= now` e che non siano contrassegnati come superseded (`watch.watch_id in superseded`), non in lifecycle `unsupported` e privi di `migration_reason`.
   - Per ciascun `source_id` dipendente, calcola la scadenza minima (`due[source_id] = min(...)`).
   - Verifica la tabella `source_polling` e accoda un job `source_refresh` nella `JobQueue` con chiave deterministica ed emission key `refresh/{source_id}/{registered.revision}/{deadline.isoformat()}`.

2. **Ingestione della fonte e cattura del nuovo snapshot (`Worker._refresh_source`, righe 381-462):**
   - Viene verificata la corrispondenza con la revisione registrata nel `SourceCatalog` (`catalog.get`).
   - Se il job non contiene già uno snapshot congelato, invoca `ingest_source(registered.spec, ...)` per produrre un nuovo `Snapshot` immutabile e `inspect_source(...)` per derivare il `SourceProfile`.
   - Il nuovo snapshot viene persistito nel ledger (`ledger.put_snapshot`).
   - **In caso di errore I/O o di rete:** aggiorna `source_polling` impostando `available=False` e invoca `advance_watch` con evento `{"kind": "quality_degraded"}` per tutti i watch collegati (`worker.py:413-422`).
   - **In caso di successo:** itera su tutti i watch collegati a `payload["source_id"]`. Se lo snapshot `snap.snapshot_id` non è già presente in `watch.source_snapshot_ids`, esegue:
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
   - L'evento `source_revised` invalida all'istante la qualifica del watch esistente:
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
   - Anche se il watch era `operational` (qualificato con backtest su 30+ origini finali contro baseline), l'arrivo del nuovo snapshot lo degrada istantaneamente a `evaluating`, `quality="stale"`, `evidence_applicable=False`, `candidate_invalidated=True` e archivia gli `evaluation_ids` tra quelli invalidati.

4. **Accodamento e compilazione del successore (`Worker._discover_refresh`, righe 463-560):**
   - Subito dopo l'invalidazione, `_refresh_source` accoda un job `discover_refresh` (`worker.py:443-452`).
   - `_discover_refresh` calcola un nuovo `epoch_id = _digest({"predecessor": old.candidate_id, ..., "snapshot": snap.snapshot_id})`.
   - Compila una nuova proposta di candidato (`compile_proposal`) con un nuovo `candidate_id`.
   - Crea una nuova `DiscoveryEpoch` con `source_snapshot_ids=(snap.snapshot_id,)` e `final_origin_ids=()`. Le origini finali passate non vengono mai riutilizzate (principio anti-leakage Plan 02/08).
   - Genera un nuovo ID per il watch successore: `watch_id = _digest({"predecessor": old.watch_id, "candidate": candidate.candidate_id})`.
   - Registra il successore tramite `create_watch` (`worker.py:519-531`), collegandolo all'antenato con `supersedes_watch_id=old.watch_id`.
   - Il nuovo watch nasce nello stato: `lifecycle="candidate"`, `quality="provisional"`, `evidence_applicable=False`, `eligibility_decision=None`.
   - Eredita i campi `muted` e `priority` dal predecessore. Se il predecessore era in pausa (`lifecycle="paused"`), il nuovo watch eredita lo stato di pausa.

5. **Emissione di un nuovo run puntuale (`Worker._discover_refresh`, righe 544-554):**
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
   - Il job chiama `runtime.run(...)` calcolando le previsioni sul nuovo orizzonte ed emettendo un `RunRecord` immutabile.

6. **Assenza di riqualifica automatica (Comportamento attuale del codice):**
   - Il worker **non accoda né esegue alcun backtest di riqualifica**.
   - Nel sistema attuale, `assess_candidate_backtest` (`src/forecast_anything/discovery/policy.py`, righe 179-270) viene eseguito solo quando un operatore invoca esplicitamente `submit_backtest` con parametro `watch_id` (`src/forecast_anything/backtesting/service.py`, righe 241-277).
   - Di conseguenza, oggi:
     - Il watch originale rimane per sempre invalidato.
     - Il watch successore rimane per sempre provvisorio senza evidenze.
     - La qualifica operativa decade al primo refresh dei dati.

7. **Scollegamento della Domanda (`Question`) dal successore:**
   - La `Question` (`question_storage.py`, `migrations/011_persistent_questions.sql`) possiede un'identità stabile (`question_id`), ma i collegamenti operativi in `question_references` rimangono fissati sul vecchio `watch_id`. Il successore e il nuovo run restano non collegati alla domanda.

---

## 2. Separazione concettuale: Polling, Freschezza e Evidenze

Un aspetto cruciale chiarito nella revisione è la **rigorosa separazione tra tre dimensioni temporali distinte**, che non devono mai essere confuse tra loro:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TRE DIMENSIONI TEMPORALI                        │
├────────────────────────────────────────────────────────────────────────┤
│ 1. PROSSIMO POLLING DELLA FONTE (next_due_at / Cadenza I/O)             │
│    Scadenza puramente tecnica di scheduling: quando il worker deve     │
│    interrogare la sorgente per verificare la presenza di nuovi dati.   │
├────────────────────────────────────────────────────────────────────────┤
│ 2. FRESCHEZZA DELLA PREVISIONE (Orizzonte temporale vs Tempo Corrente)  │
│    Riguarda i timestamp (T_1..T_H) coperti dall'ultimo RunRecord:     │
│    - now <= max(timestamps): previsione temporalmente valida/fresca.    │
│    - now > max(timestamps): PREVISIONE SCADUTA (horizon_expired),       │
│      anche se i dati sorgente sono identici e il polling è recente!    │
├────────────────────────────────────────────────────────────────────────┤
│ 3. APPLICABILITÀ DELLE EVIDENZE (Lineage scientifico del Candidato)    │
│    Attesta che il candidato ha dimostrato skill positiva (MAE < base)  │
│    su >= 30 origini finali non sovrapposte e prive di leakage.        │
│    È indipendente dal fatto che l'orizzonte sia fresco o scaduto.      │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Effetto di un refresh con dati identici
Un refresh della fonte che riscontra dati identici (nessuna nuova riga, hash invariato):
- **Aggiorna il prossimo polling:** sposta `next_due_at` in avanti a `now + refresh_seconds`.
- **NON rinnova la freschezza della previsione:** se l'orizzonte della previsione precedente è già trascorso nel tempo (`max(timestamps) < now`), la previsione **diventa scaduta (`horizon_expired`)**. Non esistono proiezioni attive per il futuro. Il sistema segnala esplicitamente: *"La fonte è invariata, ma l'orizzonte della previsione precedente è trascorso nel passato. Nessuna previsione attiva per date future."*
- **Non tocca le evidenze storiche:** le evidenze del backtest originale rimangono integre e immutate nel ledger.

### 2.2 Criteri completi per classificare un "Append"
Un aggiornamento viene classificato come **Append valido** solo se soddisfa congiuntamente tutte le seguenti verifiche sul nuovo `Snapshot` rispetto al precedente:
1. **Integrità dei record passati (`event_time` e `value`):** tutte le osservazioni presenti nello snapshot precedente compaiono nel nuovo snapshot con identico timestamp, valore e serie.
2. **Monotonia temporale dei nuovi arrivi:** tutti i record aggiunti hanno `event_time > max(previous_event_times)`. Non è ammesso alcun inserimento retroattivo.
3. **Disponibilità temporale (`available_at`):** per ogni nuovo record, `available_at <= now` e rispetta le regole di consistenza temporale (nessun punto retro-datato come disponibile prima del tempo reale).
4. **Stabilità delle revisioni (`revision`):** i campi `revision` dei record storici passati rimangono rigorosamente identici (nessun cambio di etichetta o ricalcolo).
5. **Invarianza del mapping e delle specifiche (`mapping`):** il mapping applicato (colonne, frequenza, fuso orario, calendario, conversioni di unità) è identico al profilo con cui è stato compilato il candidato.

Se anche una sola di queste verifiche fallisce (es. un valore passato corretto, un record inserito in una data passata, un mapping modificato o una revisione alterata), l'operazione **NON è un append**: viene classificata come **Rettifica** o **Mutazione**, con invalidazione immediata di candidato ed evidenze.

---

## 3. Qualifica vincolata al candidato nel primo 6B e Transizioni

### 3.1 Preservazione della qualifica nel primo 6B
Nel primo rilascio della fase 6B:
- **La qualifica rimane strettamente vincolata al candidato congelato**, nel pieno rispetto dei criteri fail-closed di Plan 02 e Plan 08.
- Quando si verifica un **Append valido**:
  1. La **domanda conserva il proprio ID stabile (`question_id`)**.
  2. Viene emesso il nuovo run per il nuovo orizzonte e **collegato immediatamente alla domanda**.
  3. Lo stato della domanda/watch **è e rimane esplicitamente PROVVISORIO (`quality="provisional"`, `lifecycle="evaluating"`, `evidence_applicable=False`)** fino all'acquisizione della nuova qualifica.
  4. Viene programmato un job di **riqualifica automatica entro budget**.
  5. L'utente vede nella chat, nelle viste e nell'Inbox:  
     *"Previsione aggiornata emessa sui nuovi dati. Lo stato resta provvisorio in attesa della riqualifica scientifica su nuove origini."*
  6. Quando il job di riqualifica completa con successo la valutazione su almeno 30 origini finali con `mean_loss < mean_reference`, la qualifica transita a `active` / `usable`.

### 3.2 Spostamento di `continuity-v1` tra le proposte future
La proposta di policy `continuity-v1` (mantenimento presuntivo della qualifica attiva durante un append ordinario) viene formalmente **spostata tra le estensioni future**.  
Prima di poterla introdurre saranno necessari:
1. **Regola di scadenza precisa (TTL):** un limite temporale e di cicli rigidamente provato oltre il quale la qualifica non può essere estesa senza backtest completo.
2. **Criteri oggettivi di confronto con la baseline sui dati realizzati:** una metrica formale per calcolare in tempo reale l'errore delle previsioni man mano che gli effettivi si materializzano, con revoca istantanea se il modello perde contro la baseline.
3. **Comportamento deterministico in caso di esiti mancanti o insufficienti:** regole stringenti che impediscano qualsiasi assunzione tacita di validità quando i dati effettivi non sono disponibili.

---

### 3.3 Matrice completa delle transizioni di continuità

| Evento / Caso | Effetto sul prossimo lavoro | Applicabilità evidenze | Stato operativo | Spiegazione mostrata all'utente |
| :--- | :--- | :--- | :--- | :--- |
| **1. Refresh senza nuovi contenuti** (Dati identici) | Riprogramma polling a `now + refresh_seconds`. Nessun nuovo run. | Evidenze storiche intatte e valide. | Se orizzonte ancora futuro: `active` / `usable`. Se orizzonte trascorso: `active` / `stale` (`horizon_expired`). | *Se orizzonte futuro:* "Dati invariati: la fonte è verificata e la previsione resta valida."<br>*Se orizzonte passato:* "Dati invariati, ma l'orizzonte dell'ultima previsione è trascorso nel passato. Nessuna previsione attiva per date future." |
| **2. Scadenza intervallo polling** (`now >= next_due_at`) | Accoda job `source_refresh`. In attesa di lettura. | Evidenze intatte; freschezza polling scaduta. | `active` / `stale` (`reevaluation_required=True`) | "Intervallo di aggiornamento della fonte scaduto: in attesa della nuova lettura programmata." |
| **3. Append valido** (Nuovi punti futuri, passato/mapping/revisioni immutati) | Ingestione nuovo snapshot. Emette nuovo `RunRecord` collegato alla domanda. **Accoda riqualifica entro budget.** | **Non ancora applicabili al nuovo run (Stato provvisorio).** | `evaluating` / `provisional` (`evidence_applicable=False`) | "Nuove osservazioni acquisite in coda: emessa nuova previsione per il nuovo orizzonte. Lo stato resta provvisorio in attesa della riqualifica sulle nuove origini." |
| **4. Dati tardivi** (Nuovi record inseriti retroattivamente nel passato) | Ingestione nuovo snapshot. Rileva intersezione con partizioni passate. Emette run provvisorio. Accoda riqualifica. | Sospese / Richiedono rivalutazione per rischio lookahead leakage. | `evaluating` / `provisional` | "Dati storici pervenuti in ritardo: le serie temporali passate sono cambiate. La previsione corrente è provvisoria in attesa di rivalutazione." |
| **5. Correzioni dati passati** (Valori o revisioni modificati per date note) | Ingestione snapshot. **Invalidazione obbligatoria** del candidato e delle evidenze. Accoda nuovo backtest entro budget. | **Inapplicabili.** `candidate_invalidated=True`, `evidence_applicable=False`. | `evaluating` / `provisional` | "Rettifica dei dati storici: valori passati modificati dalla fonte. La qualifica precedente è invalidata e richiede un nuovo backtest sui dati corretti." |
| **6. Cancellazioni dati passati** (Record rimossi retroattivamente) | Ingestione snapshot. Invalidazione completa di candidato ed evidenze. | **Inapplicabili.** | `evaluating` / `provisional` | "Dati storici cancellati o mancanti nella fonte: la qualifica precedente è invalidata e non può essere mantenuta." |
| **7. Variazione mapping, modello o orizzonte** | Crea **nuova revisione semantica** (`revision + 1`). Compila nuovo `Candidate`. | **Completamente inapplicabili** alla nuova revisione. | `candidate` / `provisional` | "Modifica metodologica o di configurazione: creata la revisione {revision}. La domanda richiede una qualifica iniziale prima di diventare attiva." |
| **8. Fonte temporaneamente non disponibile** (Errore di rete / HTTP 5xx) | Fallimento registrato in `source_polling`. Backoff esponenziale sui retry. Nessun nuovo run. | Evidenze congelate; qualità degradata per mancato aggiornamento. | `active` o `evaluating` / `degraded` | "Fonte non raggiungibile: conservata l'ultima previsione emessa, ma contrassegnata come degradata per mancato aggiornamento." |
| **9. Errore provider modello** (Timestral OOM, timeout, crash binario) | Fallimento registrato in `JobQueue`. Retry se transient, stop se permanente. **Nessun fallback silenzioso.** | Non applicabile al run fallito. | `evaluating` / `degraded` con errore esplicito | "Errore del provider di previsione (Timestral): {errore esplicito}. Nessuna previsione generata; la baseline dichiarata o l'errore restano visibili." |

---

## 4. Tabella dei Controlli e Fonti Condivise

I controlli sono specificati distinguendo tre stati temporali di esecuzione e documentando l'impatto esatto sulle **fonti condivise** e sulle **consegne webhook in coda**:

| Controllo | Lavoro in coda (`pending`) | Lavoro in esecuzione (`running`) | Job successivi (`chained / downstream`) | Effetto su fonti condivise | Effetto su Inbox e Consegne Webhook |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Pausa Domanda / Watch** (`pause_question`) | I job pendenti specifici della domanda (`run`, `backtest`) vengono rimossi o saltati al momento del claim. | Il job in esecuzione completa la sua fase protetta (il lease fencer evita corruzioni), ma il worker non genera nuovi job successivi. | Soppressi: nessun `discover_refresh`, `evaluate` o chained `run` viene generato per la domanda. | **Sulla domanda in pausa:** nessun calcolo.<br>**Sulle ALTRE domande attive che usano la stessa fonte:** il worker continua normalmente il polling della fonte e i relativi run.<br>*Sospensione polling fonte solo se TUTTE le domande dipendenti sono in pausa.* | Gli eventi storici restano consultabili. Nessun nuovo evento di run emesso durante la pausa. |
| **Mute Domanda / Watch** (`mute_question`) | **Nessun impatto:** i job in coda vengono elaborati normalmente al loro turno. | **Nessun impatto:** l'esecuzione del calcolo, refresh e backtest procede normalmente. | **Nessun impatto:** la catena computazionale prosegue completa. | **Nessun impatto sulle fonti o sulle altre domande.** | **Inbox:** gli eventi continuano a essere registrati durevolmente nel ledger, ma contrassegnati con `muted=True`.<br>**Webhook in coda:** se un job di consegna webhook per la domanda è già pendente nella outbox queue, al momento dell'estrazione il worker verifica lo stato mute: **la consegna viene soppressa / scartata (`delivery_suppressed_muted`)**, evitando invii esterni indesiderati. |
| **Priorità** (`priority: 0..5`) | Riordina i job pendenti nella coda (`ORDER BY priority ASC, run_after ASC`). | Nessun impatto (il job running non viene interrotto). | I job downstream ereditano la priorità configurata. | Nessun impatto sulle altre domande, eccetto la precedenza di scheduling quando la coda è contesa. | Determina l'ordinamento visivo nell'Inbox e nelle viste. **Invariante:** zero impatto sui criteri o sulle soglie di qualifica scientifica. |
| **Revoca Sottoscrizione Fonte** (`revoke_source_subscription`) | Cancellati immediatamente tutti i job pendenti di `source_refresh` e run collegati a quella fonte. | Se un refresh è in corso, termina senza aggiornare o viene abortito. | Soppressi tutti i job downstream. | **Impatto globale sulla fonte:** arresta il polling in background per **tutte** le domande che dipendono da quella fonte. Tutte le domande dipendenti transitano a `lifecycle="unsupported"` con motivazione `source_subscription_revoked`. | Viene registrato un evento nell'Inbox per ciascuna domanda impattata. |

---

## 5. Verificabilità del Budget e Recupero del Webhook

### 5.1 Regole e limiti del Budget di Riqualifica
Il budget di riqualifica è strutturato con vincoli verificabili e deterministici:
- `max_requalification_jobs_per_window`: massimo 1 job di backtest automatico ogni 24 ore per ciascuna domanda.
- `max_origins_per_recheck`: blocco di valutazione compreso tra 30 (minimo per significatività) e 60 origini.
- `max_execution_seconds`: timeout rigido di 300 secondi per il calcolo del backtest.

#### Comportamento nei casi limite del budget:
1. **Mancanza di nuove finestre finali (storia insufficiente):**  
   Se dopo un append il numero di nuove finestre finali indipendenti e non sovrapposte è inferiore a 30 (`new_final_origins < 30`):
   - Il worker **non accoda un backtest fittizio né forza una qualifica parziale**.
   - Lo stato della domanda **resta provvisorio (`quality="provisional"`, reason code `insufficient_final_origins`)**.
   - Spiegazione visibile: *"Previsione calcolata sui dati aggiornati; lo stato resta provvisorio poiché la storia accumulata dall'ultimo backtest ({N} origini) non è ancora sufficiente per un nuovo blocco di qualifica indipendente (minimo 30)."*
2. **Esaurimento del budget computazionale / quota:**  
   Se il limite di job o il tempo massimo di calcolo per la finestra corrente è superato:
   - Il sistema **non va in crash e non entra in loop di retry**.
   - Il job di riqualifica viene rinviato alla finestra successiva (`next_due_at = now + budget_cooldown`).
   - Lo stato della previsione resta provvisorio con codice `requalification_budget_exhausted`.
   - Spiegazione visibile: *"Budget computazionale di riqualifica esaurito per la finestra corrente. Nuova verifica programmata per {prossima_finestra}."*

---

### 5.2 Recupero, Deduplicazione e Fallimento del Webhook

1. **Persistenza dell'ID e Deduplicazione dopo Crash:**
   - Ogni evento dell'Inbox possiede un identificatore immutabile e deterministico calcolato al momento dell'emissione:
     $$\text{event\_id} = \text{sha256}(f"\text{inbox}/\{\text{question\_id}\}/\{\text{revision}\}/\{\text{run\_id}\}/\{\text{decision\_id}\}")$$
   - L'Outbox registra il job di consegna con questo `event_id`.
   - L'header HTTP inviato include obbligatoriamente:
     `X-Forecast-Event-Id: {event_id}`
   - **Comportamento dopo un crash:** se il worker o il sistema si arresta mentre la richiesta HTTP è in transito o prima della scrittura di conferma, al riavvio il worker recupera il record dall'Outbox tramite il lease fencer e ripete l'invio con **lo stesso identico `event_id`**. Il ricevente del webhook può scartare il duplicato controllando `X-Forecast-Event-Id`.

2. **Gestione Retry e Fallimento Definitivo:**
   - La coda Outbox esegue al massimo 3 tentativi con backoff esponenziale (es. dopo 30s, 120s, 600s) in caso di errori di rete o risposte HTTP 5xx.
   - **Dopo l'ultimo tentativo fallito:**
     - La consegna transita a `state='delivery_failed'` con timestamp, codice di errore e risposta registrati nel ledger.
     - I retry automatici si arrestano definitivamente (nessun ciclo infinito).
     - **L'evento nell'Inbox locale rimane integro e non viene perso**: l'utente o l'assistente possono consultarlo via MCP o console web, con evidenza esplicita del fallimento webhook (`webhook_delivery="failed"`).

---

## 6. Piano di accettazione aggiornato per la Fase 6B

| Ambito di Prova | Tipologia | Descrizione del Test | Criterio di Successo |
| :--- | :--- | :--- | :--- |
| **1. Append ordinario e Riqualifica provvisoria** | Deterministica (`seasonal_naive`) | Ingestione nuove righe con prefisso, mapping e revisioni immutati. Emette nuovo run. | Question ID preservato, run collegato, stato **provvisorio** esposto finché la riqualifica non completa. |
| **2. Refresh con dati identici ed orizzonte scaduto** | Deterministica | Polling fonte identica quando `now > max(timestamps)` della previsione. | Prossimo polling avanzato, ma stato previsione **`horizon_expired` / `stale`**, spiegazione utente chiara. |
| **3. Rettifica retroattiva e invalidazione** | Deterministica | Modifica di un valore o revisione passata. | Candidato invalidato, `evidence_applicable=False`, stato provvisorio motivato con spiegazione rettifica. |
| **4. Mancanza di finestre finali (< 30)** | Deterministica | Riqualifica automatica con meno di 30 origini nuove. | Nessun backtest forzato, stato resta provvisorio con `insufficient_final_origins`. |
| **5. Esaurimento budget di riqualifica** | Deterministica | Superamento limite giornaliero job di backtest. | Nessun loop o crash; stato provvisorio con `requalification_budget_exhausted` e riprogrammazione al cooldown. |
| **6. Perdita della qualifica (MAE >= Baseline)** | Deterministica | Backtest automatico in cui il modello perde contro la baseline. | Decisione `reject` con codice `nonpositive_final_skill`, stato watch provvisorio visibile. |
| **7. Controlli: Pausa, Mute, Priorità e Fonti Condivise** | Deterministica | Due domande sulla stessa fonte: pausa su una sola (l'altra continua i run; il polling continua finché la seconda è attiva). Mute: soppressione consegna webhook pendente in outbox e conservazione evento con `muted=True` nell'inbox. | Rispetto esatto della matrice dei controlli della Sezione 4. |
| **8. Webhook: Idempotenza e Fallimento Definitivo** | Integrazione con mock HTTP | Crash simulato durante l'invio (ripetizione con stesso `event_id`); fallimento 3/3 tentativi -> transizione a `delivery_failed` senza perdita dell'evento inbox. | Deduplicazione verificata sul receiver, outbox marcata fallita, evento leggibile in inbox. |
| **9. Inferenza reale Timestral** | Live model (Timestral locale pinned) | Esecuzione su fonte reale con pesi locali congelati. | Previsione reale completata con successo o errore/degradazione esplicito esposto all'utente (nessun fallback silenzioso). |
| **10. E2E Assistente Chiuso** | End-to-end multi-processo | Assistente chiuso -> append esterno -> daemon elabora, emette run provvisorio e notifica webhook -> assistente riaperto ritrova domanda e spiega l'aggiornamento. | Flusso completo senza sessione attiva, recupero perfetto alla riapertura. |
