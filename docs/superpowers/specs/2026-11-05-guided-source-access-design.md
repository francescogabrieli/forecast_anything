# Collegamento guidato e permessi persistenti delle fonti

## Intento

Chi collega una fonte deve capire e correggere come vengono interpretati tempo e valori; chi autorizza una fonte a essere letta dall'assistente deve poter rivedere o revocare il permesso anche dopo il riavvio.

## Stato attuale

La console consente già di ispezionare, mappare e registrare CSV e HTTP JSON. Il mapping guidato mostra i campi di tempo, disponibilità, frequenza e fuso, ma parte con `UTC` e `1d` già impostati; il profilatore accetta anche alcune costanti vuote. L'allowlist MCP degli ID fonte è presente nella config privata del workspace, ma non esiste un comando supportato per gestirla. Una registrazione CSV riuscita autorizza l'ID solo per la vita del processo MCP.

## Approcci considerati

1. **Lasciare l'allowlist nelle variabili d'ambiente e aggiungere istruzioni:** minimo codice, ma l'utente deve modificare JSON o ambiente manualmente e la revoca resta poco visibile.
2. **Aggiungere permessi amministrabili dal server/API o dalla console:** più comodo, ma allargherebbe il confine di autorità e permetterebbe di cambiare una policy operatore tramite il servizio o il browser.
3. **Usare la config privata del workspace esistente con comandi CLI espliciti, e chiedere all'utente di riavviare MCP per applicare i cambiamenti — scelto:** mantiene l'autorità locale e rende grant/revoke persistenti senza creare una nuova superficie remota.

## Decisioni

- `forecast-anything permissions list|grant|revoke --config PATH` amministra gli ID fonte autorizzati nella config privata del workspace.
- Un grant richiede una fonte già registrata nel catalogo del workspace; un revoke rimuove l'ID anche se la fonte non esiste più.
- La scrittura della config è atomica e mantiene i permessi file privati. Il comando non stampa token, percorsi fonte o credenziali.
- MCP carica i grant all'avvio. Le modifiche richiedono il riavvio del client MCP; non sono mutate automaticamente da una chiamata dello strumento `register_csv_source`.
- Nel nuovo mapping, frequenza e fuso orario non hanno valori iniziali. L'utente deve sceglierli. I suggerimenti di colonna restano suggerimenti e non vengono applicati automaticamente.
- Un timestamp senza fuso usa il fuso IANA dichiarato; la frequenza è dichiarata, non dedotta dal campione. Gli orari locali ambigui o inesistenti continuano a essere rifiutati.
- Una costante stringa vuota non risolve ruoli di osservazione che richiedono un'identità o un significato (`event_time`, `available_at`, `revision`, `series_id`, `unit`).

## Fuori ambito

Upload dal browser, nuovi connettori, permessi OAuth, amministrazione remota, autorizzazioni per utente o tenant e aggiornamento a caldo della policy MCP.

## Criteri di accettazione

- Un operatore può elencare, concedere e revocare permessi senza modificare a mano il JSON.
- Un grant inesistente è rifiutato; grant e revoke restano dopo aver riletto la config.
- La config mantiene modalità file `0600` anche dopo l'aggiornamento e gli output non rivelano il token.
- Il mapping iniziale non accetta silenziosamente `UTC` o `1d`; un utente può scegliere il fuso e la frequenza e correggerli prima di attivare la fonte.
- I campi suggeriti restano modificabili dall'utente e non diventano automaticamente la mappatura attiva.
- Le istruzioni spiegano che grant/revoke valgono al successivo riavvio di MCP e che un permesso su una fonte HTTP può avviare letture di rete dalla macchina locale.
