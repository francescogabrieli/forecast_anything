# Prima release pubblicabile

Direzione confermata dal proprietario il 30 ottobre 2026: prodotto open source installabile e utilizzabile dal proprio assistente; sito pubblico curato per scoperta e primo utilizzo; console locale opzionale. Il lancio richiede un percorso centrale completo e verificato. Nuovi connettori, modelli e maggiore autonomia potranno ampliarlo successivamente.

Questo documento definisce i criteri di rilascio, non dichiara che siano già superati. Nessuna data di lancio è fissata. Il proprietario ha autorizzato commit e push del cambiamento verificato; la pubblicazione del prodotto resta fuori scope.

## Percorso da dimostrare

**Installa → collega → prevedi → verifica → segui una domanda → comprendi cosa è cambiato.**

Il registro appartiene a Forecast Anything. La chat può chiudersi senza perdere domande, risultati e lavori accettati; l’elaborazione prosegue soltanto mentre il servizio e la macchina sono attivi. MCP è l’accesso agli strumenti, non lo scheduler né il modello numerico.

## Gate della prima release

| Gate | Evidenza disponibile | Da completare prima del lancio |
| --- | --- | --- |
| Installazione e operatività semplici | Wheel installata fuori dal checkout e baseline eseguita; API e worker persistenti separati | Percorso installato di configurazione, avvio, stato e arresto senza tre terminali o dashboard obbligatoria; errori e recupero leggibili |
| Un assistente realmente utilizzabile | Client SDK ufficiale MCP verificato su stdio reale | Almeno un host assistente desktop scelto e provato: configurazione, collegamento, fonte, disconnessione e ritorno |
| Fonti accessibili | CSV mappato via MCP, policy per cartelle e ID fonte; core con HTTP JSON limitato | Percorso guidato sulle fonti dichiarate, semantica temporale correggibile e amministrazione persistente delle autorizzazioni. Non promettere connettori generici |
| Previsioni configurabili e verificabili | 19 strumenti MCP, selezione provider/opzioni/orizzonte e confronto multi-origine con revisioni e report persistiti; percorso wheel e recovery descritto nel report | Revisione complessiva dell’incremento e rischio numerico registrato; prova con host reale e interpretazione dei report nel percorso assistente |
| Domande ricorrenti e continuità | Core con candidate, policy di evidenza, watch, worker e cursori durevoli | Percorso dall’assistente per scegliere/salvare/gestire domande, ritrovarle aggiornate e leggere perché sono cambiate; nessuna attivazione basata solo su un forecast |
| Vista comprensibile | Console esistente e letture strutturate via MCP | Riepilogo nell’assistente e grafici/report con riferimenti ai risultati persistiti, senza dipendere da una dashboard locale |
| Sito pubblico e onboarding | Direzione e materiali tecnici definiti | Sito online curato con esempio completo reale, installazione e limiti, documentazione/contribution guide. Nessun backend pubblico di forecasting obbligatorio |
| Distribuzione verificata | Licenze e packaging presenti, prima verifica wheel e sdist | Eseguire tutto il percorso da artefatti installati su piattaforme dichiarate, definire nome/destinazioni, verificare documenti e manutenzione/contributi prima di pubblicare |

## Ordine di sviluppo corrente

1. [Previsioni configurabili e backtesting](superpowers/specs/2026-10-30-forecast-evidence-design.md): incremento implementato localmente e in verifica, con [piano esecutivo](superpowers/plans/2026-10-30-forecast-evidence.md) approvato dal proprietario il 30 ottobre 2026.
2. Setup e gestione dei servizi installati; verifica con un assistente reale.
3. Domande ricorrenti e riepiloghi/report attraverso gli stessi strumenti e lo stesso registro.
4. Sito, esempio pubblico e prova completa degli artefatti di release.

I confini possono restare circoscritti a fonti e calendari supportati; il percorso promesso deve essere completo per quei confini. La mancata disponibilità di nuove funzionalità non va mascherata con esempi simulati o controlli decorativi.

## Qualità e stato delle evidenze

La precedente verifica del collegamento MCP ha prodotto 665 test Python passati e un test del provider reale saltato. L’incremento corrente aggiunge previsioni configurabili e backtest congelati: [report e limiti della verifica](research/forecast-evidence.md). I report generici non sono attestazioni di discovery: il collegamento alla policy e al ciclo watch resta da implementare. Queste evidenze non chiudono i gate di installazione gestita, host desktop, domande ricorrenti, report nell’assistente, sito e destinazioni di release.

Queste prove non dimostrano compatibilità con host desktop, accuratezza predittiva generale, usabilità esterna o prontezza dell’intera release. La prova osservata con cinque persone resta sospesa per decisione del proprietario; non viene riportata come superata. Timestral e i relativi pesi mantengono condizioni e abilitazione separate; i controlli ordinari non effettuano inferenze a pagamento o download di pesi.
