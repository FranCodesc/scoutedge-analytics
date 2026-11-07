# Risoluzione dei problemi

Sintomi frequenti in locale e nel container, con la causa probabile e cosa fare. Installazione e avvio sono descritti in [`docs/INSTALLAZIONE.md`](INSTALLAZIONE.md), il container in [`docs/DEPLOY.md`](DEPLOY.md).

| Sintomo | Causa probabile | Cosa fare |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker non è avviato | Apri Docker Desktop e riprova |
| `npm run ingest` non riesce a collegarsi a Chroma | Il container non è attivo, oppure è appena partito | `docker ps` per controllare; aspetta qualche secondo; se manca, `docker start chroma-scoutedge` |
| L'assistente dice che il manuale non è consultabile | Chroma spento, oppure manuale non ancora indicizzato | Avvia Chroma ed esegui `npm run ingest` da `back end/` |
| L'assistente dice che il servizio di analisi dati non è disponibile | Data agent spento o su un'altra porta | Avvialo come descritto in [Avvio](INSTALLAZIONE.md#avvio) e controlla `DATA_AGENT_URL` nel `.env` del back end |
| Errore "address already in use" all'avvio | La porta (3001, 5173, 8000 o 8001) è occupata | `lsof -i :3001` (cambia il numero) per vedere il processo, poi fermalo |
| Dopo `pip install` mancano pacchetti o `python` è quello sbagliato | È attivo conda, o il venv non è attivato | `conda deactivate`, poi ricrea e attiva il `venv` (vedi [Installazione](INSTALLAZIONE.md#installazione)) |
| Errore `LLM_ERROR` (502) in chat | Chiave OpenAI mancante, non valida o senza credito | Controlla `OPENAI_API_KEY` in `back end/.env` e in `data_agent/.env`, poi riavvia il servizio: le modifiche ai `.env` si leggono solo all'avvio |
| L'assistente dice che il manuale o l'analisi dati non sono disponibili, e nel log del back end compare l'errore sull'URL (`CHROMA_URL deve iniziare con http:// o https:// e contenere un host`, oppure `DATA_AGENT_URL mancante o non valida`) | Un indirizzo nel `.env` del back end è senza `http://`. Il back end parte lo stesso: l'errore compare alla prima domanda che usa quel servizio | Scrivi l'URL completo, per esempio `http://localhost:8001`, e riavvia il back end: il `.env` si legge solo all'avvio |
| Nel browser compare un errore di rete o di CORS | Il front end non gira sulla porta 5173, oppure il back end non su 3001 | In `back end/.env` imposta `FRONTEND_ORIGIN` all'indirizzo reale del front end; in `front end/.env` imposta `VITE_API_URL`; riavvia i due servizi |
| Risposta "richiesta già in corso" (409) | La domanda precedente della stessa conversazione non ha ancora finito | Aspetta la risposta, oppure avvia una "Nuova chat" |
| L'interfaccia usa un carattere diverso da Barlow Condensed | Senza rete, Google Fonts non si carica | Non è un errore: si usa il carattere di sistema |
| Errore 429 `RATE_LIMITED` ("Troppe richieste in poco tempo") | Limite di frequenza superato: sempre attivo online, in locale solo se le variabili `RATE_LIMIT_*` sono impostate | Aspetta qualche minuto (l'intestazione `Retry-After` dice quanti secondi); in locale, togli le variabili per disattivarlo |
| `docker build` si ferma con `Manca --build-arg VITE_API_URL` | La build non riceve l'URL del back end | Aggiungi `--build-arg VITE_API_URL=http://localhost:7860` (vedi [Avvio in locale con Docker](DEPLOY.md#avvio-in-locale-con-docker)) |
| Il container si ferma subito con `ERRORE: variabile … non impostata` | Nel file di variabili ne manca una delle sei richieste | Completa il file (`OPENAI_API_KEY`, `FRONTEND_ORIGIN`, le tre `RATE_LIMIT_*`, `TRUST_PROXY`) e rilancia `docker run` |
| Il container in locale dà errori di rete o di CORS nel browser | Il browser usa un indirizzo diverso da quello della build (per esempio `127.0.0.1` invece di `localhost`) | Apri lo stesso indirizzo usato in `VITE_API_URL` e `FRONTEND_ORIGIN` |
