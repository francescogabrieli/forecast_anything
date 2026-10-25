# Roadmap dei controlli di qualità

**Stato:** proposta di sequenza, senza scadenze. La CI attuale è il gate minimo già attivo; i controlli successivi entrano quando il codice e i rischi del progetto li rendono misurabili.

## Baseline attuale

Ogni pull request verso `main` verifica con Python 3.12 e 3.14:

- installazione coerente con `uv.lock`;
- lint e formattazione Ruff;
- suite pytest;
- build di wheel e source distribution.

Il run completo deve restare rapido e riproducibile. Modelli pesanti, benchmark estesi e controlli che richiedono servizi esterni vanno in job manuali o pianificati; non devono rendere casuale il gate di ogni pull request.

## Prossimo consolidamento del nucleo Python

### Limite alla dimensione dei file

Proposta: massimo **450 righe** per ogni file Python mantenuto in `src/`, `tests/` e `scripts/`. Il limite riguarda file scritti dal progetto; esclude codice generato, dipendenze copiate e dati fixture non Python.

Prima di attivarlo va suddiviso `tests/integration/test_runtime.py`, che oggi ha 560 righe, in moduli per esecuzione/errori, contratti e rappresentazioni. `src/forecast_anything/runtime.py` è a 384 righe, quindi il limite lascerebbe spazio a piccoli cambiamenti senza consentire che il modulo diventi il punto dove finisce ogni nuova responsabilità.

Un controllo semplice e deterministico deve indicare percorso e numero di righe e fallire se un file supera il limite. Se una responsabilità non si presta a una suddivisione leggibile, si rivede il limite o il perimetro nel piano: le eccezioni permanenti non vanno nascoste in una allowlist.

### Aggiornamenti controllati delle dipendenze

Configurare Dependabot per il lockfile `uv` e per GitHub Actions, con aggiornamenti settimanali. Ogni aggiornamento passa dagli stessi controlli CI e viene revisionato; niente auto-merge finché il progetto non ha esperienza sufficiente per automatizzarlo in modo affidabile. GitHub documenta gli ecosistemi `uv` e `github-actions` e gli aggiornamenti automatici: [ecosistemi supportati](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories), [Dependabot version updates](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-version-updates).

Il workflow pubblica i risultati sulla PR. La branch protection può rendere entrambi i job obbligatori prima del merge; configurarla prima di integrare altro codice su `main`.

## Quando arrivano modelli, operatori e valutazioni — piano 02

- **Controllo dei tipi:** scegliere un solo type checker dopo aver stabilizzato i contratti dei provider e degli operatori. Partire dal nucleo esistente, correggere la baseline e poi richiedere il controllo sui nuovi moduli. Evitare due checker sovrapposti.
- **Copertura dei rami:** pubblicare un report di branch coverage per scoprire rami non esercitati, soprattutto errori, compatibilità delle rappresentazioni e dati non maturati. Non imporre subito una percentuale globale: prima legare la soglia ai comportamenti importanti e ai test che li provano.
- **Gate di accuratezza:** aggiungere alle pull request un esperimento CPU breve, deterministico e con fixture piccole, contro la baseline stagionale. Controllare anche assenza di leakage temporale e split congelati. I benchmark completi su dataset con manifest, revisioni e holdout si eseguono manualmente o a intervalli regolari e pubblicano metriche e artefatti. Un test saltato o un modello non eseguito non conta come successo.
- **Vulnerabilità delle dipendenze:** con l’arrivo degli extra ML, aggiungere un audit del set installato e degli avvisi sulle dipendenze. Iniziare rendendo visibili i risultati; rendere bloccanti gli avvisi secondo una policy di severità solo dopo aver stabilito come gestire falsi positivi e aggiornamenti non compatibili. [pip-audit](https://github.com/pypa/pip-audit) è uno strumento PyPA per individuare vulnerabilità note.

## Quando arrivano API, worker e agenti — piano 03

- Test d’integrazione con riavvii, lease scadute, retry, migrazioni e fault injection: verificano il lavoro durevole già previsto dal piano 03.
- Verifica degli schemi API e dei client generati, così una modifica incompatibile diventa esplicita nella PR.
- Prima di introdurre workflow di release o permessi più ampi, aggiungere [actionlint](https://github.com/rhysd/actionlint) per controllare sintassi, espressioni e riferimenti dei workflow GitHub Actions, più una revisione statica specifica della loro sicurezza. Mantenere permessi minimi e SHA bloccati.
- Prima della pubblicazione pubblica, attivare gli strumenti GitHub disponibili per avvisi sulle dipendenze, rilevamento dei segreti e protezione dei push; aggiungere CodeQL per la scansione del codice secondo disponibilità del piano dell’account. I controlli disponibili dipendono dalle impostazioni e dal piano GitHub: [funzioni di sicurezza GitHub](https://docs.github.com/en/code-security/getting-started/github-security-features).

## Quando arriva la console e prima della release — piano 04

- Per TypeScript: formatter, lint, typecheck, test e build. Prettier entra quando esistono file frontend; non serve alla base Python attuale.
- E2E browser con provider e dati deterministici; prova i percorsi di collegamento fonte, scoperta, confronto e visualizzazione senza usare un LLM reale.
- Verifica dei link e degli esempi documentati; installazione pulita di wheel e source distribution fuori dal checkout, poi quickstart end-to-end.
- Controllo delle licenze e attribuzioni dei pacchetti, dati e pesi; inventario delle dipendenze della release.
- Test di installazione sui sistemi operativi che il progetto dichiara supportati. La matrice completa per sistema operativo arriva prima della release, non per forza su ogni PR.

Il piano 04 include già build frontend, test E2E, verifica della release installata e documentazione contribuibile; questa sequenza estende quei controlli senza duplicarli.

## Regola operativa

Ogni nuovo gate deve avere: il rischio che intercetta, un esito riproducibile, un responsabile per aggiornare la policy e un costo adeguato al valore. Le pull request mantengono controlli rapidi e deterministici; i test scientifici o infrastrutturali più costosi conservano un job manuale o pianificato con risultati visibili.
