# pandas in memoria; DuckDB e SQLite misurati

**Data:** 2026-11-05 e 2026-11-11 (commit `79ca888`, `8d6d7da`)

## Contesto

Il data agent tiene in memoria un dataframe pandas di 1.185 righe pulite (0,8 MB, avvio in circa 0,13 s). La domanda è se, al crescere dei dati, convenga salvarli in un database come DuckDB o SQLite, e da quale dimensione.

## Decisione

Nessuna modifica al codice: **pandas basta fino a 60 volte il file attuale** (71.100 righe pulite); oltre, la scelta dipende dalla soglia superata. La decisione viene da un benchmark su dataset crescenti, con una regola fissata prima di misurare e scritta in `benchmark_riepilogo.py`. Una dimensione è oltre soglia se una domanda con pandas supera 1 s (A), il dataframe pulito supera 50 MB (B1), il picco di memoria dell'avvio supera 250 MB (B2) o l'avvio supera 10 s (C); si cambia solo se l'alternativa migliora di almeno 2 volte la misura violata. La regola è del 5 novembre (pandas e DuckDB); l'11 novembre il benchmark è stato esteso a SQLite con la stessa regola, senza cambiarla.

## Come si è misurato

- Dataset sintetici da 1× a 1000×, generati dal CSV reale con id nuovi, rumore, le stesse anomalie nella stessa proporzione e un seme fisso: passano la pulizia e lo schema come il file vero.
- Un processo per dimensione; avvio, memoria, copia per richiesta e cinque domande rappresentative, mediana di 5 ripetizioni. DuckDB sul dataframe, su una tabella e su Parquet; SQLite (modulo `sqlite3` della libreria standard, SQLite 3.51.0) in memoria, su file e su file con tre indici e `ANALYZE`. Per la memoria, un processo con il solo motore e nessun dataframe; per l'avvio, la lettura di un file già pulito.
- I risultati di DuckDB e SQLite sono uguali a quelli di pandas in tutti i 180 confronti, e il dataframe riletto da SQLite è uguale a quello pulito a tutte le dimensioni.

## Risultati (corsa dell'11 novembre)

| Dimensione | Soglie superate con pandas | DuckDB | SQLite |
|---|---|---|---|
| Fino a 60× | Nessuna (a 60×: dataframe 50,0 MB, domanda più lenta 19,5 ms, avvio 4,32 s) | — | — |
| 100× | B1: dataframe di 83,3 MB | 50,0 MB su Parquet, 1,67 volte meno: **non risolve** | 3,0 MB su file: **risolve** |
| 1000× | B1 (832,6 MB), B2 (picco di 1.724 MB), C (avvio di 75,3 s) | 239,1 MB, avvio da Parquet già pulito in 0,83 s: **risolve** | 3,0 MB, avvio da SQLite già pulito in 9,99 s: **risolve** |

- La soglia A non si supera mai: con pandas la domanda più lenta richiede 458 ms a 1000×. Circa il 90% dell'avvio è la pulizia.
- DuckDB ha un costo fisso di memoria di circa 36 MB, presente già a 1×: per questo a 100× non scende sotto la metà del dataframe.

Osservazioni fatte dopo la misura. Non cambiano la regola, che si applica com'è scritta, ma contano per la scelta:

- **SQLite è lento sulle domande sullo stato attuale.** Le due domande con funzione di finestra (l'osservazione più recente di ogni giocatore) richiedono, con gli indici, 197,6 ms a 100× e 1,98 s a 1000× (3,2–3,4 s senza indici), contro 425–458 ms di pandas e 124–142 ms di DuckDB. I tempi crescono in modo lineare: circa 1 s intorno a 500×, per estrapolazione. Gli indici accelerano molto filtri e raggruppamenti, poco le funzioni di finestra (1,6–1,7 volte a 1000×).
- **L'avvio da SQLite a 1000× è al limite**: 9,99 s contro una soglia di 10 s. Preparare il file costa 6,92 s di scrittura e 2,10 s di indici e `ANALYZE`; il file pesa 384 MB con gli indici, contro i 32 MB del Parquet.
- **La memoria di SQLite è costante** (3,0 MB da 10× in su) perché legge dal disco a richiesta: la cache del sistema operativo non è misurata, quindi il confronto è tra un dato tutto in memoria e uno letto dal disco.
- **B2 a 100× è instabile**: 218, 258 e 239 MB in tre corse, attorno alla soglia di 250 MB.

## Lettura

- **Oggi** nessuna soglia è superata: nessuna modifica.
- **Oltre 60×** la scelta dipende dalla soglia superata. Se il limite è la memoria, come a 100×, la regola indica SQLite su file con indici (3 MB, domande sotto 0,2 s a 100×). Se contano i tempi delle domande, DuckDB è l'unico sotto 1 s a 1000×.
- Entrambi richiedono di riscrivere in SQL le regole del prompt del data agent, con regressione e valutazione da rifare: prima vengono gli interventi più economici (vedi Conseguenze).

## Alternative scartate

- **DuckDB o SQLite oggi.** Nessuna soglia è superata, e il cambio è costoso: le regole del prompt sono scritte in pandas e andrebbero riscritte in SQL.
- **Cambiare la regola dopo aver visto i risultati di SQLite**, per esempio con una soglia sui tempi di SQLite: la regola fissata prima si applica com'è scritta, e ciò che emerge dopo si dichiara come osservazione.

## Conseguenze

- Se il dataset crescesse, prima gli interventi più economici: liberare il dataframe grezzo, che oggi resta in memoria accanto a quello pulito (102 MB accanto agli 83 MB del pulito a 100×), e riscrivere la pulizia con operazioni vettoriali invece di `.apply` riga per riga. Poi l'avvio da un file già pulito, che riduce il tempo di avvio senza cambiare il prompt. Un motore SQL solo se una soglia restasse superata: SQLite per la memoria, DuckDB per i tempi delle domande.
- `duckdb` è solo in `requirements-dev.txt` e `sqlite3` è nella libreria standard: nell'immagine di produzione non entra nessuna dipendenza nuova.
- Limiti della misura: una sola macchina (Apple M1), più veloce della CPU dello Space; cinque domande; dati sintetici. Fino a 100× il calcolo con pandas pesa meno dello 0,4% del tempo medio di una risposta del modello (5,1% a 1000×).

## Numeri

- Corsa di riferimento, con SQLite: [corsa dell'11 novembre](../../data_agent/scripts/risultati_benchmark/corsa-20261111-1318.md). Corse del 5 novembre, con pandas e DuckDB: [completa](../../data_agent/scripts/risultati_benchmark/corsa-20261105-1051.md) e [preliminare](../../data_agent/scripts/risultati_benchmark/corsa-20261105-1042.md).

## Dove nel codice

- `data_agent/scripts/dataset_sintetico.py`, `data_agent/scripts/benchmark.py` (domande in pandas, DuckDB e SQLite; indici in `INDICI_SQLITE`), `data_agent/scripts/benchmark_riepilogo.py` (regola ed esito).
- `data_agent/main.py`: caricamento all'avvio, il punto che cambierebbe per primo.