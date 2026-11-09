# Test e valutazione

**Data:** dal 2026-11-03 al 2026-11-05 (commit `ae98d72`, `7fcb721`, `89d4649`, `4de32fa`)

## Contesto

Fino al 2026-11-02 le verifiche erano script che chiamano il modello reale (`data_agent/scripts/regression_check.py` e la seconda parte di `back end/scripts/testApi.js`, da giudicare a mano). Sono lente, costano token e il loro esito varia da un giro all'altro: non bastano per controllare ogni modifica, e non dicono se una modifica al prompt ha migliorato o peggiorato le risposte.

## Decisione

- **Due livelli separati.** I test unitari controllano il codice deterministico, senza modello e senza token; la valutazione automatica misura le risposte del modello reale.
- **Test unitari nelle tre parti**, con gli strumenti di ciascun ambiente: `pytest` per il data agent (pulizia, schema, API con agente e modello simulati da `MagicMock`, concorrenza, pulizia dei grafici), `node:test` per il back end (incluso in Node, nessuna dipendenza), Vitest per il front end.
- **`createApp` con dipendenze iniettabili.** `app.js` costruisce l'app senza avviarla; orchestratore, recupero dei grafici e store delle sessioni hanno come valore predefinito quelli veri, e i test passano versioni simulate. La lettura delle variabili d'ambiente e l'avvio stanno in `index.js`.
- **Valutazione con il modello reale** (`npm run eval`): 13 domande con le risposte attese prese dai valori di `docs/TEST.md`, ripetute N volte con una sessione nuova a ogni ripetizione. Il punteggio è deterministico: i numeri attesi si cercano in tutte le grafie dello stesso valore, senza tolleranza, insieme ai testi attesi, ai valori vietati e al grafico; gli strumenti usati si confrontano come insieme. Valori e strumenti si contano a parte. La regola è scritta in `eval/domande.json` prima di lanciare le corse, e ogni corsa si salva (JSON con tutte le risposte e riepilogo in Markdown).
- **Integrazione continua sì, deploy automatico no.** GitHub Actions esegue le tre suite a ogni push e pull request su `main`, in tre job paralleli, con permessi di sola lettura e nessun secret. Il caricamento sullo Space resta manuale (`deploy/upload_space.sh`).

## Alternative scartate

- **Solo gli script con il modello reale**: restano, ma per i casi in cui serve il modello; per il resto sono lenti, costosi e non deterministici.
- **Sostituire i moduli importati nei test**, invece di iniettare le dipendenze: più fragile, legato a come sono scritti gli import, mentre l'iniezione lascia il codice di produzione identico.
- **La valutazione nella CI**: costa token a ogni push e richiederebbe la chiave OpenAI tra i secret di un repo pubblico.
- **Deploy automatico a ogni push**: richiederebbe un token di Hugging Face con permesso di scrittura tra i secret, e metterebbe online anche un commit non ancora controllato, su una demo pubblica. Il flusso resta: commit, controllo, push, CI verde, caricamento.

## Conseguenze

- I test unitari non dicono nulla sul comportamento del modello: è il compito della valutazione, che si lancia a mano dopo ogni modifica a prompt o strumenti.
- La valutazione copre 13 domande e non gira nella CI.
- Un caricamento manuale si può dimenticare: prima di ogni invio si controlla che lo Space corrisponda all'ultimo commit.

## Numeri

- 136 test del data agent, 225 del back end, 76 del front end; nella CI circa un minuto per le tre suite.
- La prima corsa completa (N=5, 2026-11-04) ha dato 78 turni su 80 con i valori corretti: in una risposta sui tre difensori centrali compariva solo Pereira, il limite intermittente già noto; dell'altro turno sbagliato non resta traccia. Non è stata salvata nel repo.
- Le tre corse salvate: 80/80 valori e 80/80 strumenti con N=5 il 4 novembre ([corsa](../../back%20end/eval/risultati/corsa-20261104-1008.md)); 20/20 sulla domanda dei difensori centrali con N=20 il 4 novembre ([corsa](../../back%20end/eval/risultati/corsa-20261104-1030.md)); 79/80 valori e 80/80 strumenti con N=5 il 9 novembre, da un clone pulito ([corsa](../../back%20end/eval/risultati/corsa-20261109-1046.md)), con l'unico errore sulla domanda dei difensori centrali (compare solo Pereira). Su quella domanda le risposte corrette sono 29 su 30 nelle corse salvate, più almeno un errore nella prima corsa completa: l'errore resta un limite dichiarato.
- La valutazione confronta l'insieme degli strumenti, non il numero di chiamate: nel log del back end le chiamate doppie ad `analyze_data` sono 0 su 80 turni nella corsa del 9 novembre.

## Dove nel codice

- `back end/src/app.js` e `back end/src/index.js`; `back end/test/`, `data_agent/tests/`, `front end/test/`.
- `back end/eval/`: `domande.json` (domande e regola), `lib.js` (punteggio), `run.js` (corse), `risultati/`.
- `.github/workflows/test.yml`.