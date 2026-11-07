# Prima release pubblicabile

Direzione confermata dal proprietario il 30 ottobre 2026: prodotto open source installabile e utilizzabile dal proprio assistente; sito pubblico curato per scoperta e primo utilizzo; console locale opzionale. Il lancio richiede un percorso centrale completo e verificato. Nuovi connettori, modelli e maggiore autonomia potranno ampliarlo successivamente.

Questo documento definisce i criteri di rilascio, non dichiara che siano già superati. Nessuna data di lancio è fissata. Il proprietario ha autorizzato commit, push e PR per questo incremento; la pubblicazione del prodotto resta fuori scope.


## Required Timestral — current product gate

Owner decision on 5 November: local Timestral is mandatory for primary product forecasts; the seasonal baseline is only a reference. Earlier baseline-only acceptance below is historical and does not establish this gate. The implementation now has genuine pinned-model CLI/API/worker/MCP, backtest/refresh/change-summary and browser evidence, plus real parity and installed-wheel checks. [Current evidence](research/required-timestral-acceptance.md).

Prepared weights are required; there is no Mistral API key or silent fallback. Missing model setup is distinct from process liveness. Legacy watches pause for migration and new candidates/epochs require fresh evidence. Remaining public release work (destinations/site, declared platforms, login/reboot startup) is unchanged.

## Percorso da dimostrare

**Installa → collega → prevedi → verifica → segui una domanda → comprendi cosa è cambiato.**

Il registro appartiene a Forecast Anything. La chat può chiudersi senza perdere domande, risultati e lavori accettati; l’elaborazione prosegue soltanto mentre il servizio e la macchina sono attivi. MCP è l’accesso agli strumenti, non lo scheduler né il modello numerico.

## Gate della prima release

| Gate | Evidenza disponibile | Da completare prima del lancio |
| --- | --- | --- |
| Installazione e operatività semplici | Wheel installata fuori dal checkout; la prova MCP esegue baseline, backtest e liveness; dopo un crash simulato lo stato passa a `stale` e torna `running` al riavvio. Il test di processo verifica che SIGTERM rimuova subito l'heartbeat e che un job persistito venga completato. Il 5 novembre il CLI installato è stato verificato su workspace pulito: `status` ha distinto `not_running`, `running`, `stale` e recupero a `running`; `up` è ripartito correttamente dopo uno stop | Ripetere la gestione su tutte le piattaforme di installazione dichiarate; lo stato del worker indica liveness e non successo dei job |
| Un assistente realmente utilizzabile | SDK ufficiale, CLI e percorso live MCP esposto alla chat Desktop; il proprietario ha confermato rilettura immutabile dopo uscita completa/riapertura. Runtime supervisionato da launchd nella sessione macOS corrente | Accettato nel perimetro locale supportato. Setup grafico e altre piattaforme restano fuori dalle prove osservate |
| Fonti accessibili | Fonte CSV sintetica nuova registrata tramite MCP, timezone mancante rilevato e corretto; grant/revoke persistenti verificati su nuove connessioni SDK; mapping esplicito verificato anche nel browser | Accettato per CSV locale. HTTP JSON e connettori generici mantengono i limiti dichiarati |
| Previsioni configurabili e verificabili | Timestral locale obbligatorio e 26 strumenti MCP; forecast, backtest vincolato e riepiloghi confrontati con evidenze salvate. Percorsi con wheel, recovery, review indipendente e letture Desktop | Accettato per Timestral locale nel percorso reale documentato e sorgenti supportate; nessuna affermazione di accuratezza generale |
| Domande ricorrenti e continuità | Watch creata e qualificata tramite 30 origini finali; refresh alla scadenza reale, invalidazione dell’evidenza e successore provvisorio osservati dalla chat MCP. Cronologia e confronto non nullo tra run salvati verificati | Accettato mentre runtime e macchina sono attivi. Finestre finali di qualifica non riutilizzabili; avvio dopo logout/riavvio resta distinto |
| Vista comprensibile | Trascrizione Desktop con riepilogo, confronto report/origini e grafico testuale; percorso live mostra delta +8 tra valori persistiti e ragioni della watch senza confondere decisione storica con stato attuale | Accettato per report e grafici testuali. Nessun rendering grafico nativo dell’host promesso o dichiarato verificato |
| Sito pubblico e onboarding | Sorgente statica locale in `site/`, revisionata su desktop/tablet/mobile; selettore basato sugli output sintetici emessi dal runtime, con setup, MCP, limiti e link a documenti/contributi | Pubblicare il sito curato e fissare destinazione/nome. L'esempio resta sintetico e non fa affermazioni di accuratezza; nessun backend pubblico di forecasting è necessario |
| Distribuzione verificata | Licenze e packaging presenti; wheel e sdist ricostruiti dal checkout aggiornato, con import del modulo MCP nuovo dalla wheel installata in un target isolato | Eseguire tutto il percorso da artefatti installati sulle piattaforme dichiarate, definire nome/destinazioni, verificare documenti e manutenzione/contributi prima di pubblicare |

## Ordine di sviluppo corrente

1. [Previsioni configurabili e backtesting](superpowers/specs/2026-10-30-forecast-evidence-design.md): incremento implementato, verificato e revisionato, con [piano esecutivo](superpowers/plans/2026-10-30-forecast-evidence.md) approvato dal proprietario il 30 ottobre 2026.
2. Setup e gestione dei servizi installati; verifica con un assistente reale.
3. Domande ricorrenti e riepiloghi/report attraverso gli stessi strumenti e lo stesso registro.
4. Sito, esempio pubblico e prova completa degli artefatti di release.

I confini possono restare circoscritti a fonti e calendari supportati; il percorso promesso deve essere completo per quei confini. La mancata disponibilità di nuove funzionalità non va mascherata con esempi simulati o controlli decorativi.

## Qualità e stato delle evidenze

La baseline MCP precedente ha prodotto 665 test Python passati e un test del provider reale saltato. L’incremento precedente conclude con 819 test passati e 1 saltato, dopo fix e review indipendente: [report e limiti della verifica](research/forecast-evidence.md). Il ciclo watch è raggiungibile via MCP; la qualifica ora richiede un backtest associato al candidato e finestre finali non riutilizzate, mentre i report generici non promuovono watch. Queste modifiche richiedono ancora una prova end-to-end nell'host desktop. Le evidenze esistenti non chiudono i gate di installazione gestita, interfaccia desktop, accettazione dei report nell'assistente, sito e destinazioni di release.

Il test mirato del servizio locale ha riprodotto e poi escluso un deadlock del worker; i quattro test di `tests/integration/test_local_services_process.py` passano, incluso lo stop SIGTERM e la rimozione immediata dell'heartbeat. Il 5 novembre 2026 la wheel costruita dal checkout è stata installata in un virtualenv isolato fuori dal repository e verificata con `init`, `serve`, `worker` e `status`: gli stati osservati sono `not_running`, `running`, `stale`, recupero a `running` e `unreachable/unknown` quando l'API è spenta. Un workspace separato ha inoltre completato `up`, `status` con API e worker disponibili, stop e riavvio. Il server `forecast-anything` è stato aggiunto alla configurazione globale Codex con il comando supportato e compare attivo in `codex mcp list`. Lo smoke MCP via Codex CLI già presente ha completato una previsione configurata, letto il run e percorso le operazioni watch. La prova diretta nell'interfaccia Codex Desktop non è stata eseguibile: il controllo computer-use ha negato l'accesso all'app; serve ancora la verifica interattiva. Queste prove non dimostrano accuratezza predittiva generale, usabilità esterna o prontezza dell'intera release. La prova osservata con cinque persone resta sospesa per decisione del proprietario; non viene riportata come superata. Timestral e i relativi pesi mantengono condizioni e abilitazione separate; i controlli ordinari non effettuano inferenze a pagamento o download di pesi.

Il 4 novembre 2026 la sorgente del sito statico è stata aggiunta in `site/` e verificata localmente sui layout desktop, tablet e mobile, con un selettore per tre risultati sintetici emessi dal runtime. Il sito resta non pubblicato: dominio, destinazione e owner pubblico non sono stati scelti. Le immagini sono frammenti autentici dell'interfaccia e del grafico; non si usano fotografie di clienti né un video dimostrativo non disponibile.

## Accettazione Desktop e report — aggiornamento del 5 novembre

La trascrizione fornita dal proprietario conferma lettura MCP di fonti/watch, riepilogo confrontato con report/origini, grafico testuale MAE e rilettura del risultato immutabile nell'interfaccia Desktop. Due nuove prove con SDK ufficiale e processi reali verificano inoltre correzione temporale della fonte, grant/revoke persistenti, qualifica vincolata con 30 origini finali, replay, riconnessione, riavvio API/worker e aggiornamento automatico con invalidazione delle vecchie evidenze. [Dettaglio e limiti](research/desktop-assistant-acceptance.md).

Resta attesa la conferma del proprietario dopo uscita completa e riapertura di Codex; la lettura ripetuta precedente non dimostra il riavvio del collegamento. Il percorso testuale dei report è osservato; il rendering grafico nativo e l'interazione con le schermate di configurazione non sono stati osservati. I gate sopra vanno letti insieme a questo aggiornamento, senza dichiarare concluse le prove UI mancanti.

La prova del proprietario dopo riapertura alle 17:06 ha restituito `network_error`: API e worker avviati dalla sessione Codex risultavano spenti. Il runtime è stato quindi avviato sotto launchd utente, indipendente dall'app, e il report originale è tornato leggibile via MCP. La nuova configurazione va ancora confermata dopo chiusura/riapertura Desktop. L'avvio automatico dopo logout o riavvio del Mac non è installato da questo intervento.

Alle 17:09 il proprietario ha confermato la nuova lettura MCP dopo chiusura completa e riapertura di Codex: `ok: true`, `completed`, metriche invariate. È quindi superata la verifica di riconnessione Desktop nella configurazione launchd della sessione macOS corrente. Sono accettati accesso/rilettura MCP e presentazione testuale dei report nell'assistente, insieme alle prove tecniche real-process descritte nel report. Le precedenti indicazioni di attesa della conferma sono superate da questo esito. Restano distinti il rendering grafico nativo, le schermate di setup non osservate e l'avvio dopo logout/riavvio del Mac: non sono dichiarati verificati da questa prova.

## Chiusura del percorso assistente e report

Il percorso locale supportato CSV → correzione UTC → forecast → backtest vincolato → watch qualificata → refresh automatico → spiegazione del cambiamento è stato eseguito tramite MCP esposto a questa chat Desktop. La prova usa una fonte sintetica distinta e registra confronto prima/dopo, motivi della policy e invalidazione della vecchia evidenza. Grant e revoca sono stati verificati su nuove connessioni MCP. Insieme alla riapertura confermata dal proprietario, questo conclude i due punti di accettazione assistente/report nel perimetro locale supportato. [Evidenze complete](research/desktop-assistant-acceptance.md).

La presentazione accettata comprende report e grafici testuali; non promette grafici nativi dell'host. La pubblicazione del sito, le piattaforme aggiuntive e l'avvio dopo logout/riavvio del Mac restano attività separate.
