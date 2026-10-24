# Forecast Anything — specifica di progetto

Data: 24 ottobre 2026

Stato: approvata dall’utente in chat il 24 ottobre 2026; passaggio successivo: revisione del piano prima dell’implementazione.

Nome di lavoro: Forecast Anything; disponibilità e nome definitivo da verificare.

## 1. Intento

Costruire un’infrastruttura predittiva open source generale: collegare fonti differenti, scoprire quali fenomeni e domande meritano di essere osservati, mantenere rappresentazioni dei loro possibili futuri e combinare tali rappresentazioni in risposte verificabili.

L’esperienza principale è un osservatorio continuo. Una persona collega le fonti; il sistema propone cosa può analizzare e cosa vale la pena sorvegliare, verifica le proprie proposte, aggiorna le previsioni e porta all’attenzione i cambiamenti rilevanti. Le applicazioni possono utilizzare lo stesso nucleo direttamente.

La visione è trasversale ai settori. Il supporto concreto si estende attraverso connettori, modelli e operatori. La generalità non implica che ogni fenomeno sia prevedibile, né che una relazione statistica permetta di simulare automaticamente gli effetti di un intervento.

## 2. Decisioni già concordate

- Il prodotto principale è l’infrastruttura open source; Afterplot è una possibile applicazione.
- La visione resta generale: non viene definito un settore esclusivo.
- L’esperienza principale è la sorveglianza predittiva continua, interrogabile anche su richiesta.
- Il sistema deve scoprire autonomamente anche domande candidate da tenere sotto osservazione.
- Gli agenti interpretano, esplorano e preparano il lavoro; strumenti di calcolo espliciti producono i risultati numerici.
- Timestral è il primo motore candidato; il nucleo deve consentire modelli intercambiabili.
- L’approccio scelto è Future Graph: una rappresentazione condivisa dei sistemi collegati, delle dipendenze e dei possibili futuri.
- Affidabilità, provenienza, incertezza e confronto con gli esiti fanno parte del prodotto.
- La roadmap successiva comprenderà anche presentazione, pubblicazione, distribuzione e community.

Tutte le scelte introdotte nelle sezioni successive sono proposte di progettazione, non ulteriori decisioni già espresse dall’utente.

## 3. Approcci considerati

### Analisi autonome ricorrenti

Gli agenti preparano analisi eseguite periodicamente dal runtime. Ogni analisi conserva dati e risultati; le composizioni sono definite nei suoi workflow. È flessibile per molti lavori indipendenti, ma le ipotesi comuni richiedono coordinamento tra analisi.

### Future Graph — approccio scelto

Fenomeni, fonti, calendari, ipotesi, modelli e risultati condividono una rappresentazione comune. Le analisi riutilizzano questi elementi; gli aggiornamenti si propagano alle dipendenze interessate.

È stato scelto perché rende centrale la composizione dei futuri di sistemi differenti. Richiede contratti precisi su significato dei dati, tempo, relazioni e incertezza. Un grafo generico di nodi e archi, senza questi contratti, non soddisfa il progetto.

## 4. Esperienza proposta

### Collegamento e comprensione

La persona collega una o più fonti. Il sistema analizza schema, qualità, frequenza, unità, identità delle entità e copertura temporale. Propone una mappa dei fenomeni osservabili e delle eventuali corrispondenze tra fonti.

Le ambiguità che cambiano il significato del calcolo vengono rese esplicite. Un agente può suggerire che due colonne identifichino lo stesso prodotto; il runtime conserva che si tratta di una corrispondenza proposta finché non viene confermata o verificata con regole adeguate. Un campo sconosciuto non viene trasformato silenziosamente in un fatto.

### Scoperta e verifica delle domande

Gli agenti propongono domande candidate usando dati, metadati e conoscenza dei metodi disponibili. Esempi trasversali: possibile superamento di un limite dichiarato, cambiamento rispetto al comportamento stagionale, indisponibilità prima di un evento programmato, variazione importante rispetto a una previsione precedente.

Ogni candidata ha una motivazione, requisiti di dati, metodo di valutazione e costo stimato. Inizialmente è un’ipotesi da verificare, non un allarme operativo.

La valutazione usa finestre temporali separate per esplorazione, selezione e verifica finale. La ricerca automatica è limitata da budget e criteri espliciti; registra anche le ipotesi scartate, per non presentare soltanto successi scelti retrospettivamente. I metodi di selezione devono essere compatibili con le proprie assunzioni statistiche; non si promette un controllo universale dei falsi positivi.

Una domanda può diventare sorvegliata automaticamente secondo una policy visibile. L’utente può correggere priorità e rilevanza, senza dover scegliere algoritmi.

### Sorveglianza e interrogazione

Il runtime aggiorna le prospettive quando arrivano nuove osservazioni o cambiano informazioni conosciute e ipotesi. Genera una segnalazione interna quando cambia una condizione sorvegliata, emerge una nuova evidenza rilevante o degrada la qualità di una risposta utilizzata.

La persona può chiedere cosa sostiene un risultato, cosa è cambiato e quali ipotesi sono determinanti. Può creare scenari con input dichiarati. I risultati distinguono sempre osservazioni, programmi, assunzioni e stime.

La prima interfaccia proposta è un osservatorio utilizzabile da persone non specialiste, accompagnato da un’API sullo stesso nucleo. Il layout, il linguaggio visuale e il packaging non sono ancora progettati.

## 5. Il contratto comune del futuro

Ogni risorsa predittiva deve esporre almeno:

1. **Identità e significato:** fenomeno, entità, unità, frequenza, aggregazione, fuso orario e orizzonte.
2. **Origine temporale:** snapshot degli input, informazioni disponibili all’emissione e istante da cui inizia il futuro stimato.
3. **Dipendenze:** fonti, calendari, modelli, trasformazioni e ipotesi, ciascuno con versione e ruolo.
4. **Rappresentazione numerica:** stima puntuale, quantili marginali oppure traiettorie congiunte; eventuali campioni hanno significato e assunzioni dichiarati.
5. **Operazioni supportate:** quali trasformazioni e interrogazioni sono ammesse da quella rappresentazione.
6. **Evidenze:** valutazioni, baseline, campioni disponibili, freschezza e limiti conosciuti.
7. **Stato e storia:** emissioni immutabili, riferimento alla risposta corrente utilizzabile ed eventi di aggiornamento.

Il contratto è estendibile. Non è ancora uno standard pubblico né un protocollo da imporre ad altri progetti: prima deve dimostrare utilità nell’infrastruttura stessa.

## 6. Entità del Future Graph

| Entità | Responsabilità |
| --- | --- |
| Fonte | Accesso alle osservazioni e metadati; disponibilità e revisioni dei dati |
| Fenomeno | Identità semantica della quantità o sequenza osservata |
| Informazione futura conosciuta | Calendario o impegno programmato, con versione e data di disponibilità |
| Ipotesi di scenario | Input assunto, mantenuto distinto da fatti e programmi |
| Previsore | Modello, baseline o metodo con capacità dichiarate |
| Trasformazione | Formula o operatore con regole su unità, tempo e incertezza |
| Evento futuro | Condizione interrogabile sulle prospettive, con metodo di stima e valutazione |
| Sorveglianza | Politica di aggiornamento, rilevanza e segnalazione di una domanda |
| Emissione | Risultato immutabile di una specifica esecuzione |
| Valutazione | Confronto versionato tra emissione e osservazioni successive |

Le relazioni eseguibili dichiarano il proprio significato: contabile, fisico, statistico o causale supportato da un modello adeguato. Una somiglianza scoperta dall’agente è una relazione candidata, non una dipendenza causale acquisita.

Proposta iniziale: il grafo di una singola esecuzione deve essere aciclico. Dipendenze ritardate possono essere espanse nel tempo; relazioni simultanee cicliche richiedono un risolutore con un contratto dedicato e non vengono eseguite implicitamente.

## 7. Componenti e responsabilità

### Connettori e preparazione dei dati

Acquisiscono osservazioni e informazioni programmate; producono snapshot identificabili e ricette di trasformazione ripetibili. Event time e momento di disponibilità del dato sono distinti.

Proposta per il primo contratto numerico: serie con timestamp, identità e valori numerici, con una frequenza definita. Dati irregolari possono passare da una trasformazione esplicita; unità o aggregazioni sconosciute impediscono le composizioni che le richiedono. Testi e documenti possono dare contesto agli agenti o informazioni estratte verificabili, senza essere automaticamente serie prevedibili.

La matrice di compatibilità dei connettori cresce per capacità, senza identificare il prodotto con un solo settore. Le credenziali restano separate da prompt, risultati e manifest condivisibili.

### Agenti

Ruoli logici: comprensione delle fonti; esplorazione di domande; preparazione dei piani; spiegazione dei risultati. Non sono necessariamente agenti o processi distinti: numero, delega e parallelismo vanno giustificati da valutazioni di qualità, costo e latenza.

Un agente produce un piano strutturato usando strumenti registrati. Non può registrare una propria percentuale testuale come risultato numerico di un modello. Contenuti letti dalle fonti sono dati, non istruzioni operative da eseguire.

Gli agenti restano sostituibili. Il nucleo è utilizzabile direttamente senza un LLM, purché il chiamante fornisca definizioni esplicite.

### Validatore e pianificatore del runtime

Controlla struttura del piano, disponibilità temporale dei dati, identità, unità, frequenze, capacità dei modelli e rappresentazione dell’incertezza. Individua dipendenze da aggiornare, budget e risultati riutilizzabili.

Un piano valido formalmente non è per questo statisticamente valido: esecuzione e valutazione devono produrre le evidenze richieste dalla domanda.

### Motori numerici

Timestral è il primo candidato per le previsioni; baseline semplici sono parte obbligatoria del confronto. Il contratto del provider dichiara input ammessi, covariate, output, orizzonti, versioni e vincoli di esecuzione.

La scelta di un provider si basa su capacità e valutazioni pertinenti, non soltanto sul giudizio dell’agente. Eventuali fallback dichiarano il modello effettivo che ha risposto.

Codice dell’infrastruttura, librerie e pesi dei modelli hanno licenze distinte. Le condizioni dei pesi Timestral devono restare esplicite e il suo utilizzo non deve essere necessario per far funzionare il nucleo.

### Composizione e interrogazioni probabilistiche

Gli operatori dichiarano come trattano unità, allineamento temporale, vincoli e dipendenze. Una somma di quantili marginali non viene presentata come quantile della somma.

Domande come il superamento di una soglia almeno una volta in un intervallo richiedono informazioni sulla dipendenza temporale. Il runtime usa un provider o metodo adeguato, espone una risposta condizionata ad assunzioni verificabili oppure dichiara la domanda non supportata.

Ricostruire traiettorie da quantili attraverso assunzioni sui residui è un possibile componente di ricerca, non una capacità già risolta. Eventuali metodi dovranno essere valutati sugli eventi interrogati, non soltanto sull’errore delle singole previsioni.

### Valutazione ed evidenze

Confronta baseline e modelli sugli stessi dati disponibili all’origine, per orizzonte e fenomeno. Registra errore, copertura e ampiezza degli intervalli; per eventi probabilistici valuta anche qualità delle probabilità e utilità della condizione sorvegliata.

Le osservazioni future rendono progressivamente valutabili le emissioni passate. Un risultato ancora non maturato è distinto da uno valutato. Correzioni degli esiti producono nuove versioni della valutazione.

Lo stato non è un punteggio universale di affidabilità. Deve distinguere almeno: candidato, in verifica, sorvegliato, provvisorio per evidenza insufficiente, scaduto, degradato e non supportato. Gli stati hanno cause leggibili e le soglie della policy sono versionate.

### Persistenza, aggiornamenti ed eventi

Conserva definizioni, snapshot, emissioni, valutazioni e dipendenze. Un aggiornamento crea una nuova emissione, senza modificare quella precedente.

L’esecuzione riprende dopo un’interruzione; retry e aggiornamenti usano identità stabili. Le segnalazioni pubblicate hanno un registro durevole e un cursore per i consumatori. La consegna proposta è almeno una volta con deduplicazione; non si promette una generica consegna esattamente una volta.

È possibile interrogare sia lo stato corrente sia ciò che il sistema aveva effettivamente emesso in passato. Un replay distingue dati di allora da dataset successivamente corretti.

## 8. Autonomia e rilevanza

L’autonomia riguarda esplorazione, preparazione, valutazione e sorveglianza. Ogni esecuzione ha limiti di risorse, accesso e durata; la ricerca automatica non è una scansione infinita di ogni combinazione possibile.

Proposta: una nuova domanda entra nella sorveglianza attraverso una policy esplicita che considera supporto dei dati, evidenze di utilità e motivazione della rilevanza. Il sistema propone priorità; la persona può correggerle. Limiti economici, fisici o organizzativi non vengono inventati come fatti: devono essere dichiarati o acquisiti da fonti con un significato verificato.

Segnalazioni duplicate vengono raggruppate e correlate alla stessa modifica delle fonti. La persona può capire perché una scoperta è stata evidenziata e perché altre candidate sono state scartate.

Per questa proposta il prodotto osserva, interroga e segnala. Operazioni che modificano sistemi esterni non fanno parte del contratto iniziale: richiederebbero una progettazione specifica distinta dalla previsione.

## 9. Universalità e confini

L’universalità risiede in un contratto comune e in estensioni componibili. Il primo rilascio deve pubblicare una matrice onesta di fonti, operazioni, metodi e tipi di risposta supportati.

Non sono obiettivi di questa specifica: predire ogni fenomeno; inferire automaticamente causalità da correlazioni; digitalizzare qualsiasi grafico o immagine; costruire una piattaforma enterprise distribuita prima di dimostrare il nucleo. Questi confini non scelgono un settore: distinguono capacità definite da problemi ancora aperti.

L’esperienza viene considerata fallita se produce soltanto curve persuasive, se richiede di ricostruire manualmente tutta la pipeline per ogni fonte, se nasconde assunzioni o fallback, oppure se le scoperte automatiche generano rumore senza utilità ricorrente.

## 10. Prove che l’architettura dovrà superare

Queste sono condizioni di validazione del progetto, non ancora una roadmap esecutiva.

- Lo stesso contratto deve sostenere esempi indipendenti di domanda/disponibilità, consumo/capacità e attività/carico, senza cambiare il nucleo per ciascun settore.
- Un caso deve combinare almeno due fonti e una relazione esplicita: una nuova informazione aggiorna soltanto i risultati interessati e lascia ricostruibile la dipendenza.
- Una domanda candidata deve poter essere proposta, verificata e promossa oppure scartata con una motivazione documentata.
- Un replay con dati tardivi non deve usare informazioni indisponibili all’emissione originale.
- Una query che richiede dipendenze non disponibili deve essere riconosciuta come non supportata o condizionata, senza percentuali inventate.
- Baseline e modelli devono essere confrontabili con valutazioni temporali separate dalla selezione.
- Un riavvio e un consumatore temporaneamente offline non devono far perdere la storia delle emissioni e degli aggiornamenti pubblicati.
- Persone che non hanno progettato il sistema devono riuscire a collegare fonti supportate, comprendere una scoperta e tornare a verificarla quando arrivano nuovi dati.

Soglie quantitative, dataset, carichi e protocolli di queste prove devono essere fissati prima di eseguire i relativi esperimenti, nella fase di pianificazione.

## 11. Ricerca necessaria e scelte lasciate al builder

### Incognite da risolvere con esperimenti

- In quali condizioni i metodi disponibili permettono query sugli eventi con probabilità utili e valutabili.
- Quanto la comprensione automatica delle fonti riduca davvero il lavoro manuale senza introdurre errori semantici.
- Quali criteri rendano utile la scoperta autonoma e gestibile il volume delle segnalazioni.
- Quali invarianti e operatori bastino a comporre processi trasversali senza diventare una collezione di integrazioni ad hoc.

Il piano dovrà affrontare queste incognite con prove circoscritte e criteri di decisione, prima di assumere che le funzionalità siano disponibili.

### Scelte tecniche delegate alla pianificazione

Linguaggio del nucleo, framework degli agenti, persistenza, rappresentazione fisica del grafo, scheduler, API, UI e packaging non sono stati scelti dall’utente. Il builder può proporre default coerenti con: esecuzione autonoma su infrastruttura propria; separazione tra nucleo e agenti; accesso programmatico; facilità di prova; dipendenze dei modelli isolate.

Un database a grafo non è implicato dalla scelta Future Graph: la rappresentazione logica può essere implementata con altri strumenti se ne conserva la semantica.

La licenza open source del progetto e il nome definitivo restano decisioni da proporre esplicitamente prima della pubblicazione. Non devono bloccare le prove architetturali.

## 12. Posizionamento e futura roadmap

Il messaggio da dimostrare è: collegare fonti, scoprire domande e mantenere possibili futuri componibili e verificabili. Non viene rivendicata unicità assoluta né una garanzia di accuratezza universale.

FoundationForecast, TServe, Tempolith, OpenSearch, Grafana e progetti di query probabilistiche sono riferimenti da confrontare e possibili componenti da riutilizzare. API comuni, persistenza e scheduling non costituiscono da soli la differenziazione.

Dopo l’approvazione della specifica, la roadmap dovrà ordinare ricerca, prove del nucleo, sviluppo, esperienza di utilizzo, documentazione, licenze, repository, esempi riproducibili, demo, lancio, distribuzione e manutenzione della community. Sarà organizzata per risultati e dipendenze, senza una scansione temporale imposta.

La comunicazione dovrà mostrare sia la capacità di collegare sistemi sia la qualità delle risposte: previsioni emesse, esiti, assunzioni e casi non supportati. Le stelle GitHub sono un obiettivo di distribuzione; prove riuscite, utilizzo ricorrente e contributi permettono di valutare anche il valore del progetto.

## 13. Riferimenti consultati

- [Timestral: repository ufficiale](https://github.com/mistralai/timestral) e [annuncio Mistral](https://mistral.ai/news/timestral/).
- [Timestral: licenza dei pesi 28M](https://huggingface.co/mistralai/Timestral-28M/blob/main/LICENSE).
- [FoundationForecast](https://github.com/TimeCopilot/foundationforecast).
- [TServe](https://github.com/sktime/tserve).
- [Tempolith](https://github.com/MinaSaad1/Tempolith).
- [Grafana scenes-ml](https://github.com/grafana/scenes-ml).
- [OpenSearch Forecasting API](https://docs.opensearch.org/latest/observing-your-data/forecast/api/).
- [HierarchicalForecast](https://github.com/Nixtla/hierarchicalforecast).
- [tspDB](https://tspdb.mit.edu/) e [GenSQL](https://people.csail.mit.edu/rinard/paper/pldi24.sql.pdf), come precedenti di interrogazioni e rappresentazioni predittive/probabilistiche.

Le capacità dei progetti citati derivano dalla ricerca e da letture mirate di documentazione e codice svolte durante il brainstorming. Non è stato eseguito un audit completo della loro qualità o maturità.
