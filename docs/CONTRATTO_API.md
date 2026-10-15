# Contratto API — ScoutEdge Analytics

**Versione:** 1.0 — 2026-10-01
**Stato:** approvato

> Riferimento unico per l'interfaccia tra front end e back end. Ogni modifica incrementa la versione e viene annotata nello storico in fondo. Se un'implementazione richiede di discostarsi dal contratto, si aggiorna prima il contratto e poi il codice.

## Convenzioni
- Base URL back end: `http://localhost:3001` (nel front end letto da `VITE_API_URL`).
- JSON UTF-8, nomi dei campi in **camelCase** in tutte le richieste e risposte pubbliche.
- CORS: origine consentita letta da `.env` (`FRONTEND_ORIGIN`, default `http://localhost:5173`).
- Il browser comunica **solo** con il back end (porta 3001): mai direttamente con FastAPI (8000) né con Chroma (8001).
- Nessuno streaming nella v1: una richiesta → una risposta completa.
- Il campo `chart_url` restituito da FastAPI è un dettaglio interno: `dataAgentService.js` lo converte in `chartUrl`.

---

## POST /api/chat

### Richiesta
```json
{
  "message": "Qual è lo SLA per una richiesta ad alta priorità?",
  "sessionId": "3f1c2a9e-7b4d-4e8a-9c1f-2d5e6a7b8c9d"
}
```

| Campo | Tipo | Obbligatorio | Regole |
|---|---|---|---|
| `message` | string | sì | viene applicato `trim()`; lunghezza 1–2000 caratteri |
| `sessionId` | string (UUID v4) | no | omesso alla prima richiesta o dopo "Nuova chat" |

### Risposta 200
```json
{
  "sessionId": "3f1c2a9e-7b4d-4e8a-9c1f-2d5e6a7b8c9d",
  "newSession": false,
  "reply": "Per le richieste ad alta priorità il tempo di prima risposta è di 2 ore lavorative...",
  "chartUrl": null,
  "toolsUsed": ["search_handbook"],
  "sources": [{ "section": "7. SLA e procedura di supporto" }]
}
```

| Campo | Tipo | Significato |
|---|---|---|
| `sessionId` | string | id da usare nella richiesta successiva |
| `newSession` | boolean | `true` se la sessione è stata creata in questa richiesta |
| `reply` | string | testo della risposta; può contenere Markdown |
| `chartUrl` | string \| null | path relativo al back end, es. `/charts/chart_ab12cd34.png`; `null` se nessun grafico |
| `toolsUsed` | string[] | strumenti invocati nel turno, senza duplicati, in ordine di primo utilizzo. Valori ammessi: `"search_handbook"`, `"analyze_data"`. `[]` se l'LLM ha risposto senza strumenti |
| `sources` | `{ section: string }[]` | sezioni dell'handbook recuperate dalla RAG, senza duplicati; `[]` se la RAG non è stata usata |

Esempio di risposta con analisi dati e grafico:
```json
{
  "sessionId": "3f1c2a9e-7b4d-4e8a-9c1f-2d5e6a7b8c9d",
  "newSession": false,
  "reply": "Il grafico mostra la distribuzione dello scout_rating per ruolo...",
  "chartUrl": "/charts/chart_ab12cd34.png",
  "toolsUsed": ["analyze_data"],
  "sources": []
}
```

### Gestione di `sessionId`
- **Assente** → il server crea una sessione (`crypto.randomUUID()`) e risponde con `newSession: true`.
- **Presente ed esistente** → la conversazione continua, `newSession: false`.
- **Presente ma sconosciuto o scaduto** (es. riavvio del back end: lo store è in memoria per scelta) → il server crea una **nuova** sessione e restituisce il nuovo id con `newSession: true`. Non è un errore.
- **Formato non valido** (non è un UUID) → 400 `INVALID_REQUEST`.
- Il front end sovrascrive **sempre** il proprio `sessionId` con quello ricevuto. Se riceve `newSession: true` a conversazione già avviata, mostra un avviso discreto ("La conversazione precedente è scaduta: ne è iniziata una nuova").
- "Nuova chat" nel front end = scartare il `sessionId` e svuotare la lista messaggi.
- Lato server:
  - si conservano al massimo gli ultimi **20 messaggi** (utente + assistente) per sessione;
  - la sessione scade dopo **30 minuti** di inattività;
  - nella history si salvano solo il messaggio dell'utente e la `reply` finale (non i risultati intermedi dei tool);
  - la coppia domanda/risposta viene salvata **solo in caso di successo** (risposta 200).
- La lista messaggi del front end serve alla visualizzazione; la history del server serve alla memoria dell'LLM. Sono due copie con ruoli distinti.

### Gestione di `chartUrl`
- Il data agent salva il PNG e FastAPI restituisce `chart_url` (es. `/charts/chart_ab12cd34.png`); il back end lo riespone **con lo stesso path** sulla propria rotta `GET /charts/:filename`.
- Il front end mostra l'immagine con `<img src={VITE_API_URL + chartUrl} alt="Grafico generato dall'analisi dei dati">`, sotto il testo della risposta.
- Al massimo **un grafico per risposta**: se nello stesso turno ne vengono generati più di uno, vale l'ultimo.
- `reply` non contiene mai link o path all'immagine.
- I PNG restano su disco: un `chartUrl` resta valido finché il file esiste.

---

## GET /charts/:filename
- `filename` deve rispettare l'espressione regolare `^chart_[0-9a-f]{8}\.png$`, altrimenti 400 `INVALID_REQUEST` (protezione da path traversal).
- Il back end recupera il file da FastAPI e lo restituisce con `Content-Type: image/png`.
- 404 `NOT_FOUND` se il file non esiste.

## GET /
Health check del back end: `{ "status": "ok" }`.

---

## Errori
Formato unico per ogni risposta non 2xx:
```json
{ "error": { "code": "INVALID_REQUEST", "message": "Il messaggio non può essere vuoto." } }
```
- `message` è in italiano e mostrabile direttamente all'utente.
- Mai stack trace, né testo grezzo di errori OpenAI/FastAPI/Chroma: i dettagli vanno solo nei log del back end.

| HTTP | `code` | Quando |
|---|---|---|
| 400 | `INVALID_REQUEST` | JSON non valido, `message` assente/vuoto/oltre 2000 caratteri, `sessionId` malformato, `filename` non valido |
| 404 | `NOT_FOUND` | rotta inesistente o grafico non trovato |
| 409 | `SESSION_BUSY` | è già in corso una richiesta sulla stessa sessione |
| 413 | `PAYLOAD_TOO_LARGE` | body oltre il limite di `express.json` (10 kb) |
| 502 | `LLM_ERROR` | errore della chiamata all'LLM orchestratore (rete, rate limit, chiave non valida) |
| 504 | `TIMEOUT` | elaborazione complessiva oltre 120 s |
| 500 | `INTERNAL_ERROR` | qualsiasi altro errore imprevisto |

### Guasti di un singolo strumento
Se Chroma o il data agent non sono raggiungibili, o FastAPI risponde con un errore, questo **non** è un errore HTTP verso il front end:
- l'errore viene restituito all'LLM come risultato del tool;
- la risposta è un 200 il cui `reply` dichiara che il componente non è al momento disponibile;
- `toolsUsed` include comunque lo strumento tentato;
- **comportamento garantito:** in questo caso l'agente non inventa dati numerici né contenuti del manuale.

---

## Timeout
| Tratta | Timeout |
|---|---|
| Back end → data agent (`POST /analyze`) | 90 s |
| Pipeline completa di `POST /api/chat` | 120 s → 504 `TIMEOUT` |
| Front end → back end | non interrompe prima di 130 s |

Durante tutta l'attesa il front end mostra l'indicatore di digitazione/caricamento.

## Obblighi del front end
- Un solo invio alla volta: input e pulsante disabilitati finché la risposta non arriva.
- `reply` reso come testo/Markdown **senza HTML grezzo** (niente `dangerouslySetInnerHTML`).
- Gli errori vengono mostrati in chat come messaggio di sistema usando `error.message`; il messaggio dell'utente resta visibile.
- `toolsUsed` e `sources` vengono mostrati come etichette discrete sotto la risposta (es. "📄 Handbook — 7. SLA e procedura di supporto", "📊 Analisi dati").

## Obblighi del back end
- Validazione dell'input prima di qualsiasi chiamata all'LLM.
- Nessun dato sensibile o errore interno nelle risposte.
- Rispetto dei limiti di sessione e dei timeout indicati sopra.

---

## Esempi
```bash
# Prima domanda (nessun sessionId → nuova sessione)
curl -s -X POST http://localhost:3001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Come funziona lo scout_rating?"}'

# Domanda successiva nella stessa sessione, con grafico
curl -s -X POST http://localhost:3001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Mostrami la distribuzione dello scout_rating per ruolo","sessionId":"<id ricevuto>"}'

# Errore di validazione
curl -s -X POST http://localhost:3001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"   "}'
# → 400 { "error": { "code": "INVALID_REQUEST", "message": "Il messaggio non può essere vuoto." } }
```

---

## Storico versioni
- **1.0 — 2026-10-01**: prima versione approvata (decisioni: camelCase, `toolsUsed` e `sources` nella risposta, sessione sconosciuta → nuova sessione, `SESSION_BUSY`, limiti 2000 caratteri / 20 messaggi / 30 min / 90-120-130 s).