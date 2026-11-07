# Forecast Anything — roadmap completa

Specifica e roadmap approvate il 24 ottobre 2026 · Piano 01 implementato il 25 ottobre 2026 · PR #2 e #3 integrate in main il 26 ottobre 2026.

Questa roadmap ordina risultati e dipendenze, senza assegnare date. Non è un elenco di funzionalità da costruire tutte prima di imparare qualcosa: ogni passaggio produce evidenze utilizzabili per decidere il successivo.

## Punto di partenza

[Specifica approvata](superpowers/specs/2026-10-24-forecast-anything-design.md). Il prodotto è un osservatorio predittivo continuo, generale e open source, basato su un Future Graph. Scopre domande candidate, le verifica e mantiene prospettive componibili. Timestral e agenti sono componenti; il runtime conserva il significato delle operazioni e le evidenze.

## Prima release pubblicabile (30 ottobre 2026)

Il proprietario ha confermato un prodotto installabile e usabile dal proprio assistente, con sito pubblico curato e console locale opzionale. Il lancio richiede il ciclo completo installazione → fonti → previsione → verifica → domande ricorrenti → spiegazione degli aggiornamenti. I [criteri di rilascio e gap verificati](first-release.md) distinguono le prove già disponibili dai gate ancora aperti. Il [piano per previsioni configurabili e backtesting](superpowers/plans/2026-10-30-forecast-evidence.md) è implementato localmente e in verifica: [evidenze, limiti e gate ancora aperti](research/forecast-evidence.md).

## Direzione corrente — MCP-first (29 ottobre 2026)

Il proprietario ha scelto l’approccio di REA: **MCP come ingresso principale dal proprio assistente, sito per presentazione/onboarding e console opzionale per grafici ed evidenze**. La [specifica MCP-first](superpowers/specs/2026-10-29-mcp-first-product-design.md) aggiorna il canale e le priorità; conserva infrastruttura OSS, Future Graph, previsioni verificabili e scoperta autonoma di domande.

L’adattatore MCP locale stdio è implementato e verificato con il client SDK Python ufficiale `mcp==2.3.0`, API e worker indipendente, anche tramite wheel installata fuori dal checkout. La sorgente del sito dedicato è disponibile in `site/` e verificata localmente, ma resta da pubblicare; Codex Desktop ha un percorso storico baseline verificato e legge i risultati Timestral registrati. Il frontend esistente resta una console di supporto. Upload dal browser e chat proprietaria non precedono più il percorso dall’assistente. L’agente Eve resta opzionale e distinto dal MCP; il percorso iniziale non richiede Eve, Postgres o una chiave LLM del progetto.

### Prossime consegne, in ordine

| Priorità | Risultato da chiudere | Criterio di completamento |
| --- | --- | --- |
| 1. Integrazione MCP verticale — verificata nel checkout | 15 strumenti stdio: CSV, forecast da candidato, letture immutabili e valutazione singola | SDK ufficiale, API/worker reali, baseline senza pesi, disconnessione e replay della stessa richiesta/chiave; wheel installata fuori dal checkout. Host desktop ancora da validare. |
| 2. Verifica delle previsioni | Configurazione supportata e backtesting su più origini accessibili tramite strumenti | Origini point-in-time, confronto baseline, split separati e metriche persistite; esiti non maturi e limiti multi-fonte dichiarati |
| 3. Setup e sito | Sorgente del sito statico locale pronta per revisione, installazione locale riproducibile, collegamento al client, esempi e documentazione; console opzionale | Pubblicare dopo le decisioni di destinazione/nome; ambiente pulito e percorso completo dal setup a una previsione verificabile; solo client provati nella matrice di compatibilità |
| 4. Continuità e scoperta | Consultare aggiornamenti, proporre/verificare domande e sorvegliarle | Worker indipendente dalla chat, recovery, cursori durevoli, budget e promozione con evidenze |
| 5. Distribuzione e adozione | Pacchetti, sito e materiali coerenti con ciò che funziona | Artifact verificati e destinazioni approvate prima della pubblicazione |

Il nucleo già costruito viene riusato. Il backtest multi-origine è implementato nel core con cattura congelata, runner e job durevoli; MCP invia richieste e legge evidenze. Un backtest associato a una watch ricalcola la policy sul candidato congelato e riserva finestre finali non riutilizzabili; i report generici restano descrittivi e non qualificano le watch. La chiusura del client non cancella i job; elaborazione e watch richiedono runtime/worker attivi. La prova con cinque persone resta sospesa, senza bloccare queste consegne o dichiarare usabilità validata.

## Scelte tecniche proposte dal builder

Queste sono decisioni del piano, non preferenze già espresse dall’utente:

- Python 3.12 per il nucleo; Pydantic 2 per contratti serializzabili; NumPy per i calcoli; FastAPI per l’API.
- Grafo logico aciclico, verificato con strumenti della libreria standard; nessun database a grafo obbligatorio.
- SQLite su disco locale, transazioni brevi e WAL per il registro; un worker numerico per istanza iniziale. Il coordinamento di più host resta un’evoluzione separata.
- Timestral-28M locale richiesto per le nuove previsioni. Il lock fissa le revisioni di codice e pesi. La baseline stagionale resta il riferimento del confronto.
- Eve per l’adattatore agenti, isolato dal nucleo attraverso API e schemi JSON; Node 24 LTS. Eve è in beta: un esperimento verifica restart, provider e self-hosting prima di costruirci sopra. La versione viene fissata, non seguita automaticamente.
- Per la durata dei workflow Eve self-hosted si verifica il backend Postgres documentato; il registro dei forecast resta del runtime. Nessun account cloud obbligatorio per il nucleo.
- React, TypeScript e Vite per l’osservatorio; client derivato dal contratto API. Versioni compatibili risolte e bloccate all’avvio dell’implementazione.
- Un solo agente esploratore/orchestratore come configurazione iniziale; ruoli e strumenti separati. Ulteriori agenti entrano soltanto dopo un confronto misurato.
- Installazione completa con Docker Compose; modalità Python/CLI per usare il nucleo separatamente.
- Apache-2.0 è la licenza proposta per il nostro codice; il nome resta provvisorio. Licenze di modelli, dati e dipendenze restano distinte.

## Ordine generale

| Passaggio | Risultato concreto | Condizione per procedere |
| --- | --- | --- |
| 1. Rendere eseguibile il contratto | Grafo tipizzato, dati disponibili nel tempo, registro e CLI con baseline | Una previsione è ricostruibile, un aggiornamento non modifica il passato |
| 2. Provare modelli e composizione | Timestral collegato, operatori, valutazioni e esperimenti probabilistici | Le operazioni supportate sono dimostrate; quelle non giustificate vengono riconosciute |
| 3. Costruire l’osservatorio autonomo | Scoperta di domande, policy, aggiornamenti durevoli, agente e API | Un’interruzione non perde il lavoro e una domanda viene promossa o scartata con evidenze |
| 4. Renderlo accessibile dal proprio assistente | MCP, spiegazioni verificabili, console opzionale, installazione ed esempi | Percorso fonte → previsione → evidenze verificato con un client MCP reale; prova con persone esterne ancora sospesa |
| 5. Pubblicare il progetto come prodotto OSS | Repository, pacchetti, documentazione, dati attribuiti e contribution guide | Quickstart verificato su installazione pulita e matrice di capacità pubblica |
| 6. Preparare e fare il lancio | Demo provabile, video, articolo tecnico, messaggi per comunità pertinenti | Tutte le promesse del lancio rimandano a capacità dimostrabili |
| 7. Costruire adozione e community | Feedback, contributor, adattatori e prove su fonti nuove | Le nuove estensioni migliorano il sistema senza introdurre percorsi speciali nel nucleo |

## Piani esecutivi separati

1. [Nucleo, tempo e registro](superpowers/plans/2026-10-24-01-core.md): sei task; termina con un programma CLI funzionante senza LLM.
2. [Modelli, composizione ed evidenze](superpowers/plans/2026-10-24-02-models-and-evidence.md): cinque task; termina con benchmark riproducibili e query supportate esplicite.
3. [Osservatorio autonomo e agenti](superpowers/plans/2026-10-24-03-observatory-and-agents.md): sei task; termina con un servizio headless sorvegliabile via API.
4. [Esperienza, packaging e pubblicazione](superpowers/plans/2026-10-24-04-experience-and-release.md): quattro task; termina con una release candidata utilizzabile.

I piani elencati documentano l’esecuzione precedente e i relativi contratti. Dal 29 ottobre le prossime consegne seguono l’ordine MCP-first sopra; l’adattatore verticale è descritto nel [piano MCP](superpowers/plans/2026-10-29-mcp-vertical-slice.md) e nella [guida operativa](implementation/mcp.md). Il lavoro indipendente può essere parallelizzato soltanto dopo aver fissato le interfacce condivise.

## Controlli di qualità del repository

La CI attuale verifica installazione bloccata, Ruff, test e build su Python 3.12 e 3.14. La progressione dei controlli — incluso un limite proposto di 450 righe per file Python — segue i rischi di ogni fase ed è descritta nella [roadmap qualità e CI](quality-roadmap.md).

## Passaggio 1 — Prima le proprietà su cui costruire tutto

Implementare il contratto comune, gli snapshot point-in-time, la validazione delle dipendenze, le emissioni immutabili e gli eventi durevoli. La prima previsione usa una baseline e una fonte CSV normalizzata.

Il risultato non è ancora un osservatorio completo: è il nucleo su cui un’applicazione può fare affidamento per sapere cosa è stato calcolato e con quali informazioni.

**Evidenza richiesta:** prova con una correzione arrivata in ritardo, un ricalcolo e un riavvio. La vecchia emissione resta intatta e lo stesso idempotency key non produce un duplicato.

## Passaggio 2 — Rendere visibili le incognite scientifiche

Integrare Timestral, poi distinguere risultati puntuali, quantili marginali e traiettorie congiunte. Le composizioni utilizzano rappresentazioni compatibili, con unità e dipendenze esplicite.

Per gli eventi su un intero intervallo, eseguire un esperimento separato su distribuzioni note e dati reali. Un metodo che non dimostra utilità resta sperimentale o non supportato; il grafo e gli altri tipi di risposta rimangono utilizzabili.

**Evidenza richiesta:** confronto con baseline a parità di informazioni e orizzonte; split esplorazione/selezione/verifica congelati prima dei risultati; metriche e insuccessi esportabili.

I dati di validazione coprono tre contesti senza cambiare il nucleo: transazioni retail, consumi elettrici, attività Wikimedia. Calendari di consegne e limiti aggiunti agli esempi sono scenari sintetici dichiarati, non fatti presenti nei dataset.

## Passaggio 3 — Autonomia che produce lavori verificabili

L’agente propone associazioni e domande attraverso schemi e strumenti registrati. Il runtime decide se il piano è eseguibile e la policy decide se le evidenze permettono la sorveglianza.

La scoperta parte da famiglie esplicite di domande: deviazione dal comportamento atteso, cambiamento della previsione e superamento di un limite dichiarato. La disponibilità prima di un evento richiede l’operatore corrispondente. Il catalogo può crescere mantenendo i contratti.

**Evidenza richiesta:** fonti ambigue, dati testuali contenenti istruzioni, un’ipotesi convincente ma senza supporto, un modello fallito e un consumatore offline. Tutti producono stati e provenienza coerenti.

## Passaggio 4 — Trasformare il motore in un’esperienza

Dal 29 ottobre il percorso principale passa dall’assistente via MCP; sito e quickstart guidano il setup. La console è una vista opzionale sugli stessi risultati. Accesso conversazionale e backtesting devono utilizzare i contratti del core, senza introdurre un motore parallelo.

La console consente di collegare le fonti supportate, correggere interpretazioni, esplorare il grafo, leggere le scoperte, confrontare emissioni e scenari. La domanda naturale è un ingresso allo stesso runtime, non un motore parallelo.

Usare cinque persone esterne per una prova osservata: almeno quattro devono completare collegamento e comprensione di una scoperta senza istruzioni del maintainer. È una soglia proposta per il piano, non una misura statistica di adozione.

**Decisione del proprietario, 27 ottobre 2026:** questa prova è in sospeso. Non blocca lo sviluppo né la preparazione dell’anteprima tecnica. Il protocollo resta disponibile e il risultato non viene considerato acquisito; l’usabilità per persone non specialiste resta da validare.

**Evidenza richiesta:** report dei problemi incontrati, correzioni del percorso e nuovo tentativo dove necessario. Layout e testi si rifiniscono su questi risultati.

## Passaggio 5 — Preparare GitHub e il progetto pubblico

- Scegliere nome e owner dopo ricerca di repository, package registry e domini; non comprare nulla come conseguenza automatica della ricerca.
- Fissare licenza del nostro codice, attribution e inventario delle dipendenze; documentare separatamente pesi e dati.
- Portare nel repository specifica, piani e decisioni tecniche; usare commit piccoli e una CI che provi installazione, contratti e scenari di errore.
- Prima della pubblicazione avere README, quickstart, esempi, capability matrix, CONTRIBUTING, SECURITY, issue form e guida per un primo connettore.
- Pubblicare un’anteprima tecnica quando la demo centrale è riproducibile; classificare chiaramente stabilità e componenti sperimentali.
- Pubblicare pacchetto e immagini soltanto dopo aver verificato il percorso installato, non solo il checkout di sviluppo.

Il profilo community GitHub identifica questi documenti come parte della preparazione di un repository per utilizzatori e contributor. [Documentazione GitHub](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories)

## Passaggio 6 — Presentazione e distribuzione

### La promessa da mostrare

“Collega le tue fonti. Scopri cosa vale la pena prevedere. Osserva come cambiano i possibili futuri.”

Il nome può essere Forecast Anything; il testo del README precisa le capacità supportate. Timestral compare come primo motore e come contesto del progetto, mentre la spiegazione del valore resta valida cambiando provider.

### Materiale da preparare prima di annunciare

1. Demo breve: due fonti, una domanda scoperta, una prospettiva composta.
2. Demo di credibilità: nuova informazione, risposta aggiornata, confronto con un’emissione precedente e con gli esiti.
3. Esempio installabile con dati pubblici dal proprio assistente, con baseline senza chiavi del progetto o pesi; i requisiti dell’assistente sono dichiarati separatamente. Il replay storico è etichettato e non usa dati successivi all’origine. Una demo web ospitata è facoltativa e richiede uno scope separato.
4. README con video o GIF iniziale, esempio provabile, compatibilità, limiti, architettura e come contribuire.
5. Articolo che spiega un problema difficile risolto, con un esperimento riproducibile.
6. Confronto rispettoso con i progetti studiati: capacità comuni, differenze dimostrate e componenti riutilizzati.

### Canali e sequenza

Prima far provare il prodotto a utilizzatori e maintainer pertinenti. Correggere gli impedimenti, poi fare l’annuncio pubblico con demo, repository e articolo.

Preparare messaggi diversi per comunità di forecasting, agenti e prodotti open source: ciascuno deve contenere un risultato utile a quel pubblico. Contattare persone o pubblicare messaggi avviene durante l’esecuzione, con l’autorizzazione del proprietario del progetto.

Show HN è appropriato quando il progetto è realmente provabile; privilegiare accesso semplice e una discussione tecnica sostenibile. Le sue regole escludono le sole landing page e richiedono che il creatore possa discutere il lavoro. [Linee guida ufficiali](https://news.ycombinator.com/showhn.html)

Le sponsorizzazioni economiche arrivano dopo avere un percorso di prova efficace e costi di acquisizione misurabili. Preparare eventuali proposte per sostenere connettori, benchmark o documentazione; distinguere sponsorizzazione del lavoro e visibilità commerciale.

## Passaggio 7 — Crescita dopo il lancio

Registrare per ogni canale visite aggregate, avvii della demo, quickstart completati, utilizzo ripetuto e contributor. Le stelle sono un risultato desiderato, senza attribuire a una formula la capacità di garantirle. La telemetria del prodotto self-hosted resta disattivata per default.

Creare issue contribuibili su connettori e dataset ben delimitati, con contratto e test di accettazione. Accogliere casi non coperti nella capability matrix; evitare di promettere supporto generale sulla base di una sola demo.

Usare le segnalazioni e i ritorni degli utilizzatori per ordinare miglioramenti e integrazioni. Le estensioni accettate devono riutilizzare i contratti del grafo. La fase successiva può includere Afterplot, nuovi motori, nuovi operatori e, quando giustificato dai carichi, persistenza e worker distribuiti.

## Stato dell’esecuzione

Il piano 01 (C1–C6) e i piani 02 e 03 sono integrati in `main` tramite PR #2. La recovery Eve/Postgres interrompe un turno dopo `inspectSource`, riavvia i servizi e verifica la stessa sessione, lo stesso operation ID e il budget persistente. La fixture anticipa la scadenza della lease Graphile Worker invece di attendere quattro ore; la policy reale del lock scaduto resta una dipendenza operativa.

Il 26 ottobre 2026 è stata approvata la configurazione GPT-6 Luna per l’orchestrazione Eve e Mistral soltanto per Timestral. Lo smoke GPT limitato è stato eseguito con una richiesta sintetica: una chiamata `inspect_source` su dati locali, 518 token in ingresso e 23 in uscita. Conferma il percorso base provider-Eve-core e l’operation ID persistito; non misura qualità del modello né prontezza per la produzione.

Il piano 04 è in corso: U1, U2 e l’implementazione di U3 sono integrate tramite PR #2; la copertura E2E a due sorgenti è stata completata e integrata tramite PR #3. Nel piano 02, la parità CPU fp32 Timestral e il confronto M4 sui tre domini sono stati eseguiti con autorizzazione del proprietario per una valutazione locale personale e integrati tramite PR #5; la licenza dei pesi continua a valere per ogni utilizzatore e deployment. La PR #6 aggiunge le traiettorie residue congiunte; la PR #7 documenta lo smoke Compose Eve/LLM su ambiente pulito, limitato a build, avvio e salute locale senza chiamata al provider.

Il 27 ottobre 2026 il percorso del [primo forecast dopo l’attivazione](superpowers/plans/2026-10-26-first-source-forecast.md) è stato verificato con API e worker reali: scelta esplicita dell’utente, snapshot della fonte, baseline a un passo e apertura del run persistito. Il refresh usa una nuova epoca e i tentativi dopo risposte di rete perse riutilizzano la richiesta originale. La console mostra titoli italiani per le domande sorvegliate e conserva il motivo originale. La fixture E2E mantiene l’orologio fisso; la modalità per lo studio osservato usa `FA_USABILITY=1` e date correnti congelate all’avvio.

Il [test osservato con cinque persone](research/console-usability-study.md) è in sospeso per decisione del proprietario e non blocca il lavoro successivo. Le tre issue iniziali per contributor sono aperte: [paginazione HTTP #9](https://github.com/francescogabrieli/forecast_anything/issues/9), [ricetta dati #10](https://github.com/francescogabrieli/forecast_anything/issues/10), [operatore differenza #11](https://github.com/francescogabrieli/forecast_anything/issues/11). Restano la risoluzione di nome/owner/registry per la pubblicazione e i passaggi di preparazione della release. Lo smoke locale dell’agente e i benchmark non dimostrano qualità generale né prontezza di produzione. [Stato del core e decisioni](implementation/core.md).

La [verifica della candidata tecnica del 27 ottobre](research/release-candidate-check.md) copre wheel installata fuori dal checkout e immagini baseline ricostruite in workspace temporaneo, con primo forecast, invio idempotente e run invariato dopo riavvio. Il pacchetto sorgente esclude ora i materiali locali di lavoro con un test di regressione. La candidata resta locale: nessun pacchetto o immagine è stato pubblicato su registry.

Il 29 ottobre 2026 il [frontend di prodotto](superpowers/specs/2026-10-27-product-frontend-design.md), approvato dal proprietario, sostituisce la console su pagina unica: Home con fonti e previsioni registrate, Fonti con mappatura guidata, Osservatorio con risultato e Future Graph prima della cronologia tecnica, e Workspace per la connessione al core. Il progetto visivo segue TasteSkill; grafici ed evidenze consumano gli stessi contratti del runtime. Lo storico del grafico richiede la fonte risolta dal grafo e dal binding registrato nel run. Le metriche mostrate sono valutazioni già persistite, non un nuovo backtesting interattivo.

La priorità frontend qui descritta è stata aggiornata dalla decisione MCP-first del 29 ottobre: l’integrazione verticale MCP sopra il runtime esistente è verificata con il client SDK ufficiale, inclusi permessi delle fonti dopo riconnessione, esiti osservati e wheel installata; previsione configurabile, backtesting su più origini, controlli delle watch e qualifica vincolata al candidato tramite backtest sono implementati localmente; le [prove Desktop storiche](research/desktop-assistant-acceptance.md) e le [prove SDK con Timestral reale](research/required-timestral-acceptance.md) coprono percorsi distinti; setup guidato e rilascio restano da completare. I report generici restano separati dalla qualifica. L’upload CSV dal browser è differito. Demo e pubblicazione accompagnano queste capacità senza sostituirle.

La consegna MCP del 30 ottobre usa CSV locali con root approvate e allowlist degli ID per profile/refresh dopo riavvio; la config privata ora offre comandi persistenti per elencare, concedere e revocare questi permessi. Il mapping guidato richiede frequenza e fuso espliciti e mantiene le colonne candidate come suggerimenti da verificare. Risposte degli strumenti limitate a 64 KiB e richieste/risposte upstream a 1 MiB: la paginazione non elimina questi limiti. La registrazione HTTP via MCP e il setup/sito guidato restano successivi. L’incremento del 4 novembre porta il catalogo a 26 strumenti con forecast configurabili, backtest CSV multi-origine congelati, riepiloghi dei report e gestione delle watch con riepilogo di run registrati. I report generici non qualificano le watch; un backtest associato a un candidato può attivare la policy solo su finestre finali non riutilizzate. API, worker e MCP sono processi separati; il percorso baseline non richiede chiavi LLM.

Il 4 novembre 2026 è stata aggiunta la sorgente locale del sito statico con esempi sintetici emessi dal runtime, istruzioni da checkout, limiti del prodotto e link a setup/MCP/contributi. TasteSkill non segnala errori di layout o funzionalità; restano non verificati pubblicazione, destinazione web e setup dentro Codex Desktop.

Il 7 novembre 2026 la fase 2 aggiunge domande persistenti con revisioni semantiche e riferimenti, operazioni recuperabili dopo riconnessione sul job queue esistente, riepiloghi compatti degli snapshot e presentazioni condivise fra API e MCP. Migrazione 011 e schemi TypeScript sono generati; i test verificano retry concorrenti e un CSV sintetico da 320 righe entro il limite MCP senza leggere SQLite. La candidata è in revisione; vedi [rapporto e procedura riproducibile](research/phase-2-persistent-questions.md).

## Fonti tecniche per le scelte del piano

- [Timestral](https://github.com/mistralai/timestral): capacità e dipendenze del provider.
- [Eve](https://github.com/vercel/eve) e [self-hosting](https://eve.dev/docs/guides/deployment/self-hosting): servizio agenti separato, versionato perché in beta.
- [SQLite WAL](https://www.sqlite.org/wal.html): registro locale; più lettori, un writer alla volta, nessun WAL su filesystem di rete.
- [Node LTS](https://nodejs.org/en/about/previous-releases), [Vite](https://vite.dev/guide/).
- [UCI retail](https://archive.ics.uci.edu/dataset/502/online+retail+ii), [UCI consumi](https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption), [Wikimedia API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/).
