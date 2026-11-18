# pandas in memoria; DuckDB e SQLite misurati

**Data:** 2026-11-05, 2026-11-11 e 2026-11-18 (commit `79ca888`, `8d6d7da`, `dc4d81c`, `4ef960b`)

## Contesto

Il data agent tiene in memoria un dataframe pandas di 1.185 righe pulite (0,8 MB). La domanda è se, al crescere dei dati, convenga salvarli in un database come DuckDB o SQLite, e da quale dimensione, sulla macchina su cui gira la demo.

## Decisione

Nessuna modifica al codice: **sulla macchina della demo pandas basta fino a 30 volte il file attuale** (35.550 righe pulite; fino a 60 volte su un Apple M1). Il primo limite in produzione è il tempo di avvio, che si risolve partendo da un file già pulito, senza cambiare motore; un motore SQL servirebbe più avanti, e la scelta dipende dalla soglia superata. La decisione viene da un benchmark su dataset crescenti, con una regola fissata prima di misurare e scritta in `benchmark_riepilogo.py`. Una dimensione è oltre soglia se una domanda con pandas supera 1 s (A), il dataframe pulito supera 50 MB (B1), il picco di memoria dell'avvio supera 250 MB (B2) o l'avvio supera 10 s (C); si cambia solo se l'alternativa migliora di almeno 2 volte la misura violata. La regola è del 5 novembre (pandas e DuckDB); l'11 novembre il benchmark è stato esteso a SQLite e il 18 novembre è stato rifatto sulla macchina della demo, sempre con la stessa regola.

## Come si è misurato

- Dataset sintetici da 1× a 1000×, generati dal CSV reale con id nuovi, rumore, le stesse anomalie nella stessa proporzione e un seme fisso: passano la pulizia e lo schema come il file vero.
- Un processo per dimensione; avvio, memoria, copia per richiesta e cinque domande rappresentative, mediana di 5 ripetizioni. DuckDB sul dataframe, su una tabella e su Parquet; SQLite (modulo `sqlite3` della libreria standard) in memoria, su file e su file con tre indici e `ANALYZE`. Per la memoria, un processo con il solo motore e nessun dataframe; per l'avvio, la lettura di un file già pulito.
- **Due macchine.** L'11 novembre un Apple M1 (8 core, 8,6 GB, SQLite 3.51.0). Il 18 novembre un Job di Hugging Face `cpu-basic`, lanciato con `deploy/benchmark_job.sh` sull'immagine di base della demo (`python:3.13-slim-trixie`, SQLite 3.46.1): Intel Xeon Platinum 8375C, limite di 2 CPU e di 16 GB, cioè la stessa CPU e gli stessi limiti che lo Space della demo scrive nel log all'avvio. Il riepilogo riporta i limiti del container (`cpu.max`, `memory.max`), perché i core e la memoria visti dal sistema sono quelli della macchina che lo ospita.
- I risultati di DuckDB e SQLite sono uguali a quelli di pandas in tutti i 180 confronti di ogni corsa, e il dataframe riletto da SQLite è uguale a quello pulito a tutte le dimensioni.

## Risultati sulla macchina della demo (corsa del 18 novembre)

| Dimensione | Soglie superate con pandas | DuckDB | SQLite |
|---|---|---|---|
| Fino a 30× | Nessuna (a 30×: avvio 6,16 s, dataframe 25,0 MB, domanda più lenta 13,3 ms) | — | — |
| 60× | C: avvio di 12,24 s | avvio da Parquet già pulito in 0,13 s: **risolve** | avvio da SQLite già pulito in 0,85 s: **risolve** |
| 100× | B1 (83,3 MB), C (20,27 s) | B1: 63,1 MB su Parquet, **non risolve**; C: 0,17 s, risolve | B1: 2,9 MB su file, risolve; C: 1,41 s, risolve |
| 1000× | B1 (832,6 MB), B2 (picco di 1.465,8 MB), C (185,19 s) | 203,8 MB, avvio da Parquet già pulito in 1,42 s: **risolve** | B1 e B2: 3,0 MB, risolve; C: 12,78 s, **non risolve** |

- La pulizia è il 94% dell'avvio (11,56 s su 12,24 s a 60×): il limite è il tempo di pulizia, non pandas, e l'avvio da un file già pulito lo risolve senza cambiare motore.
- La soglia C cade tra 30× e 60×: l'avvio cresce di circa 0,2 s per ogni volta il file attuale, quindi circa 50× per estrapolazione lineare.
- La soglia A non si supera mai: con pandas la domanda più lenta richiede 570 ms a 1000×. Fino a 100× il calcolo pesa meno dello 0,6% del tempo medio di una risposta del modello (6,4% a 1000×).
- DuckDB ha un costo fisso di memoria di circa 48 MB su questa macchina (circa 36 MB sull'M1), presente già a 1×: per questo a 100× non scende sotto la metà del dataframe.

**Confronto con l'Apple M1 (corsa dell'11 novembre).** La memoria è la stessa, perché dipende dai dati (dataframe di 50,0, 83,3 e 832,6 MB a 60×, 100× e 1000×); i tempi no. Sulla macchina della demo l'avvio è circa 2,5–2,8 volte più lento (12,24 s contro 4,32 s a 60×) e le domande circa 1,2–1,5 volte. Sull'M1 nessuna soglia era superata fino a 60× e il primo limite era la memoria a 100×; sulla macchina della demo il primo limite è il tempo di avvio, a 60×. A 1000× l'avvio da SQLite già pulito era al limite sull'M1 (9,99 s) e sulla macchina della demo non risolve (12,78 s).

Osservazioni fatte dopo la misura. Non cambiano la regola, che si applica com'è scritta, ma contano per la scelta:

- **SQLite è lento sulle domande sullo stato attuale.** Con gli indici le due domande con funzione di finestra (l'osservazione più recente di ogni giocatore) richiedono 337–341 ms a 100× e 3,09–3,11 s a 1000× sulla macchina della demo (1,98 s sull'M1), contro 533–570 ms di pandas e 166–197 ms di DuckDB. Gli indici accelerano molto filtri e raggruppamenti, poco le funzioni di finestra.
- **Preparare il file SQLite costa**: a 1000× 9,82 s di scrittura e 3,10 s di indici e `ANALYZE`; il file pesa 384 MB con gli indici, contro i 32 MB del Parquet.
- **La memoria di SQLite è costante** (circa 3 MB da 10× in su) perché legge dal disco a richiesta: la cache del sistema operativo non è misurata, quindi il confronto è tra un dato tutto in memoria e uno letto dal disco.
- **B2 a 100× è instabile sull'M1**: 218, 258 e 239 MB in tre corse, attorno alla soglia di 250 MB; sulla macchina della demo 159 MB.

## Lettura

- **Oggi** nessuna soglia è superata (a 1× l'avvio richiede 0,34 s sulla macchina della demo): nessuna modifica.
- **Fino a 30×** pandas basta così com'è sulla macchina della demo.
- **Il primo limite in produzione è l'avvio** (C, già a 60×). Si risolve senza cambiare motore né prompt: pulizia con operazioni vettoriali invece di `.apply` riga per riga, oppure avvio da un file già pulito (da Parquet 0,13 s a 60×).
- **Oltre 100×** conta anche la memoria: la regola indica SQLite su file con indici per la memoria e DuckDB per i tempi delle domande e dell'avvio. Entrambi richiedono di riscrivere in SQL le regole del prompt del data agent, con regressione e valutazione da rifare.

## Alternative scartate

- **DuckDB o SQLite oggi.** Nessuna soglia è superata, e il cambio è costoso: le regole del prompt sono scritte in pandas e andrebbero riscritte in SQL.
- **Cambiare la regola dopo aver visto i risultati**, per esempio con una soglia sui tempi di SQLite o con una soglia di avvio più larga perché la macchina della demo è più lenta: la regola fissata prima si applica com'è scritta, e ciò che emerge dopo si dichiara come osservazione.
- **Misurare solo sull'Apple M1**: è più veloce della macchina della demo e sposta la prima soglia oltre 60×, mentre in produzione cade intorno a 50×.

## Conseguenze

- Se il dataset crescesse, prima gli interventi più economici, nell'ordine indicato dalla macchina della demo: ridurre il tempo di avvio (pulizia con operazioni vettoriali, oppure avvio da un file già pulito, che non cambia il prompt), poi liberare il dataframe grezzo, che oggi resta in memoria accanto a quello pulito (102 MB accanto agli 83 MB del pulito a 100×). Un motore SQL solo se una soglia restasse superata: SQLite per la memoria, DuckDB per i tempi.
- `duckdb` è solo in `requirements-dev.txt` e `sqlite3` è nella libreria standard: nell'immagine di produzione non entra nessuna dipendenza nuova.
- Limiti della misura: cinque domande; dati sintetici; una corsa per macchina (il picco di memoria varia tra le corse). La macchina della demo è misurata con un Job e non dentro lo Space: stessa CPU, stessi limiti e stessa immagine di base, ma non lo stesso container.

## Numeri

- Corsa di riferimento, sulla macchina della demo: [corsa del 18 novembre](../../data_agent/scripts/risultati_benchmark/corsa-20261118-0943.md). Sull'Apple M1, con SQLite: [corsa dell'11 novembre](../../data_agent/scripts/risultati_benchmark/corsa-20261111-1318.md). Corse del 5 novembre, con pandas e DuckDB: [completa](../../data_agent/scripts/risultati_benchmark/corsa-20261105-1051.md) e [preliminare](../../data_agent/scripts/risultati_benchmark/corsa-20261105-1042.md).
- Per rifarla: `deploy/benchmark_job.sh --prova` (1×, controlla il Job), poi `deploy/benchmark_job.sh` (completa, circa 35 minuti); i risultati arrivano nel bucket della demo, cartella `benchmark/`.

## Dove nel codice

- `data_agent/scripts/dataset_sintetico.py`, `data_agent/scripts/benchmark.py` (domande in pandas, DuckDB e SQLite; indici in `INDICI_SQLITE`; macchina e limiti del container), `data_agent/scripts/benchmark_riepilogo.py` (regola ed esito).
- `deploy/benchmark_job.sh`: la corsa su un Job di Hugging Face con la macchina della demo.
- `data_agent/main.py`: caricamento all'avvio, il punto che cambierebbe per primo.
