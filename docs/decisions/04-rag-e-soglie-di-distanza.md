# RAG con Chroma e soglie di distanza

**Data:** dal 2026-10-07 al 2026-10-09 (commit `d16dded`, `1f6b6d6`, `60f1e04`)

## Contesto

Le domande su regole, procedure e metodologia si rispondono con il manuale interno (`data/platform_handbook.md`), indicizzato in Chroma. Servono due cose: che la ricerca restituisca i passaggi giusti, e che le sezioni mostrate come fonti (`sources`) siano solo quelle davvero pertinenti.

## Decisione

- **Client diretto di Chroma** (pacchetto `chromadb`), senza il vector store di LangChain.
- **18 chunk con id deterministici** (`sec-7`, `sec-3-1`, `sec-8-q2`, ...): sezioni intere, la sezione 3 per sottosezione e la sezione 8 per domanda; ogni chunk inizia con il titolo, così l'embedding conserva il contesto. L'indicizzazione usa `upsert` e alla fine cancella gli id non più presenti nel manuale: rilanciarla aggiorna gli stessi record invece di duplicarli. Se la struttura del manuale non è quella attesa si ferma con un errore.
- **Embedding calcolati fuori da Chroma**, con `text-embedding-3-small` definito in un solo punto e usato sia per indicizzare sia per cercare (`embeddingFunction: null`); **distanza coseno**, fissata alla creazione della collection.
- **Due soglie sui primi 4 passaggi**: un passaggio resta se la distanza è al massimo 0.60 (soglia assoluta) e al massimo la migliore + 0.12 (soglia relativa).

## Come sono state scelte le soglie

Dalle distanze misurate sul manuale indicizzato ([tabella](../TEST.md#distanze-di-retrieval)):

- le domande pertinenti hanno il passaggio migliore tra 0.293 e 0.491; quella fuori ambito ("capitale della Francia") ha tutti i passaggi tra 0.893 e 0.938. La soglia di 0.60 separa i due gruppi;
- per lo SLA a priorità alta il migliore è `sec-7` a 0.364 e il secondo una FAQ a 0.550: con la sola soglia assoluta la FAQ entrerebbe tra le fonti. Con la soglia relativa (0.364 + 0.12 = 0.484) resta solo la sezione 7;
- per lo scout_rating restano `sec-3-1`, `sec-8-q2` e `sec-8-q1` (fino a 0.413), esce `sec-3-4` a 0.451.

## Alternative scartate

- **Vector store Chroma di LangChain** (`@langchain/community`, tolto il 2026-10-07 perché non usato): ciò che conta per questa RAG (id scelti, `upsert` e pulizia degli orfani, metrica coseno, embedding esterni, distanze restituite così come sono) con il client diretto sta in poche righe esplicite, senza una dipendenza grande in più.
- **Solo i primi passaggi, senza soglie**: una domanda fuori ambito riceverebbe comunque quattro passaggi a più di 0.89, e le fonti si riempirebbero di sezioni non pertinenti.
- **Solo la soglia assoluta**: vedi il caso dello SLA.
- **`getOrCreateCollection` nella ricerca**: se l'indicizzazione non è stata eseguita creerebbe una collection vuota e risponderebbe "nessun risultato" in silenzio; si usa `getCollection`, che dà un errore esplicito.

## Conseguenze

- Le soglie valgono per questo manuale e questo modello di embedding: se il manuale cambia molto, o cambia il modello, le distanze vanno rimisurate e il manuale reindicizzato.
- Sono state scelte sulle distanze di sei domande di prova: per il manuale attuale bastano, ma con un manuale più grande andrebbero verificate su un insieme di domande più ampio.
- Online i dati di Chroma stanno in una cartella temporanea: a ogni avvio il manuale viene indicizzato di nuovo (18 chunk), con una chiamata agli embedding.
- Il server Chroma è fissato con il digest dell'immagine (versione 1.4.4), in locale e nel container.

## Numeri

- 18 chunk e distanze: [docs/TEST.md](../TEST.md#distanze-di-retrieval).
- Valutazione automatica del 2026-11-04: le tre domande sul manuale corrette 15 volte su 15 ([corsa](../../back%20end/eval/risultati/corsa-20261104-1008.md)).

## Dove nel codice

- `back end/scripts/ingestHandbook.js`: divisione in chunk, id, `upsert`, pulizia degli orfani.
- `back end/src/services/chromaClient.js`, `back end/src/services/embeddings.js`, `back end/src/services/ragService.js`.
- `back end/src/agent/tools.js`: `MAX_DISTANCE`, `MAX_DISTANCE_GAP`, `filterRelevantPassages`.
- `back end/test/tool.test.js` e `back end/test/turnTools.test.js`: le soglie.
