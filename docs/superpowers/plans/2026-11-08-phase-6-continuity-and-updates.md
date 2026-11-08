# Phase 6: Continuità e Aggiornamenti Indipendenti dalla Chat

## Obiettivi di fase
- Consolidare il contratto di continuità e qualifica delle domande durature (Checkpoint 6A).
- Implementare aggiornamenti e rivalutazioni indipendenti dalla sessione della chat (Checkpoint 6B).
- Supportare controlli granulari (Pausa, Mute, Priorità) e separazione esplicita tra grant di sessione MCP e sottoscrizioni di background.
- Fornire un'Inbox durevole di eventi consultabile via MCP e viste web, con raggruppamento e deduplicazione.
- Implementare il primo canale esterno opt-in via webhook con outbox durevole e retry.
- Verificare il percorso completo end-to-end con assistente chiuso, elaborazione da daemon e recupero alla riapertura.

## Fasi di esecuzione
- [x] **6A: Contratto di continuità, qualifica e controlli** (`docs/research/phase-6a-continuity-contract.md`)
  - Analisi del codice attuale (`worker.py`, `watches.py`, `discovery/policy.py`, `question_storage.py`).
  - Matrice unificata di transizione (9 casi operativi).
  - Specifica della policy di continuità `continuity-v1`.
  - Definizione dei controlli e piano di collaudo.
- [ ] **6B: Implementazione aggiornamenti, controlli, inbox e webhook** (dopo approvazione del contratto 6A)
  - Modelli e migrazioni per Inbox, Outbox webhook e sottoscrizioni fonti.
  - Implementazione `continuity-v1` nel worker e collegamento automatico domande-successori.
  - Tool MCP e endpoint API per Inbox, controlli (Pausa, Mute, Priorità) e gestione webhook.
  - Suite di test completa (deterministica + Timestral reale + E2E ad assistente chiuso).
