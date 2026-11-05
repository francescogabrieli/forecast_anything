# Qualifica delle watch con backtest vincolato

## Intento

Un assistente deve poter collegare un backtest a una domanda sorvegliata e capire se la policy del core rende la watch operativa. Un backtest generico resta un report descrittivo: non può qualificare una watch solo perché usa la stessa fonte.

## Approcci considerati

1. **Promuovere un report generico per ID watch:** semplice, ma non prova che il grafo, il modello o la revisione della fonte coincidano; rende facile riutilizzare il holdout dopo aver visto i risultati.
2. **Copiare le metriche del backtest in `EvaluationRecord` discovery:** riusa la policy, ma falsifica la lineage e mescola due protocolli diversi.
3. **Eseguire il backtest con un ID watch esplicito, derivare la selezione dal candidato immutabile e valutare le sue finestre finali nel core — scelto:** conserva il report generico separato, lega le prove a candidato/watch/revisione e non accetta risultati selezionati a posteriori.

## Decisioni

- `submit_backtest` accetta `watch_id` facoltativo. Se omesso, comportamento e risultato restano generici e non qualificano watch.
- Se presente, il core carica candidato e watch. La selezione richiesta deve coincidere con il grafo congelato del candidato; la fonte e la revisione registrata devono coincidere con il profilo del candidato.
- Il percorso vincolato è limitato alle domande eseguibili `expected_deviation` e `forecast_change`, al criterio MAE e a `prespecified_holdout`. Richiede almeno 30 origini finali pianificate; se i dati non bastano, la decisione resta provvisoria.
- La policy usa soltanto esiti valutati della partizione finale, finestre non sovrapposte, almeno 30 origini e skill media positiva rispetto al riferimento. Fallimenti, esclusioni e prove incomplete non attivano la watch.
- Il piano di backtest salva `watch_id` e `candidate_id`; il core crea e registra la decisione e aggiorna la watch dopo il report. MCP non può inviare una decisione o una metrica.
- Prima di eseguire un backtest vincolato, il ledger rifiuta finestre finali sovrapposte con qualsiasi piano di backtest precedente della stessa fonte e revisione. Dopo la prenotazione, rifiuta anche nuovi backtest che riutilizzino quelle finestre. Il controllo avviene nello stesso lock SQLite della persistenza del piano.
- Il backtest generico continua a supportare confronti ripetuti. Se uno di questi ha già usato le finestre finali richieste, il candidato dovrà attendere nuove finestre non viste prima di poter essere qualificato.
- Le decisioni conservano `backtest_id` e gli ID delle valutazioni finali; gli eventi esistenti di revisione fonte invalidano tali valutazioni come ogni altra prova della watch.

## Fuori ambito

Qualifica per grafi multi-fonte, domande probabilistiche Brier/eventi, scelta automatica del provider, correzioni per ricerca multipla, confronto tra backtest non vincolati o attivazione da un report già esposto all'assistente.

## Criteri di accettazione

- Un backtest senza `watch_id` non modifica lo stato di alcuna watch.
- Un backtest con `watch_id` non parte con fonte, revisione, provider, opzioni, baseline o orizzonte diversi dal candidato; richiede almeno 30 origini per partizione.
- Il piano vincolato conserva lineage watch/candidato e il worker persiste report, decisione e transizione in modo ripetibile.
- Solo 30 o più finestre finali valutate e non sovrapposte con MAE medio inferiore alla baseline possono attivare una watch. Prove insufficienti restano `evaluating/provisional`; skill nulla o negativa non attiva.
- Le finestre finali non possono essere riutilizzate da un piano precedente o da un piano successivo, generico o vincolato.
- Un aggiornamento della fonte invalida la decisione e le relative evaluation IDs.
- La watch espone policy, ID report/evidence e codici motivazione; l'assistente non può impostare direttamente `activate`.
