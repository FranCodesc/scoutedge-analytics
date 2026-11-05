# Decisioni di progetto

Storia e motivazioni delle scelte principali: contesto, decisione, alternative scartate, conseguenze e numeri. Come funziona il sistema è descritto in [DESIGN_ORCHESTRATORE.md](../DESIGN_ORCHESTRATORE.md) e come si verifica in [TEST.md](../TEST.md); qui si spiega perché è fatto così.

| Pagina | Di cosa parla |
|---|---|
| [01 - Orchestrazione nel back end](01-orchestrazione-nel-back-end.md) | Ciclo ReAct scritto a mano, procedura di decisione esclusiva, parametro `chart` ed errori degli strumenti come testo |
| [02 - Domande autonome per il data agent](02-domande-autonome-per-il-data-agent.md) | Come l'orchestratore riscrive le domande di una conversazione per un servizio che non la vede |
| [03 - Regole del prompt del data agent](03-regole-del-prompt-del-data-agent.md) | Procedure con codice esatto invece di regole condizionali, e i difetti che le hanno motivate |
| [04 - RAG con Chroma e soglie di distanza](04-rag-e-soglie-di-distanza.md) | Client diretto di Chroma, id deterministici e come sono state scelte le due soglie |
| [05 - Pulizia e schema dei dati](05-pulizia-e-schema-dei-dati.md) | Pulizia deterministica all'avvio, schema dichiarato in Python e tutte le violazioni in un solo errore |
| [06 - Esecuzione del codice generato](06-esecuzione-del-codice-generato.md) | Agente per richiesta, grafici salvati dallo strumento, lock attorno all'esecuzione e pulizia dei grafici |
| [07 - Test e valutazione](07-test-e-valutazione.md) | Test unitari senza token, dipendenze iniettabili, valutazione con il modello reale, integrazione continua senza deploy automatico |
| [08 - Deploy su Hugging Face Spaces](08-deploy-su-hugging-face-spaces.md) | Un container con nginx unico punto esposto, scelta della piattaforma, `TRUST_PROXY` e limite di frequenza |
| [09 - pandas e non DuckDB](09-pandas-e-non-duckdb.md) | Benchmark con regola fissata prima: pandas basta fino a 60 volte i dati attuali, quando conviene DuckDB e perché non SQLite |