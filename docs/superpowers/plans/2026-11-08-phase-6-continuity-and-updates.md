# Phase 6: Continuità e Aggiornamenti Indipendenti dalla Chat (Revisione 3)

## Obiettivi di fase
- Consolidare il contratto di continuità, qualifica e controlli (Checkpoint 6A - Revisione 3).
- Mantenere la qualifica vincolata al candidato nel primo rilascio di 6B, esponendo lo stato provvisorio finché la riqualifica automatica entro budget (target 30 origini, tetto BacktestSettings di 50, scadenza `requalification_due_at` separata da `next_due_at`) non viene completata.
- Separare rigidamente prossimo polling della fonte, freschezza dell'orizzonte di previsione ed applicabilità delle evidenze storiche, con gestione dell'orizzonte trascorso a dati invariati e verifica dell'invarianza di `available_at` storico.
- Implementare controlli completi (Pausa, Mute, Priorità) distinguendo lavoro in coda, in esecuzione e chained, con gestione deterministica di fonti condivise e soppressione di webhook già in coda.
- Fornire un'Inbox durevole nel ledger con `event_id` deterministico contenente `event_kind` e `transition_id`, e un canale esterno opt-in via webhook con outbox durevole, deduplicazione con `X-Forecast-Event-Id`, politica a 3 tentativi totali con 2 attese di retry e arresto al terzo fallimento su `delivery_failed`.
- Verificare il percorso completo end-to-end con assistente chiuso, elaborazione dal daemon di background e recupero della stessa domanda alla riapertura.

## Fasi di esecuzione
- [x] **6A: Contratto di continuità, qualifica e controlli (Rev 3)** (`docs/research/phase-6a-continuity-contract.md`)
  - Analisi del codice (`worker.py`, `watches.py`, `discovery/policy.py`, `question_storage.py`).
  - Separazione tripartita: Polling, Freschezza orizzonte, Applicabilità evidenze.
  - Criteri completi per append (valori, event_time, available_at storico immutato, revisioni, mapping).
  - Qualifica vincolata al candidato e stato provvisorio esplicito post-append; target riqualifica a 30 origini e scadenza separata `requalification_due_at`.
  - Spostamento di `continuity-v1` a proposta futura.
  - Matrice controlli (in coda, in esecuzione, chained) e semantica fonti condivise.
  - Limiti e regole del budget di riqualifica (< 30 origini, budget esaurito) e gestione webhook (crash, deduplicazione, 3 tentativi con 2 attese).
- [x] **6B: Implementazione aggiornamenti, controlli, inbox e webhook** (implementazione e acceptance consegnate per revisione; nessun push)
  - Modelli ledger e migrazioni per Inbox, Outbox webhook, campo `requalification_due_at` e sottoscrizioni fonti.
  - Implementazione aggiornamenti post-append con stato provvisorio e scheduling riqualifica.
  - Endpoint e tool MCP per gestione controlli (Pausa, Mute, Priorità), consultazione Inbox e configurazione Webhook.
  - Verificati scenari deterministici, retry/crash webhook, Timestral reale e journey end-to-end con assistente chiuso, receiver locale e recupero della stessa domanda.
  - Limite da sottoporre alla revisione: il budget di 300 secondi è cooperativo tra origini e non interrompe un'inferenza provider già in esecuzione; il contratto 6A lo definisce invece timeout rigido. Osservazione Codex Desktop non disponibile tramite il tool UI.
