# Regole del prompt del data agent

**Data:** dal 2026-10-02 al 2026-10-18 (commit `b43a56b`, `305290d`, `90da3a8`, `81d3c8f`, `3852567`, `b6d21fd`)

## Contesto

Il data agent risponde scrivendo codice pandas che esegue con lo strumento `python_repl`. Il suo system prompt è cresciuto per correggere comportamenti sbagliati osservati nelle prove: ogni sezione ha un motivo, e l'ordine e la formulazione contano.

## Decisione

Le regole che il modello deve seguire sempre sono scritte come **procedure con codice esatto da eseguire e un ordine fisso della risposta**, non come regole condizionali ("se ... allora ..."), che il modello non esegue in modo affidabile. Gli esempi di codice usano segnaposto (`<id>`): un valore reale verrebbe copiato. Le regole principali:

- **Periodo o stato attuale.** Se la domanda indica un periodo si usano tutte le osservazioni del periodo; se chiede lo stato attuale si prende l'ultima riga di ogni giocatore con un ordinamento stabile (`kind='stable'`: a parità di data vince la riga registrata per ultima), anche per massimi, minimi e classifiche. Prima delle correzioni del 2026-10-06 lo scout_rating medio dell'ultima stagione veniva calcolato sulle ultime osservazioni dei giocatori (65.21 invece di 65.11 su 405) e "il valore attuale più alto" restituiva il massimo storico.
- **"Osservazione più recente".** Il modello a volte la leggeva come la sola data più recente del dataset (poche righe, un solo difensore) invece che come l'ultima osservazione di ogni giocatore. Le misure oscillano tra un giro e l'altro: circa 2 errori su 10 il 2026-10-09 (`81d3c8f`), risposte corrette da 1 su 5 a circa 7 su 10 nelle prove del 2026-10-15 ([docs/TEST.md](../TEST.md#limiti-noti-del-data-agent)). La definizione esplicita aggiunta al prompt non ha dato un miglioramento misurabile (6/8 con la frase, 8/8 senza: campioni troppo piccoli per distinguere), ma è rimasta perché è la definizione corretta. Con "attuale" la domanda è affidabile (10 su 10 nelle prove; 20/20 nella valutazione automatica del 2026-11-04), quindi la demo usa questa formulazione e l'altra resta un limite dichiarato.
- **Osservazioni nello stesso giorno.** Per i giocatori indicati il codice stampa le righe della loro data più recente e l'elenco `GIOCATORI DA SEGNALARE`; il modello scrive prima il valore attuale e poi, solo per quegli id, la segnalazione. Dal 2026-10-09 la decisione spetta al codice e non al modello: senza ordine fisso il modello ometteva il valore, senza limite elencava la storia del giocatore, e con la regola "se compare più di una riga" segnalava anche il giocatore 33, che in quella data ha una riga sola. Le righe del controllo stanno nello stesso sottoinsieme (serie con indici diversi davano `ValueError` e il modello riscriveva il controllo a modo suo), l'elenco usa `.tolist()` (con numpy 2 si stamperebbe `[np.int64(70)]`) e non va riportato nella risposta.
- **Valori categoriali e codici di ruolo.** Prima di filtrare si controllano i valori con `.unique()`: il modello cercava `'Goalkeeper'` invece di `'GK'` e concludeva che i portieri non esistevano. Dal 2026-10-09 il prompt contiene anche il significato dei codici di `position` e i gruppi di ruoli: il modello vedeva `GK` ma non sapeva che significa "portiere".
- **Riepilogo delle correzioni.** I numeri della pulizia non si ricostruiscono dal dataframe già pulito: arrivano nel prompt dal `cleaning_report` e il modello deve usare solo quelli.

## Una correzione che non riguardava il prompt

L'errore sul valore di mercato attuale più alto (15.000.000 o 5.000.000 invece di 18.680.000) sembrava un difetto della regola sullo stato attuale. La diagnosi ha mostrato che la rappresentazione abbreviata di pandas nascondeva tra i "..." una parte delle 35 colonne, tra cui `market_value_eur`, e il modello inventava il valore. La correzione è nello strumento: stampa con tutte le colonne, un limite di 6000 caratteri e una nota fissa quando l'output viene troncato, perché il modello non riempia i vuoti.

## Alternative scartate

- **Un dataframe precalcolato con lo stato attuale (`df_attuale`).** Provato e tolto il 2026-10-09 per le regressioni che causava: il controllo delle osservazioni nello stesso giorno girava sul dataframe sbagliato e le domande su un periodo venivano calcolate sullo stato attuale.
- **Regole condizionali lasciate al modello**: vedi la segnalazione del giocatore 33.
- **Una regola sul formato degli importi**: provata e tolta perché peggiorava risposte che non riguardavano gli importi ([docs/TEST.md](../TEST.md#limiti-noti-del-data-agent)).

## Conseguenze

- Il prompt è lungo e ogni modifica si verifica con la batteria di regressione completa, anche quando cambia solo la forma.
- Limiti accettati: "osservazione più recente" variabile; con più giocatori nella stessa domanda il controllo è meno affidabile (0 corrette su 3 il 2026-10-09; passando dall'orchestratore la domanda viene divisa in richieste separate); codici di ruolo non dichiarati nelle risposte. Gli altri limiti sono in [docs/TEST.md](../TEST.md#limiti-noti-del-data-agent).

## Numeri

- 65.11 su 405, 65.21 e 18.680.000: [Valori attesi](../TEST.md#valori-attesi).
- 2 su 10, 6/8 e 8/8, 0 su 3: prove del 2026-10-09, prima riportate nei commenti del codice.
- Batteria di regressione del data agent: 28 su 28 nella verifica da clone pulito del 2026-10-19 ([docs/TEST.md](../TEST.md#verifica-da-clone-pulito-19-ottobre-2026)).

## Dove nel codice

- `data_agent/agent.py`: `build_data_agent` (testo del prompt) e `make_python_tool` (stampa completa, `MAX_TOOL_OUTPUT`).
- `data_agent/scripts/regression_check.py` e `data_agent/scripts/traccia_agente.py`: prove con il modello reale.
