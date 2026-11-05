# Pulizia e schema dei dati

**Data:** dal 2026-10-01 al 2026-11-03 (commit `3ab8f84`, `b43a56b`, `0d9e15e`, `ae98d72`)

## Contesto

Il CSV grezzo (`data/scouting_data.csv`, 1208 righe) ha grafie diverse per club e nazionalità, duplicati, importi e date in formati misti, valori fisicamente impossibili, nomi in kanji e nomi con titoli e qualifiche. Il data agent risponde con codice generato dal modello: se i dati non sono puliti e controllati prima, ogni risposta eredita gli stessi errori.

## Decisione

- **Pulizia deterministica all'avvio** (`clean_scouting_data` in `cleaning.py`), secondo la procedura della sezione 6 del manuale: elenchi espliciti (25 club, titoli, traslitterazione dei nomi giapponesi), formati di data espliciti, valori impossibili corretti e non eliminati, deduplica dopo le normalizzazioni e prima dell'imputazione, mediana per ruolo e stagione, colonne dei portieri lasciate vuote per gli altri ruoli. Le osservazioni dello stesso giocatore nello stesso giorno restano, ma vengono contate e segnalate.
- **`cleaning_report`**: i conteggi di ogni correzione si registrano mentre la correzione viene applicata (è l'unico momento in cui si conoscono il valore prima e quello dopo) e arrivano nel prompt del data agent, che li usa per rispondere sulle correzioni.
- **Schema dichiarato in Python** (`schema.py`), controllato all'avvio: sul CSV grezzo le colonne attese, sul dataframe pulito tipi, intervalli di plausibilità, domini chiusi, valori mancanti ammessi solo nelle colonne dei portieri, nessuna riga identica e relazioni tra colonne (minuti per partita, data dentro la stagione, contratto non scaduto prima dell'osservazione, attributi fissi per lo stesso `player_id`, nomi senza titoli né caratteri non latini).
- **Tutte le violazioni in un solo errore**: un `SchemaError` le elenca tutte, ciascuna con un esempio (`player_id` e valore), e il servizio non parte: meglio un avvio fallito che risposte su dati sbagliati.

## Alternative scartate

- **Lasciare la pulizia al codice generato dal modello a ogni domanda**: risultati diversi da una domanda all'altra e nessun conteggio affidabile delle correzioni.
- **La grafia più frequente come nome del club**: un elenco esplicito dà un risultato riproducibile e blocca subito un club inatteso.
- **Riconoscimento automatico delle date**: può scambiare giorno e mese (03/04/2025).
- **Una libreria di validazione per dataframe (per esempio `pandera`)**: una dipendenza in più nell'immagine di produzione per circa 200 righe di controlli, mentre per le correzioni si è scelto di non aggiungerne.
- **`pydantic`**, già presente perché lo usa FastAPI: valida un oggetto alla volta, mentre gran parte dei controlli riguarda il dataframe intero (righe duplicate, attributi uguali per tutte le righe di un giocatore, numero di club, date dentro la stagione). Con pandas sono maschere su tutte le righe in un colpo solo.
- **Fermarsi alla prima violazione**: costringerebbe a correggere, rilanciare e scoprire l'errore successivo.

## Conseguenze

- Un CSV che non rispetta lo schema blocca l'avvio del data agent: è voluto.
- I limiti di plausibilità sono scelti a mano e larghi: fermano gli errori che la pulizia corregge (percentuali oltre 100, altezze con uno zero in più, velocità negative), non un dato vero ma insolito.
- Le stagioni ammesse sono scritte in `schema.py` e nel prompt dell'orchestratore: se cambia il dataset vanno aggiornate in entrambi.
- La pulizia è la parte più lunga dell'avvio: circa il 90% del tempo nel benchmark ([risultati](../../data_agent/scripts/risultati_benchmark/corsa-20261105-1051.md)).

## Numeri

- 1208 righe, poi 1185; 23 duplicati (13 identici nel file grezzo, 10 emersi dopo le normalizzazioni); club da 74 a 25 grafie; nazionalità da 45 a 24; 5 casi di osservazioni nello stesso giorno; titoli tolti dai nomi di 12 giocatori (113 righe). Sono verificati da `data_agent/tests/test_dataset_reale.py` e riportati nei [Valori attesi](../TEST.md#valori-attesi).

## Dove nel codice

- `data_agent/cleaning.py`, `data_agent/schema.py`, `data_agent/main.py` (avvio: lettura, controllo delle colonne, pulizia, schema).
- `data_agent/tests/test_cleaning.py`, `data_agent/tests/test_schema.py`, `data_agent/tests/test_dataset_reale.py`.
- `data/platform_handbook.md`, sezione 6: la procedura di pulizia.
