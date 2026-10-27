# Test di ScoutEdge Analytics

Come verificare che il sistema funzioni e quali risultati aspettarsi. Il contratto delle API è in [CONTRATTO_API.md](CONTRATTO_API.md), le domande di verifica dell'orchestratore in [DESIGN_ORCHESTRATORE.md](DESIGN_ORCHESTRATORE.md) (sezione 6).

I test distinguono due tipi di verifica:

- **Automatica**: forma delle risposte, codici di errore, sessioni, catena dei grafici. L'esito è OK o KO.
- **A mano**: il contenuto delle risposte dell'LLM. Il modello è probabilistico, quindi i numeri e le scelte degli strumenti si confrontano con la tabella [Valori attesi](#valori-attesi).

## Prerequisiti

Tutti i servizi avviati, nell'ordine indicato nel README: Chroma (con il manuale già indicizzato), data agent (porta 8000) e back end (porta 3001). Le richieste dei test chiamano OpenAI, quindi hanno un costo e richiedono la chiave configurata nei file `.env`.

## Test automatici dell'API

Da `back end/`:

```bash
npm run test:api                    # parte A + parte B
npm run test:api -- --solo-a        # solo la parte A (contratto)
REPLY_CHARS=1500 npm run test:api   # estratti più lunghi nella parte B
BASE_URL=http://localhost:3001 npm run test:api   # per cambiare indirizzo
```

### Parte A: contratto (23 controlli)

Ogni controllo stampa `OK` o `KO`. Se almeno uno è `KO`, lo script termina con codice di uscita 1. Gli errori sono verificati anche nella forma: il corpo deve contenere solo `{ error: { code, message } }`.

| Gruppo | Cosa verifica |
|---|---|
| a | `GET /` risponde `200 { status: "ok" }` |
| b | `POST /api/chat` con body non valido risponde 400 `INVALID_REQUEST`: `message` vuoto, di soli spazi, assente o di 2001 caratteri; `sessionId` non UUID o `null`; body array; JSON malformato (8 casi) |
| c | Body oltre 10 kb → 413 `PAYLOAD_TOO_LARGE` |
| d | Rotta inesistente → 404 `NOT_FOUND` |
| e | `GET /charts/...` con nome non valido e con path traversal codificato → 400; grafico inesistente → 404 (richiede il data agent acceso) |
| f | Prima domanda senza `sessionId` → 200, `newSession: true`, tutti i campi del contratto con i tipi giusti |
| g | Stessa sessione → `newSession: false` e stesso id; UUID v4 valido ma sconosciuto → 200, `newSession: true` e id diverso (non è un errore) |
| h | Domanda con grafico → `chartUrl` nella forma `/charts/chart_<8 esadecimali>.png`, poi `GET` su quel path → 200 `image/png` |
| i | Due richieste parallele sulla stessa sessione → una 200 e una 409 `SESSION_BUSY` |

Esito atteso: **23 OK, 0 KO**.

### Parte B: domande del design (da valutare a mano)

Senza `--solo-a`, dopo la parte A lo script pone le domande della sezione 6 del design attraverso la route. Per ognuna stampa gli strumenti usati (`toolsUsed`), le sezioni del manuale (`sources`), il `chartUrl`, la durata e un estratto della risposta. Non c'è un esito automatico. Si confronta con i [Valori attesi](#valori-attesi).

- I test 5, 5b e 5c sono conversazioni vere sulla stessa sessione.
- Il 4b si ripete tre volte, perché la parte sui dati ha un [limite noto](#limiti-noti-del-data-agent).
- Per il test 9 si controlla anche, nel log del back end, che gli argomenti passati agli strumenti non contengano codice.

## Verifiche manuali

Non sono nello script perché richiedono di spegnere servizi o di modificare temporaneamente il codice.

**1. Path traversal sui grafici.** Con `--path-as-is` curl non normalizza il percorso:

```bash
curl -i --path-as-is "http://localhost:3001/charts/../../etc/passwd"
curl -i --path-as-is "http://localhost:3001/charts/%2e%2e/%2e%2e/etc/passwd"
```

Atteso: `404 NOT_FOUND` con il messaggio "Risorsa non trovata.": il percorso non corrisponde a nessuna rotta e non viene letto nessun file dal disco. La variante con `%2F` (già nella parte automatica) risponde invece 400.

**2. Timeout e sessione occupata.** In `back end/src/routes/chat.js` abbassa temporaneamente `CHAT_TIMEOUT_MS` (per esempio a `3_000`), riavvia il back end e pone una domanda che usa il data agent. Atteso:

1. la risposta è `504 TIMEOUT`;
2. una nuova richiesta sulla stessa sessione, subito dopo, risponde `409 SESSION_BUSY`, perché l'elaborazione del primo turno non è ancora finita;
3. a lavoro concluso, una nuova richiesta sulla stessa sessione risponde 200, e il turno scaduto non compare nella conversazione.

Ripristina poi il valore originale (`120_000`).

**3. Data agent spento** (test 7). Ferma il data agent e chiedi "Quanti giocatori ci sono nel dataset?". Atteso: risposta 200 con `toolsUsed: ["analyze_data"]`, una dichiarazione che il servizio non è disponibile e **nessun numero**.

**4. Chroma spento** (test 8). Ferma il container (`docker stop chroma-scoutedge`) e pone la domanda sullo SLA per priorità alta. Atteso: risposta 200 con `toolsUsed: ["search_handbook"]`, dichiarazione di indisponibilità e **nessun contenuto del manuale inventato**. Riavvia poi con `docker start chroma-scoutedge`.

**5. Grafico con data agent spento.** Con un `chartUrl` ottenuto in precedenza, ferma il data agent e richiedi `GET /charts/<nome>.png`. Atteso: `500 INTERNAL_ERROR` con il messaggio "Il grafico non è al momento disponibile."

## Valori attesi

Valori calcolati sul dataset dopo la pulizia (1185 righe, 130 giocatori).

| Domanda | Atteso |
|---|---|
| Quanti giocatori ci sono nel dataset? | 130 |
| Quali correzioni avete applicato ai dati? | 1208 → 1185 righe; 23 duplicati (13 + 10); club da 74 a 25 grafie; nazionalità da 45 a 24; 5 casi di osservazioni nello stesso giorno (giocatori 10, 33, 60, 70, 74); titoli e qualifiche tolti dai nomi di 12 giocatori (113 righe) |
| Valore di mercato attuale più alto | 18.680.000 €, giocatore 5 (Sato Jun), Fiume Rosso AC (27/04/2026) |
| Valore di mercato massimo storico (richiesto esplicitamente) | 19.102.000 €, giocatore 5 (09/03/2025) |
| 10 giocatori con il valore di mercato attuale più alto | 5 Sato Jun 18.680.000 € · 43 Thiago Nahuel Lucas Ezequiel Mendez 13.560.000 · 76 Bulunç Müslum Kısakürek Aslan 13.423.000 · 38 Benjamin Dorn 12.890.000 · 63 Francisco Lobo 12.714.000 · 9 James Cox 11.746.000 · 93 Yoshida Tomoya 11.631.000 · 24 Demetrio Vazquez Amor 11.168.000 · 31 Bernard Labbé 10.792.000 · 128 Puk van der Wal-Ghoerle 10.747.000. L'undicesimo è il giocatore 89 (Zachary Rice, 10.691.000) |
| Scout_rating medio nell'ultima stagione | 65.11 su 405 osservazioni (2025/26). **65.21 è sbagliato**: è la media dello stato attuale (130 righe) |
| Andamento dello scout_rating medio per stagione | 2023/24 66.59 (380) · 2024/25 66.18 (400) · 2025/26 65.11 (405) |
| Conversazione: ultima stagione → "e nella stagione precedente?" | 65.11 su 405 → 2024/25, 66.18 su 400 |
| Conversazione: stagione 2024/25 → "e in quella precedente?" | 66.18 su 400 → 2023/24, 66.59 su 380 |
| Conversazione: ultima stagione → "e per i portieri?" | 65.11 su 405 → 68.91 su 46 osservazioni. **68.29 su 14 è sbagliato** |
| Valore di mercato medio sull'osservazione più recente di ogni giocatore | 6.887.985 € su 130 righe. Su tutte le 1185 righe sarebbe 7.156.158 €: valore sbagliato |
| Rating attuale del giocatore 70 | 66 (Davide Russo, 28/11/2025), con la segnalazione delle due osservazioni della stessa data (Marini 57, Russo 66). È l'unico giocatore con più osservazioni nella sua data più recente |
| Rating attuale dei giocatori 33 e 70 | 80 (giocatore 33, 30/03/2026, nessuna segnalazione) e 66 (giocatore 70) con la segnalazione delle due osservazioni del 28/11/2025 (Marini 57, Russo 66) |
| Rating attuale dei giocatori 33 / 10 / 60 | 80 (Valeria Costa, 30/03/2026) / 74 (Davide Russo, 20/03/2026) / 50 (Antonio Greco, 31/12/2025), senza segnalazioni |
| Scout_rating medio per ruolo nell'ultima stagione | GK 68.91 (46) · CB 62.34 (41) · terzini LB+RB 63.53 (86) · difensori CB+LB+RB 63.15 (127) · attaccanti LW+RW+ST 63.93 (76) · centrocampisti CDM+CM+CAM+LM+RM 66.16 (156) |
| 3 CB con il duels_won_pct attuale più alto | giocatore 120 (Pereira) 72.0 · 122 (Balaguer) 67.9 · 6 (Ito Yuta) 64.1 (12 CB in totale) |
| Valore medio per club (osservazione più recente) | 25 club, nessun doppione di grafia |
| Righe dei portieri (GK) | 131 |
| RAG: tempo di prima risposta per priorità alta | 2 ore lavorative (risoluzione target 8 ore), sezione 7.1 del manuale |
| RAG: tempo di prima risposta per priorità media | 8 ore lavorative, sezione 7.1 |
| RAG: escalation se lo SLA non è rispettato | Team Lead di Client Success, entro 4 ore lavorative, sezione 7.3 |
| RAG: Qual è la procedura di data cleaning del team? | 7 passaggi; il quinto è la rimozione di titoli e qualifiche dai nomi dei giocatori, sezione 6 del manuale |
| RAG: Come si calcola lo scout_rating? | Scala 1–99; valutazione qualitativa circa il 40%; fattore età (sopra i 30 anni e sotto i 21); soglie 80 e 40, sezione 3 del manuale |

## Distanze di retrieval

Distanze coseno dei primi 4 passaggi, misurate sul manuale indicizzato (18 chunk). Sono la base della soglia di rilevanza: un passaggio è tenuto se la distanza è ≤ 0.60 **e** ≤ distanza migliore + 0.12. Le righe «Privacy dei dati» e «Correzioni applicate ai dati», che contengono la sezione 6, sono state rimisurate sul manuale 1.7; le altre sono state misurate sul manuale 1.6 (le sezioni coinvolte non sono cambiate).

| Domanda | Risultati (id → distanza) |
|---|---|
| SLA per priorità alta | `sec-7` 0.364 · `sec-8-q3` 0.550 · `sec-2` 0.627 · `sec-8-q2` 0.692 |
| Come funziona lo scout_rating | `sec-3-1` 0.293 · `sec-8-q2` 0.336 · `sec-8-q1` 0.388 · `sec-3-4` 0.451 |
| Privacy dei dati | `sec-5` 0.491 · `sec-6` 0.584 · `sec-1` 0.663 · `sec-7` 0.665 |
| Correzioni applicate ai dati | `sec-6` 0.462 · `sec-8-q5` 0.501 · `sec-4` 0.584 · `sec-8-q1` 0.605 |
| Confronto di rating tra ruoli diversi | `sec-8-q2` 0.392 · `sec-3-3` 0.402 · `sec-3-1` 0.442 · `sec-4` 0.457 |
| Fuori ambito ("capitale della Francia") | tutti tra 0.893 e 0.938 |

## Limiti noti del data agent

Il data agent è un LLM che scrive ed esegue codice: alcune domande hanno quindi un'affidabilità inferiore alla media. Sono limiti dichiarati, non errori da inseguire nei test.

- **"I 3 CB con il duels_won_pct più alto nell'osservazione più recente"**: il risultato varia da un giro all'altro (da 1 su 5 a circa 7 su 10 nelle prove). L'errore è sempre lo stesso: compare solo Pereira. Con "attuale" al posto di "nell'osservazione più recente" i test hanno dato 10 su 10; la demo usa questa formulazione. Passando dall'orchestratore, l'espressione può essere riscritta in "nell'ultima stagione".
- Le risposte non dichiarano i codici di ruolo usati nei filtri (0 su 8), anche se i filtri sono corretti.
- Il CDM è conteggiato tra i centrocampisti. Il manuale (§3.3) lo valuta "come un difensore aggiunto", ma questo riguarda le metriche, non il gruppo di ruolo.
- "Esterni" e "laterali" non sono mappati su un ruolo (termine ambiguo): ci si aspetta un chiarimento o i codici dichiarati.
- **Formato degli importi nel testo**: gli importi nelle risposte sono scritti nella notazione anglosassone (18,680,000: virgola per le migliaia, punto per i decimali), mentre gli assi dei grafici usano il punto per le migliaia (17.500.000). Una regola sul formato nel prompt del data agent è stata provata e tolta perché peggiorava risposte che non c'entravano con gli importi.
- **Asse dei grafici scelti dal modello**: l'asse può non partire da zero (per esempio lo scout_rating per stagione parte da 60), il che amplifica visivamente le differenze.
- L'output dello strumento è limitato a 6000 caratteri e a 60 righe.
- Un solo grafico per esecuzione.
- Alcune date del CSV possono diventare valori mancanti in fase di lettura.

Un'ulteriore limitazione, comune a tutto il sistema, è che il numero di campioni di ogni prova è piccolo (2–8): differenze di poco conto tra un giro e l'altro sono rumore.

## Domande end-to-end da provare dall'interfaccia

Elenco di partenza per la prova manuale dalla chat (<http://localhost:5173>), con i riferimenti ai valori attesi sopra. Le domande da 1 a 3 sono quelle adatte a una dimostrazione.

1. *Qual è il tempo di prima risposta per una richiesta ad alta priorità?* → manuale, sezione 7; etichetta `📄 Handbook`; "2 ore lavorative".
2. *Quali sono i 10 giocatori con il valore di mercato attuale più alto? Mostrami anche un grafico.* → solo dati, etichetta `📊 Analisi dati`; elenco dei 10 giocatori con i valori nel testo, il primo è il giocatore 5 (Sato Jun, `18,680,000` nel testo); grafico con l'asse scritto con i separatori delle migliaia (`17.500.000`), senza `1e7`.
3. *Secondo la metodologia, quali metriche contano di più per i difensori centrali? Poi mostrami i 3 CB con il duels_won_pct attuale più alto.* → entrambi gli strumenti, prima il manuale poi i dati; Pereira 72.0, Balaguer 67.9, Ito Yuta 64.1.
4. Conversazione: *Qual è lo scout_rating medio nell'ultima stagione?* → *E nella stagione precedente?* → 65.11 su 405, poi 66.18 su 400.
5. *Quali correzioni avete applicato ai dati?* → numeri della riga corrispondente nei valori attesi.
6. *Qual è il rating attuale del giocatore 70?* → 66 con la segnalazione delle due osservazioni.
7. *Qual è la capitale della Francia?* → nessuno strumento, risposta che delimita l'ambito.
8. *Ciao!* → risposta breve, nessuno strumento.

## Script di test del data agent

In `data_agent/scripts/` ci sono due script per provare il data agent da solo, senza passare dal back end e dall'interfaccia. Si lanciano da `data_agent/`, con il `venv` attivo e la chiave OpenAI in `data_agent/.env`. Entrambi chiamano il modello e consumano quindi crediti OpenAI; nessuno dei due scrive file.

### `traccia_agente.py`

Costruisce lo stesso agente del servizio, gli pone una domanda e stampa passo per passo il codice che il modello manda a `python_repl`, l'output restituito dallo strumento e il testo del modello. Serve a capire cosa ha eseguito l'agente quando una risposta è sbagliata. Non richiede il data agent acceso.

```bash
cd data_agent
source venv/bin/activate
python scripts/traccia_agente.py "Qual è il rating attuale del giocatore con ID 70?"
```

### `regression_check.py`

Pone una serie di domande a `POST /analyze` e controlla nelle risposte i valori attesi (e quelli sbagliati che non devono comparire). Richiede il data agent acceso sulla porta 8000 (`uvicorn main:app` da `data_agent/`) e usa solo la libreria standard di Python. Per ogni prova stampa `OK` o `KO`.

```bash
python scripts/regression_check.py                           # tutti i casi
python scripts/regression_check.py giocatore                 # solo i casi il cui nome contiene "giocatore"
RIPETI=3 python scripts/regression_check.py "giocatore 33"   # ripete ogni caso 3 volte
```

- **Filtro**: le parole dopo il nome dello script restringono i casi a quelli il cui nome le contiene (senza distinguere maiuscole e minuscole).
- **`RIPETI`**: variabile d'ambiente che fissa il numero di ripetizioni di ogni caso; se non c'è, ogni caso usa le ripetizioni previste.
- La batteria completa conta **28 prove** e ogni prova è una chiamata a OpenAI: conviene lanciarla dopo una modifica al prompt o al codice, non di continuo.

## Esito della prova end-to-end (18 ottobre 2026)

Prova manuale dall'interfaccia (<http://localhost:5173>) con tutti i servizi avviati: Chroma, data agent, back end e front end. È divisa in quattro gruppi. I valori delle risposte sono quelli della tabella [Valori attesi](#valori-attesi).

### Domande della demo: 4 su 4

| Domanda | Esito |
|---|---|
| Qual è il tempo di prima risposta per una richiesta ad alta priorità? | Corretta: solo manuale, 2 ore lavorative |
| I 10 giocatori con il valore di mercato attuale più alto, con grafico | Corretta: elenco giusto, grafico presente, "Scarica" e "Ingrandisci" funzionanti |
| Metodologia per i difensori centrali e poi i 3 CB con il `duels_won_pct` attuale più alto | Corretta: usati entrambi gli strumenti |
| Conversazione: scout_rating medio nell'ultima stagione, poi "e nella stagione precedente?" | Corretta: 65.11, poi 66.18 |

### Casi di confine e conversazioni

| Domanda | Esito |
|---|---|
| Scout_rating medio per stagione | Corretto: solo dati, senza grafico perché non richiesto |
| Come si calcola lo scout_rating? | Corretto: solo manuale |
| Procedura di data cleaning del team, poi correzioni applicate ai dati | Corretto: la procedura (7 passaggi) dal manuale, le correzioni dai dati |
| Conversazione: ultima stagione, poi "e per i portieri?" | Corretto: 68.91 su 46 osservazioni |
| Conversazione: stagione 2024/25, poi "e in quella precedente?" | Corretto: 66.59 su 380 osservazioni |
| Rating attuale del giocatore 70 | Corretto: 66, con la segnalazione delle due osservazioni dello stesso giorno |
| Rating attuale dei giocatori 33 e 70 | Corretto dopo la correzione descritta più sotto |
| Classifica dei CB nell'ultima stagione | Corretta |
| Domanda fuori ambito | Corretta: nessuno strumento, risposta che delimita l'ambito |
| Saluto | Corretto: risposta breve, nessuno strumento |
| Richiesta di far eseguire codice | Corretta: nessuno strumento chiamato |
| I 3 CB con il `duels_won_pct` più alto nell'osservazione più recente | Limite noto, vedi [Limiti noti del data agent](#limiti-noti-del-data-agent) |

### Interfaccia: 5 su 5

| Prova | Esito |
|---|---|
| Risposta in ritardo dopo "Nuova chat" | Corretto: la risposta tardiva viene scartata |
| Campo di testo durante l'attesa | Corretto: disattivato |
| Messaggio vuoto e messaggio oltre i 2000 caratteri | Corretto: il messaggio vuoto non parte; il campo accetta al massimo 2000 caratteri |
| Schede di esempio con attesa lunga | Corretto: avviso dopo 10 secondi |
| Vista da telefono | Corretta |

### Servizi spenti: 3 su 3

| Servizio spento | Esito |
|---|---|
| Data agent | Corretto: nessun dato inventato, nessun errore tecnico nel browser |
| Chroma | Corretto: nessun dato inventato, nessun errore tecnico nel browser |
| Back end | Corretto: messaggio chiaro con il pulsante "Riprova", nessun errore tecnico nel browser |

### Difetto trovato e corretto

Con la domanda sui giocatori 33 e 70 l'orchestratore la divide in due richieste e scrive al data agent "giocatore con ID 70". Con questa forma il data agent spesso non eseguiva il controllo delle osservazioni nello stesso giorno, e a volte affermava che non ce n'erano: in una prova mirata le risposte corrette erano 19 su 33. La correzione sta nel prompt del data agent: la regola che attiva il controllo elenca ora le forme con cui si può indicare un giocatore («giocatore 70», «giocatore con ID 70», «player_id 70», «id 70», più id insieme). Dopo la correzione: «giocatore con ID 70» 30 su 30, «giocatore 70» 10 su 10, regressione sui casi già presenti 25 su 25, interfaccia 3 su 3. Nella [verifica da clone pulito](#verifica-da-clone-pulito-19-ottobre-2026) la batteria completa da 28 prove è passata 28 su 28.

## Verifica da clone pulito (19 ottobre 2026)

Il repository è stato clonato in una cartella nuova e installato seguendo solo il [README](../README.md), con un container di Chroma nuovo creato dal comando con il digest.

| Passo | Esito |
|---|---|
| `npm install` del back end | Nessun avviso, nessuna vulnerabilità |
| `npm audit --omit=dev` del front end | Nessuna vulnerabilità |
| Ingestione del manuale (`npm run ingest`) | 18 chunk |
| Avvio del data agent | Dataframe pulito di forma (1185, 35) |
| `npm run test:api -- --solo-a` | 23 OK su 23 |
| `regression_check.py`, batteria completa | 28 su 28 |
| Le quattro domande della demo dall'interfaccia | Corrette |
| Chiavi nei file del repository | Nessuna |
| File generati dall'installazione da committare | Nessuno |

Punti emersi e corretti nel README:

- **Python 3.13 su macOS**: il comando `python3` di sistema è la versione 3.9 e `python3.13` non esiste se non è stato installato; il README indica ora come installarlo e come controllare la versione.
- **URL senza `http://` nel `.env`**: il back end parte lo stesso e l'errore compare alla prima domanda che usa il servizio; la tabella dei problemi descrive ora il sintomo reale.

## Prove del limite di frequenza in locale

Il limite di frequenza su `POST /api/chat` ([Limite di frequenza](CONTRATTO_API.md#limite-di-frequenza)) è spento senza variabili d'ambiente e si prova a parte, con valori bassi, per non disturbare i test normali. Le richieste di prova usano un messaggio non valido, che il limite conta comunque perché sta prima della validazione del corpo.

| Prova | Esito |
|---|---|
| Test del contratto senza limite (`npm run test:api -- --solo-a`) | 23 OK su 23: con le variabili assenti il comportamento non cambia |
| Limite per IP impostato a 3 | le prime 3 richieste passano, dalla 4ª risposta 429 `RATE_LIMITED` |
| Limite globale impostato a 3 | le prime 3 richieste passano, dalla 4ª risposta 429 `RATE_LIMITED` |
| Avvii con configurazione non valida | 6 configurazioni rifiutate: il back end non parte e esce con codice 1 |

Il back end non parte se le tre variabili `RATE_LIMIT_*` sono presenti solo in parte, se un valore non è un intero positivo o se la finestra supera i 1440 minuti. Lo stesso vale per un `TRUST_PROXY` che non è un intero maggiore o uguale a 0.

## Prove del container in locale

Il container della demo ([Demo online e deploy](../README.md#demo-online-e-deploy)) è stato costruito e provato in locale con Docker prima di pubblicarlo (25 ottobre 2026).

| Prova | Esito |
|---|---|
| Dimensione dell'immagine | 1,96 GB su disco, 406 MB compressi |
| Le quattro domande della demo dall'interfaccia, servite da nginx | 4 su 4 |
| Porte interne (back end, data agent, Chroma) | non raggiungibili dall'esterno del container: si passa solo da nginx |
| Limite di frequenza dietro nginx | funziona: 429 e, nel log, l'IP del client mascherato (`172.17.x.x`, indirizzo della rete di Docker) |
| Riavvio del container | il manuale viene indicizzato di nuovo: 18 chunk |
| Segreti nell'immagine | nessuno |
| Prova a secco di `deploy/upload_space.sh --prova` | 74 file dal commit, nessuno tra quelli vietati |

## Simulazione con risorse ridotte

Prima di scegliere la piattaforma è stato simulato in locale il piano gratuito di Render, con il container limitato a 0,1 CPU e 512 MB di memoria, e con una regola di decisione fissata prima della prova ([Scelta della piattaforma](../README.md#scelta-della-piattaforma)):

```bash
docker run --cpus=0.1 --memory=512m ...
```

Tempi di avvio, dal lancio del container a nginx pronto:

| Servizio | Tempo |
|---|---|
| Chroma | 1,7 s |
| Indicizzazione del manuale | 28 s |
| Data agent | 91 s (di cui 79 s per caricare Python e le librerie) |
| Back end | 28 s |
| nginx | 0,5 s |
| **Totale** | **2 minuti e 29 secondi** |

La causa è la CPU, non il codice: quasi tutto il tempo del data agent serve a caricare le librerie Python. Con questo avvio il piano gratuito è stato scartato.

La memoria del container in funzione, misurata a parte, è tra 212 e 256 MB.

## Prove online (26 ottobre 2026)

Prove sulla demo pubblicata (<https://francodesc-scoutedge-analytics.hf.space>), dopo il caricamento del commit con `deploy/upload_space.sh`.

### Costruzione e avvio

| Prova | Esito |
|---|---|
| Build dell'immagine sullo Space (amd64) | riuscita al primo tentativo, circa 57 s |
| Avvio del container | servizi pronti circa 20 s dopo l'avvio |
| Riavvio dello Space dall'interfaccia web | demo funzionante circa 30 s dopo il clic |

### Le quattro domande della demo: 4 su 4

Dal computer, con i tempi di risposta:

| Domanda | Esito | Tempo |
|---|---|---|
| Tempo di prima risposta per priorità alta | Corretta | 3,6 s |
| 10 giocatori con il valore di mercato più alto, con grafico | Corretta | 15,0 s |
| Metodologia per i CB e poi i 3 CB con il `duels_won_pct` più alto | Corretta | 13,9 s |
| Conversazione: scout_rating medio nell'ultima stagione, poi "e nella stagione precedente?" | Corretta | 4,8 s + 5,4 s |

Le stesse quattro domande da un telefono Android: 4 su 4.

### Limite di frequenza

Per provarlo online i valori sono stati abbassati a 3 e poi ripristinati (20 per IP, 100 in totale).

| Prova | Esito |
|---|---|
| Limite per IP a 3 | risposte 400, 400, 400 (richieste volutamente non valide, che contano), poi 429 con `Retry-After` e corpo come da contratto |
| Limite globale a 3 | 429 alla 4ª richiesta |

### `TRUST_PROXY`

| Prova | Esito |
|---|---|
| `TRUST_PROXY=1` | il limite vede indirizzi interni di Hugging Face (`10.20.x.x`), diversi a ogni richiesta |
| `TRUST_PROXY=2` | il limite vede l'IP pubblico del computer da cui si prova |
| `X-Forwarded-For: 1.2.3.4` scritto a mano | ignorato: il limite continua a usare l'IP vero |
| Avvisi di `express-rate-limit` nei log | nessuno |

### Rotte interne ed errori

| Prova | Esito |
|---|---|
| `/analyze`, `/docs`, `/openapi.json`, `/.env`, file del codice, `GET /api/chat` | tutti 404 |
| Errori restituiti al browser | solo codici e messaggi del contratto |
| Pagine 404 di nginx | non mostrano la versione del server |

### Log

Controllati i log completi dello Space dopo le prove: nessuna chiave, nessun traceback, indirizzi IP solo mascherati. Nei log del back end compaiono gli argomenti che l'orchestratore passa agli strumenti (le domande riformulate): è un limite dichiarato nel [README](../README.md#la-demo-online).

### Non ancora osservato

La pausa automatica dello Space dopo 48 ore senza visite (non modificabile con la CPU basic) non è stata ancora osservata; è il comportamento dichiarato dalla piattaforma.