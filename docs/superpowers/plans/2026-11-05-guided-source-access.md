# Guided Source Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendere esplicita la semantica temporale delle fonti e amministrabili i permessi MCP persistenti dal workspace locale.

**Architecture:** La console mantiene il mapping guidato esistente ma richiede scelte temporali senza precompilarle. Il CLI aggiorna in modo atomico la allowlist `source_ids` della config privata già consumata da `mcp --config`; il server continua a verificare i permessi prima delle operazioni di lettura.

**Tech Stack:** Python 3.11+, argparse, JSON e SQLite già presenti; React/TypeScript della console; documentazione Markdown.

**Spec:** [2026-11-05-guided-source-access-design.md](../specs/2026-11-05-guided-source-access-design.md)

## Global Constraints

- Grant e revoke sono decisioni dell'operatore locale, non strumenti MCP.
- La config resta privata (`0600`) e non espone token, percorsi fonte o segreti nell'output CLI.
- Un grant si applica solo dopo il riavvio del processo MCP.
- I timestamp senza fuso usano esclusivamente il fuso IANA scelto; frequenza e disponibilità non si inferiscono.
- Nessun commit o push.

## Review Focus

- Config mancante, malformata o non scrivibile: rifiutare senza perdere contenuto e senza stampare token.
- ID fonte non registrato o revoca ripetuta: rifiutare il grant e rendere la revoca ripetibile.
- Corsa tra processi o errore a metà scrittura: aggiornamento atomico nella stessa directory e permessi privati.
- Mapping temporale vuoto o con costante vuota: il profilo lo lascia da chiarire; nessun default silenzioso.
- Suggerimento di colonna: mostrarlo come proposta, senza cambiare il mapping inviato dall'utente.

---

### Task 1: Mappatura guidata con semantica temporale esplicita

**Files:**
- Modify: `apps/console/src/features/sources/ConnectSource.tsx`
- Modify: `apps/console/src/features/sources/SourceMappingForm.tsx`
- Modify: `src/forecast_anything/sources/profiling.py`
- Modify: `docs/quickstart.md`

- [x] Rimuovere i valori iniziali `UTC` e `1d`; lasciare fuso e frequenza vuoti con esempi nei placeholder.
- [x] Rifiutare costanti stringa vuote per ruoli non numerici che identificano tempo, disponibilità, revisione, serie o unità.
- [x] Mostrare eventuali colonne candidate nella lista chiarimenti con istruzione esplicita di selezione, senza applicarle automaticamente.
- [x] Spiegare nel form che il fuso interpreta date/timestamp senza offset e che la frequenza viene dichiarata dall'utente.
- [x] Aggiornare quickstart e criteri del gate fonti.

### Task 2: Amministrazione persistente dell'allowlist MCP

**Files:**
- Modify: `src/forecast_anything/workspace_config.py`
- Modify: `src/forecast_anything/cli.py`
- Modify: `docs/implementation/mcp.md`
- Modify: `docs/quickstart.md`

- [x] Aggiungere `permissions list|grant|revoke --config PATH`.
- [x] Verificare che il grant punti a una fonte già registrata nella stessa base dati del workspace.
- [x] Salvare la lista con sostituzione atomica della config e modalità `0600`; non modificare o stampare il token.
- [x] Rendere la revoca idempotente e informare che MCP va riavviato.
- [x] Documentare il confine di autorizzazione per CSV e HTTP e il possibile accesso di rete locale dopo il grant.

### Task 3: Allineamento della prima release

**Files:**
- Modify: `docs/first-release.md`
- Modify: `docs/capabilities.md` se la matrice dei permessi ne risulta influenzata.

- [x] Aggiornare l'evidenza del gate fonti senza dichiarare superata la prova in Codex Desktop.
- [x] Ricontrollare che nomi, esempi di comando e semantica del riavvio coincidano tra guide.
- [x] Eseguire controlli statici/build pertinenti e una prova manuale isolata del ciclo CLI di grant/revoke; lasciare le suite di test fuori da questo incremento.
