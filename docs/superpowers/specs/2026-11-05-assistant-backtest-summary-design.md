# Riepiloghi dei backtest nell'assistente

## Intento

Quando un assistente legge un backtest, deve poter spiegare in modo consistente il risultato, il confronto con la baseline, le finestre valutate e i limiti dei dati. Il riepilogo deve puntare al report e alle valutazioni immutabili già registrate; non deve avviare calcoli né leggere nuovamente la fonte.

## Approcci considerati

1. **Lasciare solo `get_backtest` e chiedere all'assistente di interpretarlo:** nessuna modifica, ma conteggi, metriche e limiti possono essere presentati in modo discontinuo.
2. **Aggiungere un nuovo endpoint nel core:** crea una seconda rappresentazione API per dati che il core già espone e amplia inutilmente il contratto HTTP.
3. **Aggiungere una proiezione MCP read-only dei record esistenti — scelto:** un solo strumento combina report, esiti delle origini e stato watch facoltativo; l'API e il registro restano la fonte autorevole.

## Decisioni

- Aggiungere `summarize_backtest(backtest_id, watch_id?)` come strumento MCP di sola lettura.
- Il riepilogo usa `GET /backtests/{id}` e tutte le pagine persistite di `GET /backtests/{id}/origins`; non rilegge la fonte e non invoca provider.
- Esporre i tre riepiloghi di partizione già registrati, l'interpretazione esplicita di MAE e i punti finali pronti per un grafico (data, stato, MAE del modello e della baseline, ID valutazione o motivo di esclusione/fallimento).
- Il rapporto `relative_mae` è il rapporto MAE modello/baseline: sotto 1 indica MAE inferiore nel campione confrontato; un valore mancante conserva il motivo registrato. La spiegazione non dichiara significatività né accuratezza futura.
- Se viene fornito `watch_id`, includere il suo stato attuale e indicare se la decisione di qualifica è collegata proprio al `backtest_id` richiesto. Non presentare una decisione precedente come risultato di questo report.
- I valori previsionali puntuali restano disponibili con `get_run`; le valutazioni restano leggibili tramite gli strumenti esistenti. La console continua a fornire i grafici del forecast.
- Nessun endpoint API nuovo, nessuna mutazione di ledger, nessuna nuova dipendenza.

## Obiettivi

- Consentire all'assistente di riferire risultato, baseline, denominatore, assunzioni e motivi di incompletezza senza dover sintetizzare campi ambigui.
- Fornire una serie compatta e verificabile per visualizzare l'errore MAE per origine finale.
- Rendere esplicito se una watch è stata aggiornata da quel backtest e perché.

## Fuori ambito

- Nuovi forecast, scoring o inferenza; metriche non presenti nei record; causalità o garanzie di accuratezza.
- Modifiche al frontend, grafici generati dal core, lettura di archivi privati o dati grezzi della fonte.
- Riepiloghi di run non valutati: `get_run` continua a esporre le previsioni registrate e `list_run_evaluations` le valutazioni persistite.

## Vincoli e limiti

- Gli strumenti MCP restituiscono al massimo 64 KiB inclusa la duplicazione testo/struttura.
- I backtest pianificano al massimo 50 origini per partizione; il riepilogo include soltanto le origini finali nel grafico.
- `get_backtest` resta immutabile e può restituire `not_found` finché il worker non pubblica il report.
- I report generici restano descrittivi; la vista watch non modifica né qualifica una watch.
