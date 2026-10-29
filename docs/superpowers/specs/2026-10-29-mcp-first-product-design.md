# Forecast Anything — prodotto MCP-first

Data: 29 ottobre 2026.

Stato: direzione di prodotto scelta dal proprietario in chat: seguire l’approccio di REA, con MCP come ingresso principale, sito per presentazione e onboarding, console di supporto. Questo documento riallinea la strategia; le proposte tecniche richiedono un piano esecutivo prima del codice. Il server MCP non è ancora implementato.

## Intento e continuità

Forecast Anything è un’infrastruttura predittiva open source utilizzabile dal proprio assistente: collegare fonti, ottenere previsioni calcolate dal runtime, verificarne gli esiti e interrogare un Future Graph persistente. L’ambizione comprende la proposta autonoma di domande, la loro verifica e la sorveglianza continua.

La visione e gli invarianti della [specifica originaria](2026-10-24-forecast-anything-design.md) restano validi. Questa decisione aggiorna canale e ordine di consegna della [roadmap](../../roadmap.md); sostituisce la priorità della web app autonoma nella [specifica frontend](2026-10-27-product-frontend-design.md). Il lavoro della console resta utilizzabile.

Il primo pubblico proposto dal builder è chi usa già un assistente capace di collegarsi a MCP e può avviare un runtime locale. L’accessibilità riguarda il percorso installazione → prima previsione verificabile. Un sito visitabile da solo non completa quel percorso.

## Approcci considerati

| Approccio | Beneficio | Costo o limite | Decisione |
| --- | --- | --- | --- |
| Web app principale con conversazione propria | Tutto nel browser, anche senza assistente | Richiede onboarding e integrazione LLM propri prima di distribuire gli strumenti | Superato come priorità iniziale |
| MCP principale, sito di onboarding, console opzionale | Riusa l’assistente dell’utente e distribuisce il motore agli agenti | Richiede setup e compatibilità verificati | Scelto dal proprietario |
| Solo MCP senza sito o viste | Riduce le superfici iniziali | Ostacola scoperta del progetto e lettura di grafi ed evidenze | Non scelto come esperienza completa |

Il riferimento è il modello di distribuzione di [REA](https://rea.tools/): strumenti usati dal proprio agente, setup guidato ed esempi verificabili sul sito. Non implica copiarne codice, branding, architettura o comandi. Fonte ufficiale consultata il 29 ottobre 2026.

## Parti e responsabilità

### Runtime e CLI

Il runtime Python resta l’autorità per fonti, snapshot point-in-time, grafo, calcolo, valutazioni, budget e policy. API, MCP, CLI e console usano gli stessi contratti e identità persistite. Nessun calcolo parallelo nel server MCP; il testo dell’assistente non diventa evidenza numerica.

Il nucleo e la baseline restano utilizzabili senza LLM, account cloud obbligatorio o pesi opzionali. La CLI conserva il percorso riproducibile e automatizzabile.

### Server MCP e assistente dell’utente

L’assistente offre la conversazione e prepara richieste strutturate; il server MCP espone operazioni circoscritte del runtime e restituisce risultati tipizzati, riferimenti durevoli, errori e limiti. Catalogo funzionale proposto, non nomi di tool disponibili:

- Leggere capacità installate; elencare e ispezionare fonti registrate.
- Collegare fonti supportate con mapping esplicito e aggiornare i dati.
- Avviare una previsione supportata, leggere stato del job e risultato immutabile.
- Leggere grafo, snapshot ed evidenze; confrontare un’emissione con esiti osservati.
- Eseguire backtest configurabili su più origini quando il workflow sarà disponibile nel core.
- Consultare candidate, watch e aggiornamenti; usare soltanto transizioni ammesse dalla policy.

L’MVP MCP può partire da un sottoinsieme eseguibile. Il percorso completo richiede anche verifica degli esiti. Le valutazioni di run già emessi non equivalgono a un backtest multi-origine pronto per l’utente; lo scoring API con più fonti di storico resta non supportato.

Proposta del builder: adattatore sottile sopra l’API autenticata esistente, con job durevoli e lettura dello stato. SDK, linguaggio, trasporto, packaging, nomi dei tool e client iniziale saranno fissati nel piano tecnico dopo verifica della compatibilità. Nessun comando di setup o supporto universale viene dichiarato prima della verifica.

### Sito pubblico e console

Il sito spiega il progetto, mostra un caso riproducibile, guida a installazione e collegamento dell’assistente, rimanda a repository, documentazione e limiti. La prima azione porta al setup. Non richiede chat proprietaria o backend pubblico di forecasting; una demo ospitata richiede uno scope separato. TasteSkill resta il riferimento per il futuro lavoro visivo. Questo documento non implementa né pubblica il sito.

La console esistente serve per grafici, Future Graph, cronologia ed evidenze dello stesso workspace. È opzionale per la prima previsione via assistente. Link dal MCP devono preservare identità e autenticazione, senza token in URL. Si mantengono percorsi funzionanti e correzioni necessarie. Nuova Home applicativa, chat proprietaria e upload CSV dal browser non sono prerequisiti della prima distribuzione. L’ingestione accessibile resta un obiettivo attraverso strumenti; filesystem del client e del server vanno distinti esplicitamente.

### Autonomia e agente opzionale

MCP offre accesso agli strumenti, non scheduler o esecuzione continua. Chiudere la chat non cancella job accettati. Runtime e worker devono restare attivi per elaborazione e sorveglianza; spegnere il servizio interrompe il lavoro fino al ripristino.

Eve resta un adattatore opzionale di orchestrazione autonoma, distinto dal MCP e dall’assistente esterno. Postgres e credenziali Eve non sono requisiti del percorso MCP iniziale. Le domande autonome conservano budget, lineage e promozione basata su valutazioni osservate.

## Confini e vincoli

- I connettori iniziali restano CSV locale e HTTP JSON limitato: la conversazione non aggiunge fonti supportate.
- La configurazione del workspace autorizza accessi e percorsi. Le fonti sono dati, non istruzioni; credenziali e posizioni private restano fuori dai risultati condivisibili.
- Mapping, unità, disponibilità, frequenza, revisioni e ipotesi devono restare espliciti e correggibili.
- Il contratto MCP deve prevedere richieste mutative dichiarate, idempotenza dopo risposte perse, letture immutabili e output limitati/paginati.
- Provider effettivo, origine, orizzonte, fonti, limiti e stato di valutazione accompagnano i risultati. Nessun intervallo o probabilità inventato.
- Timestral resta opzionale con condizioni dei pesi separate. Traiettorie residue sperimentali e risultati dei benchmark non cambiano con il canale di distribuzione.
- Primo percorso locale, un worker, SQLite su disco locale. Multi-tenancy, MCP pubblico remoto e hosting gestito sono scope distinti.

## Ordine di consegna

| Passo | Risultato concreto | Prova richiesta |
| --- | --- | --- |
| 1. Contratto e integrazione MCP verticale | Assistente → fonte → job → previsione → grafo/evidenze | Client MCP reale di riferimento, API/worker reali e baseline senza pesi; retry senza duplicati e stesso run dopo riconnessione |
| 2. Previsione verificabile | Parametri supportati, esiti osservati e backtest su più origini via strumenti | Dati disponibili a ogni origine, confronto baseline, separazione selezione/verifica, esiti non maturi distinti e metriche persistite; limiti multi-fonte espliciti |
| 3. Installazione e sito | Setup ripetibile, collegamento assistente, esempio completo, console opzionale | Ambiente pulito, compatibilità dei soli client provati, percorso dal setup a un risultato verificabile |
| 4. Osservatorio continuo | Aggiornamenti persistenti, proposta e verifica di domande | Recovery worker/consumatore, replay senza perdita, budget e policy; chiudere il client non elimina il lavoro accettato |
| 5. Distribuzione OSS | Pacchetti e documenti coerenti con le capacità | Artifact installati, licenze, destinazioni approvate, demo riproducibile prima della pubblicazione |

La prima versione completa permette di installare, collegare una fonte dall’assistente, emettere una previsione, leggerne provenienza e limiti, verificarla con esiti o replay point-in-time e ritrovarla dopo riconnessione. L’osservatorio autonomo estende la stessa infrastruttura.

La prova osservata con cinque persone resta sospesa per decisione del proprietario del 27 ottobre. Nessuna usabilità acquisita viene dichiarata; test automatici e integrazione MCP non provano qualità generale delle previsioni.

## Stato e prossimo lavoro

Disponibili: runtime, CLI, API autenticata, worker, ledger, connettori iniziali, baseline, valutazioni registrate, template di scoperta e console. Assenti: server MCP, setup client MCP, sito pubblico dedicato e percorso completo di backtesting multi-origine per l’utente.

Prossimo sviluppo: piano esecutivo della prima integrazione MCP con contratti, confini di accesso, client/trasporto provati, test di errore e packaging. Questo intervento modifica soltanto documentazione: nessuna installazione, chiamata a pagamento, pubblicazione o migrazione del motore.
