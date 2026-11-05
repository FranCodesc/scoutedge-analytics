# Orchestrazione nel back end

**Data:** dal 2026-10-08 al 2026-10-09 (commit `60f1e04`, `4efea08`, `64996d6`)

## Contesto

L'orchestratore deve decidere da solo, a ogni domanda, se rispondere con il manuale (`search_handbook`), con i dati (`analyze_data`), con entrambi o senza strumenti. Il funzionamento è descritto in [DESIGN_ORCHESTRATORE.md](../DESIGN_ORCHESTRATORE.md) (sezioni 3 e 4); qui c'è il perché delle scelte principali.

## Decisione

- **Ciclo ReAct scritto a mano**, con `@langchain/core` e `@langchain/openai`: al massimo 4 chiamate al modello con gli strumenti, poi una chiamata finale senza strumenti, così il turno finisce sempre con una risposta costruita sui risultati già ottenuti. Prima di ogni giro si controlla il `signal` della route, che interrompe il lavoro al timeout di 120 s. Modello `gpt-4o-mini` a temperatura 0.
- **Procedura di decisione esclusiva**: "solo analyze_data" per le domande di soli numeri anche se nominano una metrica, "solo search_handbook" per la sola metodologia, entrambi solo se la domanda chiede esplicitamente le due cose. Senza "solo" il modello leggeva le regole come cumulative e, su "scout_rating medio per stagione", consultava anche il manuale. Nella descrizione di `search_handbook` "scout_rating" è diventato "calcolo del rating": la parola esatta legava al manuale ogni domanda su quella metrica.
- **Parametro `chart` strutturato e obbligatorio** in `analyze_data`: la frase di richiesta del grafico la aggiunge il codice, e il risultato dello strumento dichiara sempre se il grafico è stato generato. Il prompt annuncia un grafico solo se il risultato lo conferma.
- **Errori degli strumenti restituiti come testo** (`ERRORE_STRUMENTO: ...`): il modello dichiara che un componente non è disponibile, non inventa numeri o contenuti, e in una domanda ibrida risponde alla parte disponibile. Solo gli errori del modello dell'orchestratore arrivano alla route, che risponde `502 LLM_ERROR`.
- **Strumenti in sequenza**: l'ordine dei risultati e di `toolsUsed` resta quello deciso dal modello. Il motivo originale, lo stato globale di matplotlib nel data agent, oggi è coperto dal lock ([pagina 6](06-esecuzione-del-codice-generato.md)).

## Alternative scartate

- **Un agente già pronto (`createAgent`)**. Sta nel pacchetto generico `langchain`, che porta con sé LangGraph e altre dipendenze: per due strumenti e un ciclo di circa 30 righe bastano i due pacchetti già usati. Un agente già pronto, superato il limite di giri, di solito si ferma con un errore; il ciclo a mano chiude invece con una risposta, e timeout e distinzione tra i due tipi di errore stanno in un punto solo. Nel data agent l'agente già pronto (`create_agent`) basta: un solo strumento, e il controllo sta nello strumento stesso.
- **Richiesta di grafico scritta dal modello dentro la domanda**: spariva dalla domanda 6 volte su 6, e il modello dichiarava comunque un grafico che non esisteva.
- **Una riga in più di caso di confine**, invece della procedura esclusiva: nessun effetto (la domanda sullo scout_rating per stagione falliva ancora 3 volte su 3); con la procedura esclusiva, 3 su 3 corrette.
- **Errori degli strumenti come eccezioni**: un componente spento farebbe fallire tutto il turno, anche la parte che si poteva rispondere.

## Conseguenze

- Il testo del prompt è vincolante: una modifica si decide e si registra prima in [DESIGN_ORCHESTRATORE.md](../DESIGN_ORCHESTRATORE.md), poi si ripetono anche i casi di confine.
- Quando si arriva al limite di giri, la chiamata finale senza strumenti risponde solo con i risultati già ottenuti, quindi la risposta può essere parziale.
- La scelta degli strumenti resta probabilistica: si misura con la valutazione automatica, non con una prova sola.

## Numeri

- 6 su 6, 3 su 3 e da 0/3 a 3/3: "Storico versioni" di [DESIGN_ORCHESTRATORE.md](../DESIGN_ORCHESTRATORE.md) (versioni 1.2, 1.3 e 1.4).
- Valutazione automatica del 2026-11-04: strumenti corretti in 80 turni su 80 ([corsa](../../back%20end/eval/risultati/corsa-20261104-1008.md)) e 20 su 20 sulla domanda ibrida dei difensori centrali ([corsa](../../back%20end/eval/risultati/corsa-20261104-1030.md)).

## Dove nel codice

- `back end/src/agent/orchestrator.js`: ciclo, limite di giri, chiamata finale.
- `back end/src/agent/tools.js`: i due strumenti, `chart`, `ERRORE_STRUMENTO`, raccolta di `toolsUsed`, `sources` e `chartUrl`.
- `back end/src/agent/systemPrompt.js`: procedura di decisione.
- `back end/src/routes/` (route della conversazione): timeout di 120 s e `502 LLM_ERROR`.
- `back end/test/turnTools.test.js`, `back end/test/tool.test.js`, `back end/test/chatRoute.test.js`.
