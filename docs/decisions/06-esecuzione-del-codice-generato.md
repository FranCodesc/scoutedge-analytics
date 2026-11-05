# Esecuzione del codice generato

**Data:** dal 2026-10-06 al 2026-11-03 (commit `5c85f92`, `9126ef5`, `3009cba`)

## Contesto

Il data agent esegue con `exec`/`eval`, nel processo del servizio, il codice pandas e matplotlib scritto dal modello. FastAPI esegue `analyze`, che è una funzione sincrona, in un pool di thread: nella demo pubblica due richieste possono girare insieme nello stesso processo.

## Decisione

- **Un agente per richiesta, con una copia del dataframe** (2026-10-06). `main.py` chiama `build_data_agent` a ogni richiesta e `make_python_tool` crea un namespace nuovo con `df.copy()`: le variabili restano tra le chiamate dello strumento nella stessa richiesta, non passano alla successiva, e nessuna richiesta modifica il dataframe condiviso. Costruire l'agente costa pochi millisecondi, contro i secondi della chiamata al modello.
- **Grafici salvati solo dallo strumento** (2026-10-12). Se il codice del modello chiamava `plt.savefig` scriveva un PNG fuori da `charts/` con un nome suo, e se poi chiamava `plt.close()` la figura spariva prima che lo strumento la vedesse: grafico mancante in modo intermittente. Durante l'esecuzione `plt.savefig`, `plt.close`, `plt.show` e `Figure.savefig` non fanno nulla; dopo, lo strumento salva la figura come `chart_<8 esadecimali>.png` e aggiunge la nota che `main.py` trasforma in `chart_url`.
- **Un lock attorno all'esecuzione** (2026-11-03). Le sostituzioni del punto precedente, la cattura di `sys.stdout` e le opzioni di pandas valgono per tutto il processo: con due richieste insieme, la seconda poteva salvare come "originale" la funzione vuota messa dalla prima, e da quel momento i grafici sparivano fino al riavvio. Un `threading.Lock` serializza solo l'esecuzione del codice; la chiamata al modello resta fuori e continua in parallelo. Chi aspetta più di 30 s riceve un errore leggibile ("servizio occupato"), prima del timeout di 90 s del back end.
- **Pulizia automatica dei grafici** (2026-11-03). All'avvio e prima di ogni salvataggio si cancellano i PNG più vecchi di 2 ore e quelli oltre i 200 più recenti, solo se hanno il nome esatto dei grafici dello strumento. Due ore superano di molto la scadenza delle sessioni (30 minuti di inattività); se un grafico non c'è più, il front end mostra un testo di riserva.

## Alternative scartate

- **API a oggetti di matplotlib (`Figure()` senza `pyplot`).** Elimina la figura corrente condivisa, ma non basta: anche `sys.stdout` (sostituito per catturare l'output) e le opzioni di pandas sono globali al processo, e seaborn disegna sugli assi correnti di pyplot. Richiederebbe inoltre di cambiare la docstring dello strumento e il prompt, perché il modello scrive codice con `plt` e `sns`, e quindi di rifare la regressione e la valutazione con il modello reale. Il lock copre tutto lo stato condiviso senza toccare i prompt.
- **Processi separati.** Isolerebbero tutto lo stato e permetterebbero di interrompere un codice che non termina. Ma le variabili del modello devono restare tra le chiamate della stessa richiesta: un processo per chiamata le perderebbe e ricaricherebbe ogni volta le librerie (la parte lenta dell'avvio, vedi [docs/TEST.md](../TEST.md#simulazione-con-risorse-ridotte)), mentre un processo vivo per richiesta è un cambio di architettura dello strumento, con comunicazione, timeout e grafici da gestire e testare. Il lock risolve il bug con poche righe e senza cambiare ciò che vede il modello. Resta la strada se servisse un timeout sul codice o una sandbox.

## Conseguenze

- Le esecuzioni del codice avvengono una alla volta; di norma durano meno di un secondo.
- Un codice che non termina tiene il lock: le altre analisi ricevono "servizio occupato" dopo 30 s e nessun timeout lo interrompe.
- Il salvataggio riservato allo strumento non è una sandbox: il codice del modello può ancora scrivere file in altri modi. L'assenza di sandbox resta il limite principale del progetto.
- Un solo grafico per esecuzione.
- Nessuna nuova dipendenza: `threading` è nella libreria standard.

## Numeri

- Il bug è stato riprodotto con un test prima di correggerlo: `test_due_esecuzioni_parallele` in `data_agent/tests/test_concorrenza.py` (20 giri, due esecuzioni sovrapposte) falliva in 17 giri su 20 sul codice di `9c3e341` e passa in 20 su 20 con il lock (`3009cba`).
- Costanti: `ATTESA_MASSIMA_LOCK_S = 30`, `CONSERVAZIONE_GRAFICI_S` di 2 ore, `MAX_GRAFICI = 200`.

## Dove nel codice

- `data_agent/agent.py`: costanti in testa al file, `pulisci_grafici`, `make_python_tool` (`_esegui` e `python_repl`).
- `data_agent/main.py`: avvio (pulizia iniziale) e `analyze` (agente per richiesta, lettura della nota del grafico).
- `data_agent/tests/test_concorrenza.py` e `data_agent/tests/test_pulizia_grafici.py`.
- `front end/src/components/ChartDialog.jsx` e `front end/src/components/ChartsPanel.jsx`: testo di riserva.
