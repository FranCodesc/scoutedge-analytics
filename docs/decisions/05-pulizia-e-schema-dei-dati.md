# Pulizia, schema e qualità dei dati

**Data:** dal 2026-10-01 al 2026-11-12 (commit `3ab8f84`, `b43a56b`, `0d9e15e`, `ae98d72`, `26b00aa`)

## Contesto

Il CSV grezzo (`data/scouting_data.csv`, 1208 righe) ha grafie diverse per club e nazionalità, duplicati, importi e date in formati misti, valori fisicamente impossibili, nomi in kanji e nomi con titoli e qualifiche. Il data agent risponde con codice generato dal modello: se i dati non sono puliti e controllati prima, ogni risposta eredita gli stessi errori. Un controllo bloccante, però, dice solo se i dati passano o no: non mostra cosa cambia a ogni passo della pulizia né da un caricamento all'altro, e un limite senza motivazione non si può discutere né correggere.

## Decisione

- **Pulizia deterministica all'avvio** (`clean_scouting_data` in `cleaning.py`), secondo la procedura della sezione 6 del manuale: elenchi espliciti (25 club, titoli, traslitterazione dei nomi giapponesi), formati di data espliciti, valori impossibili corretti e non eliminati, deduplica dopo le normalizzazioni e prima dell'imputazione, mediana per ruolo e stagione, colonne dei portieri lasciate vuote per gli altri ruoli. Le osservazioni dello stesso giocatore nello stesso giorno restano, ma vengono contate e segnalate.
- **`cleaning_report`**: i conteggi di ogni correzione si registrano mentre la correzione viene applicata (è l'unico momento in cui si conoscono il valore prima e quello dopo) e arrivano nel prompt del data agent, che li usa per rispondere sulle correzioni.
- **Schema dichiarato in Python** (`schema.py`), controllato all'avvio: sul CSV grezzo le colonne attese, sul dataframe pulito tipi, intervalli di plausibilità, domini chiusi, valori mancanti ammessi solo nelle colonne dei portieri, nessuna riga identica e relazioni tra colonne (minuti, cartellini e porte inviolate rispetto alle partite giocate, data dentro la stagione, età all'osservazione, attributi fissi per lo stesso `player_id`, nomi senza titoli né caratteri non latini).
- **Tutte le violazioni in un solo errore**: un `SchemaError` le elenca tutte, ciascuna con un esempio (`player_id` e valore), e il servizio non parte: meglio un avvio fallito che risposte su dati sbagliati.
- **Ogni limite con motivo e fonte.** In `schema.py` un limite è un `Limite(minimo, massimo, motivo, fonte)`, e la fonte è di quattro tipi: *definizione* (scala, percentuale, conteggio, dal manuale), *regola del gioco*, *ordine di grandezza*, *pulizia* (il limite prende ciò che la pulizia non ha corretto). "Ordine di grandezza" vuol dire un valore reale non verificato con una fonte citabile: si dichiara come tale invece di dare un numero preciso. Le regole sono 31 (tabella sotto).
- **Rapporto di qualità a ogni avvio** (`qualita.py`), dopo lo schema: impronta del CSV (SHA-256 con gli a capo normalizzati), righe dopo ogni passo della pulizia e valori cambiati per colonna, profilo del grezzo e del pulito (per colonna e per stagione), limiti con il valore osservato e il margine, confronto con un profilo di riferimento committato (`qualita_riferimento.json`, solo statistiche, nessuna riga del dataset). Nel log va un riepilogo (righe `Qualità dei dati — …`), il JSON completo nella cartella dei rapporti, che tiene gli ultimi 10. Gli scostamenti oltre le tolleranze diventano **avvisi, che non bloccano l'avvio**: a bloccare resta lo schema. Il riferimento si aggiorna solo a mano, con `scripts/aggiorna_riferimento_qualita.py`.

### Limiti per fonte

| Fonte | Regole | Esempi: limite (osservato sui dati reali) |
|---|---|---|
| Definizione | 17: identificatore positivo, scala del rating, 4 percentuali, giorni di infortunio, 10 conteggi e somme di probabilità | `scout_rating` 1–99 (25–99); percentuali 0–100 (`pass_accuracy_pct` 55,7–99,0); `injury_days_last_season` 0–365 (0–88). I conteggi non hanno un massimo: nessuna fonte dà un tetto, e i valori alti li segnala il rapporto |
| Regola del gioco | 4 relazioni con le partite giocate | al massimo 120 minuti (90 più i supplementari; osservato 93,0), 2 gialli (0,5), 1 rosso (0,06) e 1 porta inviolata (0,43) per partita |
| Ordine di grandezza, a volte con una seconda fonte | 10 | `height_cm` 150–220 (163–198; anche pulizia), `weight_kg` 50–120 (64,1–99,1), `sprint_speed_kmh` 20–40 (24,2–37,5; anche pulizia), `distance_covered_km` 5–15 (7,57–12,98), `market_value_eur` da 1 a 200 milioni (da 1,6 a 19,1 milioni), `matches_played` 0–80 (1–38), gialli 0–30 (0–12) e rossi 0–5 (0–1) in una stagione, età all'osservazione 15–45 anni (17,2–37,3), stagione dal 1° luglio al 30 giugno (osservazioni ad almeno 45 giorni dall'inizio e 41 dalla fine) |

### Cosa è cambiato con i limiti motivati (2026-11-12)

- **Altezza.** La pulizia divideva per 10 le altezze sopra 210 e lo schema ammetteva al massimo 210: un giocatore vero di 211 cm sarebbe diventato 21,1 cm e avrebbe fermato il servizio. Ora si divide solo un'altezza di 4 cifre (`>= 1000`: in centimetri un'altezza ne ha al massimo 3) e il massimo dello schema è 220. Sui dati reali le correzioni restano 12.
- **Contratto già scaduto all'osservazione.** Lo schema lo bloccava, ma la FAQ della sezione 8 del manuale lo considera un segnale utile (un giocatore svincolato o in scadenza), non un dato sporco: è uscito dallo schema e il rapporto lo conta come indicatore (0 righe sui dati attuali).
- **Partite** fino a 80 invece di 60 (con coppe e nazionale i più impiegati arrivano intorno a 60-70); **stagione** dal 1° luglio invece che dal 1° agosto (anno sportivo dei contratti, che scadono il 30 giugno).
- **Regole nuove**: cartellini gialli, rossi e porte inviolate rispetto alle partite giocate; età all'osservazione tra 15 e 45 anni.

### Tolleranze degli avvisi

| Controllo | Avviso se |
|---|---|
| Righe e giocatori | calano, oppure crescono oltre il 50% (righe) o il 20% (giocatori) |
| Righe per stagione | calano |
| Valori mancanti nel CSV grezzo | superano quelli del riferimento di oltre 5 punti percentuali |
| `nationality` e `scout_name`, testo libero che lo schema non chiude | compaiono valori nuovi o spariscono valori del riferimento |
| Minimi e massimi delle 24 colonne con un intervallo (`player_id` escluso) | escono dal riferimento allargato del 20% dell'ampiezza |

Le tolleranze sono calibrate togliendo dal riferimento una stagione alla volta e trattando il dataset completo come un caricamento nuovo: con il 20% gli avvisi su minimi e massimi sono 4, 0 e 1 (6, 2 e 2 con il 10%; 14, 8 e 4 con lo 0%), con tutti i controlli 4, 1 e 2. Una stagione nuova vale circa il 34% di righe in più, la rosa è stabile (130 giocatori in ogni stagione) e tra le stagioni la quota di mancanti varia al massimo di 2,2 punti.

## Alternative scartate

- **Lasciare la pulizia al codice generato dal modello a ogni domanda**: risultati diversi da una domanda all'altra e nessun conteggio affidabile delle correzioni.
- **La grafia più frequente come nome del club**: un elenco esplicito dà un risultato riproducibile e blocca subito un club inatteso.
- **Riconoscimento automatico delle date**: può scambiare giorno e mese (03/04/2025).
- **Una libreria di validazione per dataframe (per esempio `pandera`)**: una dipendenza in più nell'immagine di produzione per circa 200 righe di controlli, mentre per le correzioni si è scelto di non aggiungerne.
- **`pydantic`**, già presente perché lo usa FastAPI: valida un oggetto alla volta, mentre gran parte dei controlli riguarda il dataframe intero (righe duplicate, attributi uguali per tutte le righe di un giocatore, numero di club, date dentro la stagione). Con pandas sono maschere su tutte le righe in un colpo solo.
- **Fermarsi alla prima violazione**: costringerebbe a correggere, rilanciare e scoprire l'errore successivo.
- **Avvisi bloccanti**: un dato vero ma insolito (un giocatore più alto, una stagione in più) fermerebbe il servizio. Bloccano le violazioni dello schema; il resto si segnala.
- **Riferimento aggiornato da solo a ogni avvio**: confronterebbe sempre i dati con sé stessi. Si aggiorna a mano, dopo un'anteprima degli avvisi, e si committa.
- **Tolleranze più strette**: con il 10% o lo 0% dell'ampiezza gli avvisi su dati buoni salgono (6, 2 e 2 oppure 14, 8 e 4, contro 4, 0 e 1).
- **Una rotta per leggere il rapporto**: il data agent non è raggiungibile dall'esterno e una rotta nel back end cambierebbe il contratto delle API; il riepilogo è nel log e il JSON nella cartella dei rapporti.

## Conseguenze

- Un CSV che non rispetta lo schema blocca l'avvio del data agent: è voluto.
- I limiti sono di plausibilità: abbastanza larghi da non fermare un dato vero ma insolito, abbastanza stretti da prendere gli errori che la pulizia corregge (percentuali oltre 100, altezze con uno zero in più, velocità negative). Dieci regole poggiano su un ordine di grandezza non verificato con una fonte citabile, ed è dichiarato; i margini sui dati reali sono nel rapporto.
- Gli avvisi sono informativi: qualche avviso su dati buoni è atteso (fino a 4 su minimi e massimi nella calibrazione).
- Le stagioni ammesse sono scritte in `schema.py` e nel prompt dell'orchestratore: se cambia il dataset vanno aggiornate in entrambi, e il riferimento va rigenerato.
- La pulizia è la parte più lunga dell'avvio: circa il 90% del tempo nel benchmark ([risultati](../../data_agent/scripts/risultati_benchmark/corsa-20261111-1318.md)). Il rapporto aggiunge circa 21 ms in locale.
- Nel container i rapporti vanno in `/tmp/quality_reports` e si perdono a ogni riavvio; resta il riepilogo nei log ([DEPLOY.md](../DEPLOY.md#architettura-del-container)).
- `scripts/dataset_sintetico.py` ripete alcuni limiti dello schema, compatibili con quelli nuovi: non è stato modificato perché i risultati del benchmark dipendono da lui.

## Numeri

- 1208 righe, poi 1185; 23 duplicati (13 identici nel file grezzo, 10 emersi dopo le normalizzazioni); club da 74 a 25 grafie; nazionalità da 45 a 24; 5 casi di osservazioni nello stesso giorno; titoli tolti dai nomi di 12 giocatori (113 righe). Sono verificati da `data_agent/tests/test_dataset_reale.py` e riportati nei [Valori attesi](../TEST.md#valori-attesi).
- Rapporto sul CSV del repository: righe 1208 → 1208 → 1185 → 1185 (lettura, normalizzazioni, deduplica, imputazione); valori cambiati, per esempio, in `player_name` 188, `observation_date` 181, `club` 151, `market_value_eur` 120, `height_cm` 12; 0 contratti scaduti all'osservazione; 0 avvisi.
- 178 test del data agent, di cui 24 sul rapporto (`test_qualita.py`). L'impronta della pulizia (dataframe, tipi, `cleaning_report` e testo passato al modello) è identica prima e dopo i limiti motivati. Proprio per questo il testo passato al modello descriveva ancora la soglia precedente dell'altezza (`superiori a 210`): la frase è stata corretta il 16 novembre, con un test che la controlla, e la valutazione con il modello reale è stata rifatta (79/80 valori, 80/80 strumenti; [TEST.md](../TEST.md#valutazione-automatica)). Un dataset sintetico a 10× passa pulizia e schema nuovi, con 120 altezze corrette e i 2 avvisi attesi (righe e giocatori +900%). Dettagli in [TEST.md](../TEST.md#rapporto-di-qualità-dei-dati).

## Dove nel codice

- `data_agent/cleaning.py`, `data_agent/schema.py` (`Limite`, `FONTI`, `LIMITI`), `data_agent/qualita.py` (rapporto e tolleranze), `data_agent/qualita_riferimento.json`, `data_agent/main.py` (avvio: lettura, controllo delle colonne, pulizia, schema, rapporto).
- `data_agent/scripts/aggiorna_riferimento_qualita.py`: anteprima, o `--conferma` per riscrivere il riferimento.
- `data_agent/tests/test_cleaning.py`, `data_agent/tests/test_schema.py`, `data_agent/tests/test_qualita.py`, `data_agent/tests/test_dataset_reale.py`.
- `data/platform_handbook.md`: la procedura di pulizia nella sezione 6, la FAQ sui contratti scaduti nella sezione 8.