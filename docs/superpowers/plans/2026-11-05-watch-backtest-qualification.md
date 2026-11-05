# Watch Backtest Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualificare una watch solo con un backtest eseguito sul suo candidato immutabile e su finestre finali mai riutilizzate.

**Architecture:** `submit_backtest` rimane generico per default; l'opzione `watch_id` blocca selezione e lineage sul candidato memorizzato. Il piano immutabile riserva le finestre finali sotto il lock del ledger, il worker ricalcola la policy sul report completato e registra decisione/transizione. I report generici non possono qualificare watch.

**Tech Stack:** Python/Pydantic, FastAPI `/v1/jobs`, SQLite ledger, MCP SDK, Markdown.

**Spec:** [2026-11-05-watch-backtest-qualification-design.md](../specs/2026-11-05-watch-backtest-qualification-design.md)

## Global Constraints

- Nessuna decisione o metrica di qualifica è accettata da MCP come input.
- Una selezione vincolata deve coincidere col grafo e con la revisione fonte congelati.
- `max_origins_per_partition >= 30`; soltanto origini finali indipendenti contribuiscono.
- Finestre finali già usate o prenotate non vengono riutilizzate.
- Idempotenza del job e transizioni durevoli restano sotto il worker/ledger.
- Nessun commit o push.

## Review Focus

- Replay di job preesistenti: i nuovi campi opzionali non alterano le chiavi o le identità dei backtest generici.
- Mismatch di fonte, revisione o selezione: rifiuto prima di leggere CSV o calcolare previsioni.
- Due writer concorrenti: una sola inserzione del piano può prenotare finestre finali sovrapposte.
- Dati insufficienti, finestre sovrapposte, valutazioni fallite e skill nulla/negativa: watch mai operativa.
- Crash dopo report ma prima della transizione: replay completa la stessa decisione senza duplicarla.

---

### Task 1: Policy e lineage vincolata

**Files:**
- Modify: `src/forecast_anything/contracts.py`
- Modify: `src/forecast_anything/backtesting/contracts.py`
- Modify: `src/forecast_anything/discovery/policy.py`

- [x] Aggiungere `BacktestJobRequest.watch_id` e i riferimenti opzionali watch/candidato a `BacktestPlan`, omettendoli dalla serializzazione quando `None` per preservare le identità generiche.
- [x] Aggiungere `EligibilityDecision.backtest_id` opzionale.
- [x] Derivare `ForecastSelection` dal grafo candidato e rifiutare template, criterio o selezione non supportati.
- [x] Implementare la valutazione dei soli esiti finali, con 30 origini, finestre disgiunte, MAE positivo rispetto al riferimento e reason codes fail-closed.

### Task 2: Prenotazione, worker e watch state

**Files:**
- Modify: `src/forecast_anything/backtesting/service.py`
- Modify: `src/forecast_anything/backtesting/store.py`
- Modify: `src/forecast_anything/backtesting/planning.py`
- Modify: `src/forecast_anything/store.py`
- Modify: `src/forecast_anything/watches.py`

- [x] Validare watch/candidato/revisione/selezione al submit e salvare i riferimenti sul piano vincolato.
- [x] In `BacktestStore.put_plan`, serializzare i writer SQLite e rifiutare sovrapposizioni finali con piani precedenti; bloccare i futuri piani generici sulle finestre qualificate.
- [x] Far ricalcolare al ledger la decisione dal report e dalle origini validate prima di inserirla.
- [x] Dopo il report, il worker registra decisione e transizione con evento deterministico; la replay riprende dopo un crash.
- [x] Riutilizzare l'invalidazione per source revision e assicurare che l'attivazione richieda valutazioni del report registrato.

### Task 3: Percorso MCP e documentazione

**Files:**
- Modify: `src/forecast_anything/mcp_adapter/arguments.py`
- Modify: `src/forecast_anything/mcp_adapter/server.py`
- Modify: `docs/implementation/mcp.md`
- Modify: `docs/first-release.md`
- Regenerate: `contracts/v1/schemas.json`, `contracts/v1/openapi.json`, console API contract snapshots if required

- [x] Esporre `watch_id` opzionale in `submit_backtest`; il tool dichiara che il backtest vincolato aggiorna policy/watch dal lato core.
- [x] Aggiornare gli schemi generati mantenendo compatibilità dei client esistenti.
- [x] Documentare: backtest generico non qualifica; il candidato vincolato richiede selezione esatta e almeno 30 origini; il holdout è monouso.
- [x] Aggiornare la prima release senza dichiarare concluso il gate Codex Desktop.

### Task 4: Controlli

- [x] Verificare staticamente Python e TypeScript, diff e contratti generati.
- [x] Eseguire una prova manuale isolata: generico non cambia la watch; watch backtest con lineage corretta qualifica; mismatch, riuso e insufficienza restano non operative; replay produce un solo evento.

La prova manuale del 5 novembre 2026 ha usato un ledger e CSV temporanei: selezione discordante rifiutata; backtest generico senza transizione; 30 valutazioni finali vincolate hanno attivato la watch; replay ha mantenuto un solo evento; riuso ha restituito `holdout_reuse`; dati insufficienti hanno lasciato la watch `evaluating/provisional`. Typecheck, controlli statici e contratti generati erano già stati verificati prima dello smoke. Nessuna suite automatizzata è stata eseguita in questo incremento.
