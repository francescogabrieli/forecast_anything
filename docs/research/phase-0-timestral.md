# Fase 0 — Baseline tecnica Timestral

## Branch, commit e proprietà delle modifiche

| Riferimento | Stato rilevato |
| --- | --- |
| Checkout principale | `codex/required-local-timestral` a `e6c67244a8fb0ef2df3cd568e78ffbe2ad73d235`, commit del piano prima dell'implementazione |
| Implementazione | `b19958d` più correzione `420eb74`, integrati tramite PR #16 in `11e574c` |
| Baseline candidata | `origin/main` locale a `72dcc1e`. Il worktree pulito `codex/public-release-readiness` a `59904d8` ha lo stesso albero Git `3d5a0eb70ce3a6a7fee51f0354e3b30f77980cec` |
| Altri worktree preesistenti | `codex/required-timestral-runtime` a `420eb74`, `codex/complete-console-e2e` a `df0fdaf`, snapshot detached a `a01388d` |
| Materiale locale preesistente | README, `docs/research/forecast-evidence.md`, `docs/roadmap.md`, sorgenti e materiali di design del sito. Il diff indica la provenienza dal checkout preesistente. Durante le verifiche è comparso anche un `AGENTS.md` non tracciato nel checkout originale, fuori dal diff della fase. Git non attribuisce l'autore delle modifiche non committate |
| Materiale della fase | Candidata in una copia isolata. L'overlay conserva sito, asset, piano/spec e modifiche alla ricerca e alla roadmap. Il README è stato riconciliato sul testo integrato, mantenendo i riferimenti al sito e la distinzione tra backtest generico e qualifica della watch. Il diff originale del README è disponibile nel pacchetto di revisione |

## Artifact e configurazione verificati

Il LaunchAgent attivo e la voce MCP configurata in Codex usano lo stesso eseguibile versionato `83919401ed0e`, installato come pacchetto non editable `forecast-anything==0.1.0`, su macOS arm64 con Python 3.14. L'agent è stato osservato in esecuzione. API/worker e MCP puntano alla stessa configurazione privata, con permessi `0600`. La configurazione dell'agent imposta l'accesso offline al modello. Il plist precedente presente nel workspace puntava al worktree `420eb74` e costituisce una configurazione storica.

Tra `83919401ed0ef62f7818608224f2eb165505abdb` e `72dcc1e` non ci sono differenze in codice core, schemi impacchettati, esempio minimo o dipendenze. Confronto diretto dei 66 file del package nella wheel ricostruita, nel runtime installato e, per i sorgenti, nel checkout integrato: tutti identici. La directory di versione identifica il deploy, mentre questo confronto verifica il suo contenuto. L'hash dell'intera wheel include anche metadati di build e documentazione.

- Wheel base `forecast_anything-0.1.0-py3-none-any.whl`, SHA-256 `418017661eca3ef5eccbcc531113d01ea4707cc0830f0efa3ff4575885227794`.
- Sdist base `forecast_anything-0.1.0.tar.gz`, SHA-256 `101d7c3f75fe3ad406c2a9c48d41eecd420f82c06fc50b741bfa1be1f2194682`.
- Timestral-28M CPU fp32, codice `a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff`, pesi `49b26409ac87b5935539a5d8ffe7f397b720db47`. Il client MCP connesso ha restituito `required_provider=timestral` e `status=cached`. La prova di inferenza è separata dal controllo della cache.

## Comportamento prima e dopo, file e compatibilità

Il checkout principale esponeva ancora il percorso precedente. Il codice già integrato usa Timestral per le nuove previsioni CLI, i job API/MCP, i candidati discovery e i backtest. Il worker applica la stessa policy quando esegue lavoro persistito. La baseline resta il comparatore stagionale. Gli errori di installazione, cache o caricamento sono espliciti. L'accettazione legacy resta consultabile. I job baseline-primary incompatibili terminano con `required_provider_migration` e le watch incompatibili vengono sospese con un motivo visibile.

La fase aggiorna README, quickstart, matrice, guida MCP, roadmap e comandi del sito. L'accettazione in `scripts/check_timestral_mcp.py` aggiunge replay del forecast in un nuovo processo MCP, uguaglianza dell'intero run e un confronto storico reale sfavorevole al modello. La fase usa l'implementazione e gli schemi già integrati e non richiede ulteriori migrazioni o modifiche ai contratti.

## Verifiche

| Prova | Esito |
| --- | --- |
| Policy, CLI, setup, discovery, migrazione e MCP | 118 test mirati superati. Il primo tentativo in sandbox ha fallito due test per il divieto di bind. I 118 passano con loopback autorizzato |
| Suite Python con modello abilitato | 904 superati, 66,72 s. Il primo run offline ha superato 903 test e fallito la parità perché il test consulta i metadati pubblici del checkpoint. La parità è poi passata da sola e nella suite completa |
| Lint, format e contratti | Ruff, formattazione, export core/console e check nativo del contratto agent superati. Agent: typecheck e 29 test superati |
| Console | Tipi generati, typecheck, 84 test e build superati. Playwright: 3 superati, di cui uno con Timestral reale (run `e288a50ea7937367200454d0535187ddaa0ecbd20580568d57254b4de0b2bdc3`, screenshot nel pacchetto di revisione). Il primo tentativo Playwright aveva due test riusciti e un errore di setup per la `.venv` mancante nella copia isolata |
| Artifact base | Wheel e sdist costruite offline. La suite ha installato una wheel nuova fuori dal checkout e ha completato preparazione e inferenza del modello. Lo stesso smoke reale è riuscito per la wheel della candidata, installata fuori dal checkout. I 66 file del package coincidono con quelli della wheel base e del runtime installato |
| CLI reale installata | Esempio minimo, richiesta ripetuta e `show` hanno restituito lo stesso record `e86d055eeb3024a0d1d30ad1e5dfa0fd1e95cd035681597957184e64293c1994` |
| Pesi e dipendenze | Il subprocess CLI con cache vuota verifica `model_not_prepared` senza forecast. I test di diagnostica esercitano dipendenza assente, revisione errata ed errore di caricamento con fixture |
| MCP connesso, sola lettura | Due letture identiche del run `7a78c0f340a53d3152fd1a0ecbb52fa2436be8dee6c58b05437d9b55d431cd81`. Letto anche il backtest storico baseline `8a2f888fe105f38a43c5e80389ba262bfa697d47df13f4c62da4b3d0becdd6c1` con MAE finale 0 contro 1. Quattro watch legacy lette a una per pagina risultano `paused/stale`, non operative, con `required_provider_migration`. Una pagina più ampia ha restituito `result_too_large` |

I comandi di setup del sito coincidono con quelli della guida MCP, salvo l'extra di sviluppo, e i link locali dei documenti modificati sono risolti. La build di revisione usa una copia pulita dei soli file versionati. Una build intermedia dalla copia con dipendenze frontend includeva `node_modules` e risultati Playwright nello sdist. La build pulita ne verifica l'assenza e include il sito. Wheel e sdist hanno hash separati nel pacchetto di revisione. Il diff della fase passa `git diff --check`; nel diff integrato Git segnala il file di licenza OFL preesistente, conservato byte per byte con i suoi terminatori CRLF.

## Prova reale e identificativi

La prova SDK avvia processi CLI, API e worker dal pacchetto installato già usato dal servizio connesso. Usa clock reale, cache locale e un workspace temporaneo indipendente. Le due serie CSV sono sintetiche. Il primo tentativo del riproduttore usava un'unica fonte e le stesse finestre finali per confronto generico e qualifica. La prova finale usa due serie indipendenti e mantiene la policy sulle finestre finali.

| Evidenza | Esito |
| --- | --- |
| Forecast configurato | `ab4daf33900055b81e3d6cee8face630db6b2acaef897b3b24e8b9f1c2d50430`, valore 1,0119681358337402, output primario `model`, provenienza fissata e comparatore `seasonal_naive` separato |
| Replay dopo riconnessione | Stesso job `6c1d73f67ee17ff542f3a717b7257b4635c5960f86075d79475b0f9df632a2fc`, stesso run e uguaglianza strutturale del record completo |
| Confronto sfavorevole a Timestral | `c8e043a6e98f96f1c0e87cfe5a12a983905de138dff6e1beb5075af4c1454bac`, 2 origini finali, MAE Timestral 0,01735818386077881 contro 0 della baseline a periodo 2. MAE relativo assente con motivo `zero_baseline_mae`. Report identico dopo riconnessione |
| Confronto vincolato alla watch | `0343b5e4bd42eb55aa7390f746deef032c76901dc112d216e319319b8ea26eed`, 30 origini finali, MAE Timestral 0,01022263765335083 contro 2. Il core ha qualificato la watch. Dopo la modifica controllata della fonte il worker ha invalidato la qualifica e creato il successore provvisorio `b1e88acbd8cb4eccdfcb7b90d16c40d643c99383f6cf0169ec62bce7b8e53296`. Il report storico è rimasto identico |
| Benchmark storico reale | Retail: MAE relativo 1,043 su 37 origini finali, favorevole alla baseline. Conservato il [report originale](timestral-benchmark/report.json) |

## Procedura riproducibile

Usare la candidata di revisione e un workspace privato. Il controllo attende la scadenza reale della watch dopo il completamento del backtest, circa quattro minuti nel complesso. Preparare una volta i pesi secondo la [guida](../implementation/timestral.md).

```sh
uv sync --locked --extra dev --extra mcp
uv run --locked --extra mcp forecast-anything model status
uv run --locked --extra mcp forecast-anything model prepare
trial_dir="$(mktemp -d)"
HF_HUB_OFFLINE=1 uv run --locked --extra mcp python scripts/check_timestral_mcp.py \
  --workspace "$trial_dir/workspace" --report "$trial_dir/report.json"
```

Per ripetere l'esecuzione dal pacchetto installato, usare il Python del suo ambiente, l'entrypoint MCP installato nello stesso ambiente e il percorso assoluto dello script da fuori del checkout. Per verificare una wheel nuova con un'installazione indipendente:

```sh
uv build
uv run --locked --extra dev --extra mcp python scripts/check_release.py --dist dist
```

## Revisione tecnica

La revisione indipendente ha rilevato che 35 secondi prima della scadenza non coprivano il tempo massimo del backtest. Il riproduttore ora riserva il budget del job più 30 secondi, controlla la scadenza prima della sostituzione atomica del CSV e verifica che lo stato operativo corrisponda alla decisione del core. Il riproduttore così aggiornato ha completato una seconda prova con modello reale e ha registrato gli esiti di qualifica prodotti dalla policy. La guida distingue anche i permessi via config da quelli via ambiente.

## Limiti e materiale per la revisione

La prova completa Timestral usa il client SDK stdio. Le letture effettuate nella chat Codex e il flusso Desktop storico sono evidenze distinte. I test con doppie implementazioni e i dataset sintetici servono a verificare orchestrazione e calcolo. La build dell’agent Eve opzionale si è fermata al recupero dei metadati del modello dall’AI Gateway. Il percorso locale obbligatorio non usa Eve. L'accuratezza su nuovi domini, l'installazione guidata, il riavvio dopo logout/reboot e le UI incorporate richiedono verifiche dedicate nelle fasi successive.

Il pacchetto di revisione contiene piano, overlay del materiale preesistente, diff della fase, diff integrato, JSON di accettazione e screenshot del test reale della console. La review dell'utente in questa chat è il checkpoint prima della fase 1.
