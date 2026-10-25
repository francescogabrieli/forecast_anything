# Forecast Anything — roadmap completa

Specifica e roadmap approvate il 24 ottobre 2026 · Piano 01 implementato il 25 ottobre 2026 · Integrazione del branch da approvare.

Questa roadmap ordina risultati e dipendenze, senza assegnare date. Non è un elenco di funzionalità da costruire tutte prima di imparare qualcosa: ogni passaggio produce evidenze utilizzabili per decidere il successivo.

## Punto di partenza

[Specifica approvata](superpowers/specs/2026-10-24-forecast-anything-design.md). Il prodotto è un osservatorio predittivo continuo, generale e open source, basato su un Future Graph. Scopre domande candidate, le verifica e mantiene prospettive componibili. Timestral e agenti sono componenti; il runtime conserva il significato delle operazioni e le evidenze.

## Scelte tecniche proposte dal builder

Queste sono decisioni del piano, non preferenze già espresse dall’utente:

- Python 3.12 per il nucleo; Pydantic 2 per contratti serializzabili; NumPy per i calcoli; FastAPI per l’API.
- Grafo logico aciclico, verificato con strumenti della libreria standard; nessun database a grafo obbligatorio.
- SQLite su disco locale, transazioni brevi e WAL per il registro; un worker numerico per istanza iniziale. Il coordinamento di più host resta un’evoluzione separata.
- Timestral opzionale, primo checkpoint candidato 28M; baseline disponibili anche senza scaricare pesi. Revisione esatta di codice e pesi fissata nel lock delle integrazioni all’esecuzione.
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
| 4. Farlo usare senza competenze statistiche | Console, spiegazioni verificabili, scenari, installazione e esempi | Persone esterne collegano fonti e comprendono una scoperta |
| 5. Pubblicare il progetto come prodotto OSS | Repository, pacchetti, documentazione, dati attribuiti e contribution guide | Quickstart verificato su installazione pulita e matrice di capacità pubblica |
| 6. Preparare e fare il lancio | Demo provabile, video, articolo tecnico, messaggi per comunità pertinenti | Tutte le promesse del lancio rimandano a capacità dimostrabili |
| 7. Costruire adozione e community | Feedback, contributor, adattatori e prove su fonti nuove | Le nuove estensioni migliorano il sistema senza introdurre percorsi speciali nel nucleo |

## Piani esecutivi separati

1. [Nucleo, tempo e registro](superpowers/plans/2026-10-24-01-core.md): sei task; termina con un programma CLI funzionante senza LLM.
2. [Modelli, composizione ed evidenze](superpowers/plans/2026-10-24-02-models-and-evidence.md): cinque task; termina con benchmark riproducibili e query supportate esplicite.
3. [Osservatorio autonomo e agenti](superpowers/plans/2026-10-24-03-observatory-and-agents.md): sei task; termina con un servizio headless sorvegliabile via API.
4. [Esperienza, packaging e pubblicazione](superpowers/plans/2026-10-24-04-experience-and-release.md): quattro task; termina con una release candidata utilizzabile.

Ogni piano definisce file, interfacce, verifiche e commit. L’ordine dei piani è vincolante; il lavoro indipendente al loro interno può essere parallelizzato soltanto dopo aver fissato le interfacce condivise.

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

La console consente di collegare le fonti supportate, correggere interpretazioni, esplorare il grafo, leggere le scoperte, confrontare emissioni e scenari. La domanda naturale è un ingresso allo stesso runtime, non un motore parallelo.

Usare cinque persone esterne per una prova osservata: almeno quattro devono completare collegamento e comprensione di una scoperta senza istruzioni del maintainer. È una soglia proposta per il piano, non una misura statistica di adozione.

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
3. Demo interattiva con dati pubblici, provabile senza account; il replay storico è etichettato come replay e non usa dati successivi all’origine.
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

Il piano 01 (C1–C6) è implementato nel branch `feat/future-graph-core`, nella cartella canonica `Desktop/Projects/forecast_anything`, con un implementatore e una revisione indipendente per task. Il metodo subagent-driven e il branch nella cartella attuale sono stati scelti dall’utente il 25 ottobre 2026. La revisione complessiva è completata; l’integrazione del branch precede il piano successivo.

La CLI produce previsioni puntuali con baseline e conserva snapshot, grafi, emissioni ed eventi. [Stato del core e decisioni](implementation/core.md). I piani 02–04 restano da implementare; il prossimo task è M1, provider Timestral con verifica reale delle revisioni e prova di parità.

## Fonti tecniche per le scelte del piano

- [Timestral](https://github.com/mistralai/timestral): capacità e dipendenze del provider.
- [Eve](https://github.com/vercel/eve) e [self-hosting](https://eve.dev/docs/guides/deployment/self-hosting): servizio agenti separato, versionato perché in beta.
- [SQLite WAL](https://www.sqlite.org/wal.html): registro locale; più lettori, un writer alla volta, nessun WAL su filesystem di rete.
- [Node LTS](https://nodejs.org/en/about/previous-releases), [Vite](https://vite.dev/guide/).
- [UCI retail](https://archive.ics.uci.edu/dataset/502/online+retail+ii), [UCI consumi](https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption), [Wikimedia API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/).
