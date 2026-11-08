# Phase 6: Continuità e Aggiornamenti Indipendenti dalla Chat (Revisione 2)

## Obiettivi di fase
- Consolidare il contratto di continuità, qualifica e controlli (Checkpoint 6A - Revisione 2).
- Mantenere la qualifica vincolata al candidato nel primo rilascio di 6B, esponendo lo stato provvisorio finché la riqualifica automatica entro budget non viene completata.
- Separare rigidamente prossimo polling della fonte, freschezza dell'orizzonte di previsione ed applicabilità delle evidenze storiche.
- Implementare controlli completi (Pausa, Mute, Priorità) distinguendo lavoro in coda, in esecuzione e chained, con gestione deterministica di fonti condivise e soppressione di webhook già in coda.
- Fornire un'Inbox durevole nel ledger e un canale esterno opt-in via webhook con outbox durevole, deduplicazione con `X-Forecast-Event-Id`, gestione retry con backoff e arresto al terzo fallimento.
- Verificare il percorso completo end-to-end con assistente chiuso, elaborazione dal daemon di background e recupero della stessa domanda alla riapertura.

## Fasi di esecuzione
- [x] **6A: Contratto di continuità, qualifica e controlli (Rev 2)** (`docs/research/phase-6a-continuity-contract.md`)
  - Analisi del codice (`worker.py`, `watches.py`, `discovery/policy.py`, `question_storage.py`).
  - Separazione tripartita: Polling, Freschezza orizzonte, Applicabilità evidenze.
  - Criteri completi per append (valori, event_time, available_at, revisioni, mapping).
  - Qualifica vincolata al candidato e stato provvisorio esplicito post-append; spostamento di `continuity-v1` a proposta futura.
  - Matrice controlli (in coda, in esecuzione, chained) e semantica fonti condivise.
  - Limiti e regole del budget di riqualifica (< 30 origini, budget esaurito) e gestione webhook (crash, deduplicazione, fallimento).
- [ ] **6B: Implementazione aggiornamenti, controlli, inbox e webhook** (in attesa di revisione e approvazione finale del contratto 6A)
  - Modelli ledger e migrazioni per Inbox, Outbox webhook e sottoscrizioni fonti.
  - Implementazione aggiornamenti post-append con stato provvisorio e scheduling riqualifica.
  - Endpoint e tool MCP per gestione controlli (Pausa, Mute, Priorità), consultazione Inbox e configurazione Webhook.
  - Esecuzione suite di test (deterministica, Timestral reale, crash webhook, E2E assistente chiuso).
