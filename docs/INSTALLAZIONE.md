# Installazione e avvio in locale

Come installare i tre ambienti (back end, front end, data agent), configurare i file `.env`, avviare Chroma e indicizzare il manuale, e avviare i servizi nell'ordine giusto. Il riepilogo dei comandi è nell'[Avvio rapido](../README.md#avvio-rapido) del README.

## Prerequisiti

- **Node.js** 20.19 o successivo (oppure 22.12 o successivo), con npm. Lo richiede Vite 8. Per i test del front end serve 22.13 o successivo; l'integrazione continua e il container usano Node 24.
- **Python 3.13**, con il modulo `venv`. Su macOS il comando `python3` di sistema è una versione più vecchia (la 3.9), troppo vecchia per questo progetto: pandas 3 richiede almeno la 3.11. Python 3.13 si installa dal sito python.org (installer per macOS) oppure con Homebrew (`brew install python@3.13`): entrambi forniscono il comando `python3.13`.
- **Docker**, per eseguire ChromaDB. È l'unico modo supportato per avviarlo.
- **Una chiave API OpenAI** con accesso a `gpt-4o-mini` e a `text-embedding-3-small`.
- **Porte libere**: 5173, 3001, 8000 e 8001.
- **Git**, per clonare il repository.

I comandi di questa pagina sono scritti per macOS e Linux, e sono stati provati su macOS. Per Windows c'è la sezione [Su Windows (PowerShell)](#su-windows-powershell), con i comandi equivalenti: non è stata provata su Windows.

**Sui costi.** Ogni domanda genera alcune chiamate a `gpt-4o-mini` (una per l'orchestratore, di più se interviene il data agent), e l'indicizzazione del manuale usa gli embedding. Con questi modelli il costo è contenuto, ma non nullo, e gli script che usano il modello reale (`npm run test:api`, `npm run eval`) fanno decine di richieste. Conviene usare una chiave con un limite di spesa.

## Installazione

I tre ambienti (back end, front end, data agent) si installano separatamente. Tutti i comandi partono dalla radice del repository.

```bash
git clone https://github.com/FranCodesc/scoutedge-analytics.git
cd scoutedge-analytics
```

**Back end** (le cartelle `back end/` e `front end/` hanno uno spazio nel nome: servono le virgolette):

```bash
cd "back end"
npm install
cp .env.example .env
cd ..
```

**Front end:**

```bash
cd "front end"
npm install
cp .env.example .env
cd ..
```

**Data agent** (Python 3.13, in un ambiente virtuale). L'installazione delle dipendenze può richiedere qualche minuto:

```bash
cd data_agent
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
deactivate
cd ..
```

Prima di creare il `venv`, controlla la versione: `python3.13 --version` deve rispondere 3.13.x. Se il comando `python3.13` non esiste, Python 3.13 non è installato (vedi i [Prerequisiti](#prerequisiti)): `python3` da solo, su macOS, è la versione di sistema e non va bene. Se Python 3.13 arriva da Anaconda o Miniconda, puoi usare il percorso completo dell'interprete, per esempio `/opt/anaconda3/bin/python3.13 -m venv venv`. Dopo `source venv/bin/activate`, anche `python --version` deve rispondere 3.13.x.

Se usi conda, esegui `conda deactivate` prima di creare e attivare il `venv`: con due ambienti attivi insieme `python` e `pip` possono puntare a quello sbagliato.

## Configurazione dei file `.env`

Ogni ambiente ha un file `.env.example` da copiare in `.env` (i comandi sopra lo fanno già). I valori di esempio vanno bene per l'avvio in locale: **serve solo inserire la chiave OpenAI**. I file `.env` contengono segreti, sono esclusi da git e non vanno mai committati.

| File | Variabile | Valore di esempio | Note |
|---|---|---|---|
| `back end/.env` | `OPENAI_API_KEY` | *(la tua chiave)* | Obbligatoria: embedding della RAG e LLM dell'orchestratore |
| | `PORT` | `3001` | Porta del back end |
| | `DATA_AGENT_URL` | `http://127.0.0.1:8000` | Il protocollo (`http://`) è obbligatorio |
| | `CHROMA_URL` | `http://localhost:8001` | Il protocollo è obbligatorio |
| | `FRONTEND_ORIGIN` | `http://localhost:5173` | Origine ammessa dalla CORS |
| | `RATE_LIMIT_WINDOW_MIN` | *(assente)* | Facoltativa. Finestra del limite di frequenza su `POST /api/chat`, in minuti (massimo 1440). Demo online: `15` |
| | `RATE_LIMIT_PER_IP` | *(assente)* | Facoltativa. Richieste per IP nella finestra. Demo online: `20` |
| | `RATE_LIMIT_GLOBAL` | *(assente)* | Facoltativa. Richieste totali nella finestra, da tutti i client. Demo online: `100` |
| | `TRUST_PROXY` | *(assente)* | Facoltativa. Numero di proxy davanti al back end (intero ≥ 0). Demo online: `2`. Vedi [`TRUST_PROXY`](DEPLOY.md#trust_proxy-come-è-stato-ricavato) |
| `data_agent/.env` | `OPENAI_API_KEY` | *(la tua chiave)* | Obbligatoria: modello che scrive il codice di analisi |
| `front end/.env` | `VITE_API_URL` | `http://localhost:3001` | URL del back end. Le variabili `VITE_` finiscono nel browser: qui non vanno mai chiavi |

La stessa chiave può stare nei due file che la richiedono.

Le tre variabili `RATE_LIMIT_*` vanno impostate **tutte o nessuna**: se ne manca una, o il valore non è un intero positivo, il back end non parte. Senza di esse il limite di frequenza è disattivato, ed è il comportamento in locale. Nel container della demo online, invece, tutte e quattro le variabili sono obbligatorie: lo script di avvio si rifiuta di partire se ne manca una.

## Chroma e indicizzazione del manuale

ChromaDB si esegue con **Docker**, che è l'unico modo supportato e provato. Con Docker avviato, da `back end/`:

```bash
cd "back end"
docker run -d --name chroma-scoutedge -p 127.0.0.1:8001:8000 -v "$(pwd)/chroma_data:/data" chromadb/chroma@sha256:1e0b73a187a28757c572acba508c46f48c9e8b0acaf5c20e6d95cdedce1acdf6
npm run ingest
cd ..
```

L'immagine è fissata con il digest (Chroma 1.4.4, la versione su cui il progetto è stato provato) perché il tag `latest` cambia nel tempo e una versione diversa potrebbe non essere compatibile con il client `chromadb` del back end.

- Il container espone Chroma sulla porta 8001 e salva i dati in `back end/chroma_data/`, una cartella esclusa da git. Chroma 1.x scrive in `/data` dentro il container, per questo il mount punta lì.
- La porta è pubblicata come `127.0.0.1:8001`, non come semplice `8001`: senza l'indirizzo davanti Docker la apre su tutte le interfacce, e Chroma, che qui non ha autenticazione, sarebbe raggiungibile da chiunque sia sulla stessa rete. Il back end gira sullo stesso computer e usa `localhost`, quindi non cambia nulla per l'avvio.
- `npm run ingest` legge `data/platform_handbook.md`, ne calcola gli embedding con OpenAI e li scrive nella collection `platform-handbook`. Alla fine stampa `Chunk nella collection "platform-handbook": 18`.
- L'ingestione si può rilanciare in sicurezza: aggiorna i passaggi esistenti e rimuove quelli che non esistono più nel manuale.
- Se il container esiste già (errore "name already in use"), non ricrearlo: `docker start chroma-scoutedge`. Dopo un riavvio del computer si fa lo stesso: i dati indicizzati restano.

## Avvio

Servono quattro terminali (Chroma gira già in background con Docker). L'ordine conta: ogni servizio ne usa uno di quelli sopra. Tutti i comandi partono dalla radice del repository.

**1. Chroma.** Se hai appena eseguito `docker run`, è già attivo. Dopo un riavvio del computer:

```bash
docker start chroma-scoutedge
```

**2. Data agent** (primo terminale). Aspetta il messaggio `Data agent pronto`:

```bash
cd data_agent
source venv/bin/activate
uvicorn main:app --reload
```

Uvicorn ascolta solo su `127.0.0.1` (il comportamento predefinito): non aggiungere `--host 0.0.0.0`. Il data agent esegue codice generato dall'LLM e non deve essere raggiungibile dalla rete (vedi [`docs/SICUREZZA.md`](SICUREZZA.md)).

**3. Back end** (secondo terminale). Aspetta `Back end in ascolto su http://localhost:3001`:

```bash
cd "back end"
npm run dev
```

**4. Front end** (terzo terminale):

```bash
cd "front end"
npm run dev
```

Apri <http://localhost:5173>. All'avvio compare una breve schermata introduttiva di circa 3 secondi, poi la chat con le domande di esempio.

Per verificare che i servizi rispondano, da un altro terminale:

```bash
curl http://127.0.0.1:8000/     # data agent → {"status":"ok"}
curl http://localhost:3001/     # back end   → {"status":"ok"}
```

Le analisi sui dati possono richiedere fino a un minuto (il modello scrive ed esegue codice): l'interfaccia lo segnala dopo 10 secondi di attesa.

Per fermare tutto: `Ctrl+C` in ciascun terminale e `docker stop chroma-scoutedge`.

## Su Windows (PowerShell)

I comandi di questa pagina sono stati provati solo su macOS. Quelli qui sotto sono gli equivalenti per Windows 10 e 11 con PowerShell, ma **non sono stati provati su Windows**: se qualcosa non torna, fa fede il messaggio di errore.

Servono gli stessi prerequisiti (Node.js, Python 3.13, Git, chiave OpenAI) e **Docker Desktop con il backend WSL 2**, che è l'impostazione predefinita dell'installer. Il comando `py` (installato con Python da python.org) sceglie la versione con `py -3.13`.

| Passo | macOS / Linux | Windows (PowerShell) |
|---|---|---|
| Creare il `venv` | `python3.13 -m venv venv` | `py -3.13 -m venv venv` |
| Attivare il `venv` | `source venv/bin/activate` | `.\venv\Scripts\Activate.ps1` |
| Copiare i file `.env` | `cp .env.example .env` | `Copy-Item .env.example .env` |
| Cartella corrente nel volume di Docker | `-v "$(pwd)/chroma_data:/data"` | `-v "${PWD}/chroma_data:/data"` |
| Controllare i servizi | `curl http://localhost:3001/` | `curl.exe http://localhost:3001/` |
| Variabile d'ambiente per un comando | `RIPETI=3 python scripts/regression_check.py "giocatore 33"` | `$env:RIPETI=3; python scripts/regression_check.py "giocatore 33"` |
| Processo che occupa una porta | `lsof -i :3001` | `netstat -ano \| findstr :3001` |

Il comando di Chroma, da `back end/`:

```powershell
docker run -d --name chroma-scoutedge -p 127.0.0.1:8001:8000 -v "${PWD}/chroma_data:/data" chromadb/chroma@sha256:1e0b73a187a28757c572acba508c46f48c9e8b0acaf5c20e6d95cdedce1acdf6
```

Note:

- Se PowerShell rifiuta `Activate.ps1` perché l'esecuzione di script è disabilitata, esegui una volta `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e riprova.
- In PowerShell `curl` è un alias di `Invoke-WebRequest`: per i comandi di questa pagina serve `curl.exe`.
- `${PWD}` va scritto con le graffe, altrimenti PowerShell legge male il percorso davanti ai due punti.
- `$env:RIPETI` resta impostata finché la finestra è aperta; per toglierla: `Remove-Item Env:RIPETI`.
- Tutto il resto (`npm`, `uvicorn`, `docker start`, `docker stop`, `npm run ingest`) è identico. Lo stesso vale per i comandi di [`docs/TEST.md`](TEST.md), con le stesse traduzioni.

In alternativa si può usare **WSL 2** con una distribuzione Linux (per esempio Ubuntu): i comandi Linux di questa pagina valgono così come sono. Il repository va clonato dentro il file system di WSL (non sotto `/mnt/c`, che è lento), Node.js e Python 3.13 vanno installati dentro la distribuzione, e in Docker Desktop va attivata l'integrazione con WSL.
