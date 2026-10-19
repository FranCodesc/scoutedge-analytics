# ScoutEdge Analytics — front end

Interfaccia web di chat dell'assistente di ScoutEdge Analytics (progetto finale del master "AI e Agenti AI per il Business"). La chat è l'unico punto di interazione: l'utente scrive in italiano e l'agente risponde con le informazioni del manuale interno della piattaforma (RAG) oppure con un'analisi del dataset di scouting, anche con un grafico. Il front end non decide nulla: mostra ciò che restituisce il back end e ne rispetta il contratto API.

## Cosa fa

- Chat con memoria della conversazione (il `sessionId` è tenuto dal back end; qui vive solo in memoria).
- Risposte formattate in Markdown (tabelle, elenchi, grassetto), **senza HTML grezzo**.
- Grafici generati dal data agent: nel fumetto della risposta e, su desktop (da 1024 px), nel pannello laterale con l'ultimo grafico, con "Ingrandisci" e "Scarica".
- Etichette sotto ogni risposta che mostrano da dove arriva: `📄 Handbook — <sezione>` per ogni sezione citata del manuale, `📄 Handbook (nessuna sezione citata)` se il manuale è stato consultato ma nessuna sezione è citata, oppure `📊 Analisi dati`.
- Indicatore di attesa, input bloccato durante l'elaborazione (una sola richiesta alla volta), avviso se si è offline.
- Errori mostrati in chat con il messaggio del server; il messaggio dell'utente resta e, quando ha senso, c'è "Riprova".
- "Nuova chat": azzera la conversazione e scarta le risposte ancora in arrivo.
- Domande di esempio nella schermata iniziale.

## Requisiti

- Node.js 20.19 o successivo (oppure 22.12 o successivo), richiesto da Vite 8.
- Il back end di ScoutEdge in esecuzione (di default su `http://localhost:3001`). Per avviare tutti i servizi nell'ordine giusto vedi il README nella radice del repository.

## Installazione e avvio

Da questa cartella (`front end/`):

```bash
npm install
cp .env.example .env
npm run dev
```

L'app è su `http://localhost:5173`.

## Configurazione

Un'unica variabile, in `.env` (da copiare da `.env.example`):

| Variabile      | Significato           | Default                 |
| -------------- | --------------------- | ----------------------- |
| `VITE_API_URL` | URL base del back end | `http://localhost:3001` |

Vite espone al browser **tutte** le variabili che iniziano con `VITE_`: in questo file non vanno mai chiavi API o altri segreti. Il front end parla solo con il back end, mai direttamente con il data agent o con Chroma. Se `VITE_API_URL` manca, l'app avvisa in console e usa il default.

Il back end deve accettare l'origine del front end (variabile `FRONTEND_ORIGIN` del back end): serve anche al pulsante "Scarica".

## Script

| Comando           | Cosa fa                                                 |
| ----------------- | ------------------------------------------------------- |
| `npm run dev`     | server di sviluppo con ricarica automatica (porta 5173) |
| `npm run build`   | build di produzione in `dist/`                          |
| `npm run preview` | serve la build di produzione in locale                  |
| `npm run lint`    | controllo ESLint                                        |

## Struttura

```text
src/
├── main.jsx                 punto d'ingresso
├── App.jsx                  preloader (3 s) + chat
├── index.css                Tailwind e tema ScoutEdge (@theme)
├── api/chatApi.js           unico modulo che parla con il back end
├── hooks/
│   ├── useChat.js           stato della conversazione, invio, riprova, "Nuova chat"
│   ├── useChartDownload.js  download del grafico
│   └── useOnlineStatus.js   stato online/offline del browser
└── components/
    ├── Chat.jsx             layout, scroll della lista, composizione dei pezzi
    ├── MessageBubble.jsx, MessageContent.jsx, ToolBadges.jsx, ChartImage.jsx
    ├── ChartsPanel.jsx, ChartDialog.jsx
    ├── ChatInput.jsx, Welcome.jsx, Thinking.jsx, ErrorCard.jsx
    └── Preloader.jsx, PitchBackground.jsx, Ball.jsx, Avatar.jsx
```

## Scelte principali

- **React 19 + Vite 8, JavaScript**, nessuna libreria di componenti.
- **Tailwind CSS v4** con il plugin ufficiale per Vite: il tema (colori, font, animazioni) è dichiarato con `@theme` in `src/index.css`, senza `tailwind.config.js`. Il Markdown è formattato con `@tailwindcss/typography`.
- **Markdown senza HTML grezzo**: `react-markdown` con `remark-gfm`, senza `rehype-raw` e senza `dangerouslySetInnerHTML`. Le immagini nel testo sono disabilitate, i link si aprono in una nuova scheda con `rel="noopener noreferrer"` e gli schemi pericolosi (come `javascript:`) vengono scartati.
- **`sessionId` solo in memoria**: niente `localStorage`. Ricaricare la pagina avvia una nuova conversazione.
- **Un solo client API** (`src/api/chatApi.js`) con errori normalizzati in `ApiError { status, code, message }`: i codici del contratto più `NETWORK_ERROR` e `CLIENT_TIMEOUT` (130 s, oltre i 120 s del back end), sempre con messaggio in italiano.
- **Grafici validati**: l'indirizzo di un'immagine non viene mai preso dal server così com'è. `chartSrc()` accetta solo il formato `/charts/chart_<8 cifre esadecimali>.png` e `downloadChart()` lo ricontrolla prima di scaricare.
- **Risposte tardive scartate**: dopo "Nuova chat" una risposta rimasta in volo non compare e non sblocca l'input della conversazione nuova.
- **Font**: Barlow Condensed da Google Fonts. Senza rete (o con Google Fonts bloccato) si usa il font di sistema e l'interfaccia resta utilizzabile.
- **Accessibilità**: la lista dei messaggi è un `role="log"` con `aria-live`, "riduci movimento" è rispettato (animazioni e scroll), il pannello dei grafici usa un `<dialog>` nativo per l'ingrandimento.
- Il pannello laterale dei grafici è visibile da 1024 px; su schermi più piccoli il grafico compare solo nella risposta.

## Contratto con il back end

Il formato delle richieste e delle risposte, i codici di errore, i limiti (2000 caratteri per messaggio, 20 messaggi per sessione, timeout) e gli obblighi del front end sono descritti nel contratto API: [`../docs/CONTRATTO_API.md`](../docs/CONTRATTO_API.md).

## Limiti noti

- Le variabili `VITE_` sono pubbliche per costruzione (vedi sopra).
- `npm audit` segnala una vulnerabilità moderata in una dipendenza di **sviluppo** (`postcss-selector-parser`, tramite `@tailwindcss/typography`): non arriva nel codice servito al browser (`npm audit --omit=dev` non segnala nulla). La correzione automatica richiederebbe `--force` e un downgrade del plugin, quindi non è applicata.
