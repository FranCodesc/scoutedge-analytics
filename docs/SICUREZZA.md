# Sicurezza e limiti noti

**Segreti.** Nessuna chiave API è nel codice: stanno solo nei file `.env`, esclusi da git, e ogni ambiente ha un `.env.example` senza valori. Nel front end le variabili `VITE_` sono pubbliche per costruzione e non contengono segreti. Online, la chiave OpenAI è un secret dello Space; le variabili dello Space sono pubbliche e contengono solo valori non segreti.

## Il limite principale: il data agent non ha una sandbox

Il data agent esegue codice Python generato dall'LLM (con `exec` ed `eval`) **senza isolamento**. Il percorso d'attacco è reale: il testo scritto in chat arriva, tramite l'orchestratore, al modello che genera quel codice, quindi una *prompt injection* ben costruita potrebbe tradursi in codice arbitrario eseguito sulla macchina del data agent. Il fatto che il servizio ascolti solo su `127.0.0.1` riduce la superficie d'attacco, ma non la elimina.

Per questo il sistema è pensato per un uso dimostrativo. La demo online lo espone a internet con le mitigazioni descritte nella sezione [La demo online](#la-demo-online), che riducono il rischio ma non lo eliminano. Le difese adottate sono a strati e nessuna, da sola, è una barriera di sicurezza:

- **Orchestratore:** una regola del prompt vieta di inoltrare codice, comandi o istruzioni agli strumenti (verificata con una richiesta di prompt injection, test 9 di [`docs/TEST.md`](TEST.md)). È un primo filtro, non una garanzia.
- **Input:** messaggi limitati a 2000 caratteri, corpo della richiesta a 10 kb, `sessionId` validato come UUID.
- **Rete:** il data agent e Chroma sono raggiungibili solo dal computer su cui girano: uvicorn ascolta su `127.0.0.1` e il container di Chroma pubblica la porta solo in locale (`-p 127.0.0.1:8001:8000`). La CORS del back end ammette solo l'origine del front end.
- **Tempo:** timeout di 90, 120 e 130 secondi sui tre tratti della richiesta.
- **Grafici:** i nomi dei file sono validati a tre livelli (data agent, back end e front end) contro il path traversal, e il salvataggio dei grafici è riservato allo strumento, non al codice del modello.
- **Informazioni:** nessun percorso di sistema viene dato al modello, nessun errore interno né valore di configurazione arriva al browser, e l'output dello strumento è limitato a 6000 caratteri.
- **Intestazioni HTTP:** `x-powered-by` disattivato (verificato da un test del back end) e `nosniff` sui grafici.
- **Front end:** il Markdown è reso senza HTML grezzo né immagini, e i link hanno `rel="noopener noreferrer"`.
- **Integrazione continua:** il workflow dei test (`.github/workflows/test.yml`) ha solo il permesso di lettura sul repository (`contents: read`) e non usa nessun secret: la chiave OpenAI non è tra i secret di GitHub, e il caricamento sullo Space resta manuale ([decisions/07](decisions/07-test-e-valutazione.md)).

## La demo online

- **Un solo punto esposto.** Da internet si raggiunge solo nginx. Inoltra al back end solo `/api/` e `/charts/`; le rotte interne del data agent (`/analyze`, `/docs`, `/openapi.json`), `/.env`, i file del codice e `GET /api/chat` rispondono 404. Data agent e Chroma ascoltano solo su `127.0.0.1` dentro il container.
- **Limite di frequenza** su `POST /api/chat`: 20 richieste per IP e 100 in totale ogni 15 minuti. Oltre, la risposta è 429 `RATE_LIMITED` con `Retry-After`. Il limite per IP vede l'IP vero grazie a `TRUST_PROXY=2`, e un `X-Forwarded-For` scritto a mano dal client viene ignorato (la prova è in [`docs/TEST.md`](TEST.md#prove-online-26-ottobre-2026)). Il limite globale protegge la spesa anche se l'IP non fosse affidabile.
- **Rischio dichiarato: il codice generato dall'LLM gira nello stesso processo che conosce la chiave OpenAI.** Il data agent esegue codice scritto dal modello e riceve la chiave nelle proprie variabili d'ambiente, perché gli serve per chiamare il modello: una prompt injection riuscita potrebbe leggerla. Il rischio è contenuto, non eliminato, con quattro mitigazioni: una chiave dedicata alla demo con un tetto di spesa mensile, il limite di frequenza, la regola dell'orchestratore che vieta di inoltrare codice agli strumenti e la possibilità di revocare la chiave in qualsiasi momento. Il container gira con un utente non root e il codice non è modificabile da quell'utente.
- **Log.** Nei log dello Space non compaiono chiavi né traceback. Compaiono gli argomenti che l'orchestratore passa agli strumenti (le domande riformulate), quindi nella demo non vanno scritti dati personali. Per il limite di frequenza si registrano solo il tipo di limite e l'IP mascherato (`93.34.x.x`): il testo del messaggio non finisce mai nei log del limite.
- **Variabili e secret.** Le variabili dello Space sono pubbliche; la chiave è un secret. Lo Space contiene una copia dei soli file committati, senza `.env`.

## Altri limiti noti

- **Sessioni in memoria e senza tetto.** Ogni richiesta senza `sessionId` crea una sessione che vive 30 minuti. Si potrebbe aggiungere una soglia massima.
- **Comportamento probabilistico.** Gli LLM non sono deterministici: alcune domande sui dati hanno un'affidabilità inferiore alla media (elenco in [`docs/TEST.md`](TEST.md#limiti-noti-del-data-agent)).
- **Formato degli importi.** Nelle risposte gli importi sono scritti nella notazione anglosassone (18,680,000: virgola per le migliaia, punto per i decimali), mentre gli assi dei grafici usano il punto per le migliaia (17.500.000). Una regola sul formato nel prompt del data agent è stata provata e tolta perché peggiorava risposte che non c'entravano con gli importi.
- **Stagioni scritte in due punti.** Le tre stagioni del dataset sono scritte nel prompt dell'orchestratore, per risolvere riferimenti come "la stagione precedente", e in `data_agent/schema.py`: se il dataset cambia, vanno aggiornate in entrambi.
- **Dipendenze di sviluppo del front end.** `npm audit` può segnalare vulnerabilità in pacchetti usati solo in sviluppo e in fase di build: non fanno parte del codice che arriva al browser. Lo si verifica da `front end/` con `npm audit --omit=dev`, che non segnala nessuna vulnerabilità nelle dipendenze che arrivano al browser.
- **Un codice generato che non termina tiene il lock.** Le altre analisi ricevono "servizio occupato" dopo 30 secondi, e nessun timeout interrompe quel codice ([decisions/06](decisions/06-esecuzione-del-codice-generato.md)).
- **Limiti di plausibilità dello schema scelti a mano.** Sono larghi: fermano gli errori che la pulizia corregge, non un dato vero ma insolito ([decisions/05](decisions/05-pulizia-e-schema-dei-dati.md)).
- **Valutazione automatica fuori dall'integrazione continua.** Copre 13 domande e si lancia a mano, perché costa token ([`docs/TEST.md`](TEST.md#valutazione-automatica), [decisions/07](decisions/07-test-e-valutazione.md)).
- **Benchmark su una sola macchina**, più veloce della CPU dello Space ([decisions/09](decisions/09-pandas-e-non-duckdb.md)).

## Limiti risolti

- **Stato globale di matplotlib tra richieste concorrenti.** Con due analisi in parallelo, una poteva lasciare disattivato il salvataggio dei grafici per tutto il processo, e da quel momento i grafici sparivano fino al riavvio del data agent. Un lock attorno all'esecuzione del codice generato serializza le esecuzioni: un test di concorrenza falliva in 17 giri su 20 sul codice precedente e passa in 20 su 20 con il lock ([decisions/06](decisions/06-esecuzione-del-codice-generato.md)).

## In produzione servirebbero

Una sandbox isolata per l'esecuzione del codice (container senza rete né accesso al disco), autenticazione e uno store di sessioni persistente e con limiti. Il limite di frequenza della demo è una protezione di base, per IP e globale: non sostituisce l'autenticazione.
