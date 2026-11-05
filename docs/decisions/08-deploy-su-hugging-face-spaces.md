# Deploy su Hugging Face Spaces

**Data:** dal 2026-10-25 al 2026-10-27 (commit `71e5455`, `82bd5f1`, `4da75dc`, `228765a`, `e7c3d73`)

## Contesto

La demo deve essere raggiungibile online, con gli stessi quattro servizi che in locale girano separati (front end, back end, data agent, Chroma), senza esporre i servizi interni e senza che chiunque possa consumare la chiave OpenAI.

## Decisione

- **Un solo container Docker su uno Space di Hugging Face**, con **nginx come unico punto esposto** (porta 7860): serve il front end già compilato e inoltra al back end solo `/api/` e `/charts/`. Data agent e Chroma ascoltano su `127.0.0.1`, la porta del back end non è pubblicata. Uno Space Docker esegue un solo container con una sola porta pubblica, e così il browser continua a parlare solo con il back end, come in locale.
- **Avvio controllato** (`deploy/start.sh`): Chroma, indicizzazione del manuale, data agent, back end e nginx, nell'ordine in cui dipendono l'uno dall'altro; se un servizio si ferma il container esce con un codice diverso da 0 e la piattaforma lo riavvia. Utente non root, nessun segreto nell'immagine.
- **Piattaforma scelta dopo una simulazione.** Il 2026-10-25 gli Space Docker richiedevano il piano PRO (9 $/mese), mentre i piani gratuiti di Render, Koyeb e Railway offrivano 256-512 MB di memoria e poca CPU. Il container usa tra 212 e 256 MB; il piano gratuito di Render, simulato in locale con `--cpus=0.1 --memory=512m`, avviava il container in 2 minuti e 29 secondi, di cui 79 s solo per caricare le librerie Python del data agent. Sullo Space lo stesso container è pronto in circa 20 s.
- **`TRUST_PROXY=2` ricavato con prove.** Online la catena è proxy di Hugging Face, nginx, back end. Con 1 il limite di frequenza vedeva indirizzi interni di Hugging Face (`10.20.x.x`), diversi a ogni richiesta; con 2 vede l'IP pubblico del client, e un `X-Forwarded-For` scritto a mano dal client viene ignorato. Senza la variabile il back end non si fida dell'intestazione.
- **Limite di frequenza** sulle domande inviate al back end: 20 richieste per IP e 100 in totale ogni 15 minuti, contate prima della validazione del corpo. 20 bastano a chi prova la demo con calma (le domande d'esempio sono 5 turni) e sono troppo poche per un uso automatico; 100 in totale limitano la velocità con cui si può consumare la chiave anche con molti utenti o IP diversi. La protezione finale sul budget resta il tetto di spesa mensile della chiave dedicata. Online il limite è obbligatorio: con le variabili presenti solo in parte o non valide il back end non parte, e `start.sh` le pretende.

## Alternative scartate

- **Un piano gratuito**: con quelle risorse l'avvio dopo una pausa durava minuti.
- **Un servizio per componente**: lo Space esegue un container solo, ed esporre i servizi interni avrebbe allargato la superficie d'attacco.
- **Un valore di `TRUST_PROXY` assunto senza provarlo**: con 1 il limite per IP non funzionava; fidarsi di tutta la catena renderebbe falsificabile l'IP.
- **Il solo limite per IP**: l'IP può non essere affidabile, mentre il limite globale protegge la spesa comunque.

## Conseguenze

- Costo del piano PRO; lo Space va in pausa dopo 48 ore senza visite e riparte in circa 30 s, e a ogni riavvio si perdono sessioni e grafici.
- I servizi non scalano separatamente e il guasto di uno riavvia tutto: accettabile per una demo con poche richieste.
- Il deploy è manuale ([pagina 7](07-test-e-valutazione.md)); su un'altra piattaforma `TRUST_PROXY` va ricavato di nuovo con la stessa prova.
- I valori del limite sono scelti a mano e configurabili con le variabili d'ambiente.

## Numeri

- Avvio con risorse ridotte e memoria: [docs/TEST.md](../TEST.md#simulazione-con-risorse-ridotte); prove del container: [docs/TEST.md](../TEST.md#prove-del-container-in-locale).
- Prove online del 2026-10-26 (demo 4 su 4, limite di frequenza, `TRUST_PROXY`, rotte interne): [docs/TEST.md](../TEST.md#prove-online-26-ottobre-2026).

## Dove nel codice

- `Dockerfile`, `.dockerignore`, `deploy/nginx.conf`, `deploy/start.sh`, `deploy/upload_space.sh`.
- `back end/src/http/rateLimit.js`, `back end/src/app.js` (`trust proxy` e ordine dei middleware), `back end/src/index.js`.