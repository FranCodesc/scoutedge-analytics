# pandas e non DuckDB

**Data:** 2026-11-05 (commit `79ca888`)

## Contesto

Il data agent tiene in memoria un dataframe pandas di 1.185 righe pulite (0,8 MB, avvio in circa 0,13 s). La domanda è se, al crescere dei dati, convenga salvarli in un database come DuckDB o SQLite, e da quale dimensione.

## Decisione

Nessuna modifica al codice: **pandas basta fino a 60 volte il file attuale** (71.100 righe pulite). La decisione viene da un benchmark su dataset crescenti, con una regola fissata prima di misurare e scritta in `benchmark_riepilogo.py`. Una dimensione è oltre soglia se una domanda supera 1 s (A), il dataframe pulito supera 50 MB (B1), il picco di memoria dell'avvio supera 250 MB (B2) o l'avvio supera 10 s (C); si cambia solo se l'alternativa migliora di almeno 2 volte la misura violata.

## Come si è misurato

- Dataset sintetici da 1× a 1000×, generati dal CSV reale con id nuovi, rumore, le stesse anomalie nella stessa proporzione e un seme fisso: passano la pulizia e lo schema come il file vero.
- Un processo per dimensione; avvio, memoria, copia per richiesta e cinque domande rappresentative in pandas e in DuckDB (sul dataframe, su una tabella e su Parquet), mediana di 5 ripetizioni.
- I risultati di pandas e DuckDB sono uguali in tutti i 90 confronti.

## Risultati

- Fino a 60× nessuna soglia superata (dataframe a 50,0 MB, al limite). A 100× si supera B1 (83,3 MB); a 1000× B1, B2 e C (832,6 MB, picco di 1.646 MB, avvio di 73,5 s).
- Il primo limite è la memoria, non il tempo delle domande: la più lenta richiede 455 ms a 1000×. Circa il 90% dell'avvio è la pulizia.
- A 100× DuckDB su Parquet migliora la memoria solo di 1,65 volte, sotto la soglia di 2; a 1000× risolve tutto (240 MB contro 833 MB, avvio da Parquet già pulito in 0,85 s contro 73,5 s). DuckDB conviene quindi da una dimensione tra 100× e 1000×, intorno a 170× per estrapolazione: è una stima, non una misura.

## Alternative scartate

- **DuckDB oggi.** Nessuna soglia è superata, e il cambio più utile alle domande è anche il più costoso: le regole del prompt sono scritte in pandas e andrebbero riscritte in SQL, con regressione e valutazione da rifare.
- **SQLite, non misurato.** Le domande sono analisi su molte righe (medie, classifiche, raggruppamenti): DuckDB è un motore colonnare pensato per questo e legge direttamente dataframe e Parquet, SQLite salva per righe ed è pensato per leggere e scrivere poche righe alla volta. Il costo del cambio sarebbe lo stesso (tabella e regole in SQL). Se non lo giustifica il candidato più adatto alle analisi, non lo giustifica SQLite. È un ragionamento, non una misura: il benchmark si può estendere a SQLite senza dipendenze nuove.

## Conseguenze

- Se il dataset crescesse, prima gli interventi più economici: liberare il dataframe grezzo, che oggi resta in memoria accanto a quello pulito (102 MB su 185 MB a 100×), e riscrivere la pulizia con operazioni vettoriali invece di `.apply` riga per riga. Poi l'avvio da Parquet già pulito, che non cambia il prompt; DuckDB come motore delle domande solo se una domanda si avvicinasse a 1 s.
- `duckdb` è solo in `requirements-dev.txt`: nell'immagine di produzione non entra.
- Limiti della misura: una sola macchina (Apple M1), più veloce della CPU dello Space; il picco di memoria varia tra le corse (218 MB e 258 MB a 100×); cinque domande; dati sintetici.

## Numeri

- Tutte le misure, la regola e l'esito: [corsa completa](../../data_agent/scripts/risultati_benchmark/corsa-20261105-1051.md) e [corsa preliminare](../../data_agent/scripts/risultati_benchmark/corsa-20261105-1042.md).

## Dove nel codice

- `data_agent/scripts/dataset_sintetico.py`, `data_agent/scripts/benchmark.py`, `data_agent/scripts/benchmark_riepilogo.py`.
- `data_agent/main.py`: caricamento all'avvio, il punto che cambierebbe per primo.