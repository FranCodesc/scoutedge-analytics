# Domande riscritte in forma autonoma per il data agent

**Data:** dal 2026-10-06 al 2026-10-18 (commit `305290d`, `4efea08`, `8e6b33f`, `b6d21fd`)

## Contesto

Il data agent non vede la conversazione: `POST /analyze` riceve solo una domanda e ogni richiesta costruisce un agente nuovo. L'utente invece scrive "e nella stagione precedente?" o "e per i portieri?". Qualcuno deve trasformare queste domande in domande complete.

## Decisione

Lo fa l'orchestratore: nel parametro `question` di `analyze_data` scrive una domanda autonoma. Le regole stanno nella sezione "COME CHIAMARE analyze_data" del system prompt (testo e motivi in [DESIGN_ORCHESTRATORE.md](../DESIGN_ORCHESTRATORE.md), sezione 5):

- i riferimenti alla conversazione diventano valori espliciti (`player_id`, ruolo, club, stagione, metrica);
- le espressioni temporali della domanda corrente ("attuale", "ultima stagione") si conservano parola per parola;
- quelle delle domande precedenti non si copiano mai: un riferimento relativo diventa il periodo esplicito ("nella stagione 2024/25");
- il prompt dichiara le stagioni del dataset e quale è l'ultima;
- gli esempi usano segnaposto (`<metrica>`, `<ruolo>`, `<stagione>`).

## Come ci si è arrivati

- **2026-10-06** (`305290d`): il data agent distingue un periodo da uno stato proprio da quelle parole: 65.11 su 405 per l'ultima stagione, 65.21 se si prende l'ultima osservazione di ogni giocatore ([pagina 3](03-regole-del-prompt-del-data-agent.md)). Riformularle reintrodurrebbe l'errore.
- **2026-10-09** (`4efea08`): in una prova il modello ha scritto "nell'ultima stagione precedente (2024/25)", trascinando "ultima stagione" dalla domanda prima; il numero era giusto solo grazie all'anno esplicito. Da qui la regola sulle domande precedenti.
- **2026-10-12** (`8e6b33f`): con una conversazione vera attraverso la route, la seconda domanda è fallita 4 volte su 4. La prima risposta ("65.11 su 405") non nomina la stagione; il modello supponeva che l'ultima fosse la 2023/24 e chiedeva la 2022/23, che non esiste. La prova precedente passava solo perché la history era scritta a mano e conteneva la stagione. Da qui le stagioni nel prompt.
- **2026-10-18** (`b6d21fd`): per "i giocatori 33 e 70" l'orchestratore fa due richieste e scrive "giocatore con ID 70", una forma che la regola del data agent sulle osservazioni nello stesso giorno non riconosceva: 19 risposte corrette su 33. La regola ora elenca le forme con cui si indica un giocatore; dopo la correzione, 30 su 30 ([dettaglio](../TEST.md#difetto-trovato-e-corretto)). Un componente si prova anche con le domande scritte da chi lo chiama.

## Alternative scartate

- **Passare la conversazione al data agent.** Dovrebbe risolvere i riferimenti da solo, con un prompt già lungo e più token a ogni analisi, e smetterebbe di essere senza stato: oggi ogni domanda si prova da sola con `regression_check.py`.
- **Normalizzare le espressioni temporali nell'orchestratore** (per esempio "attuale" riscritto come una stagione): trasformerebbe uno stato in un periodo o viceversa, cioè l'errore tra 65.21 e 65.11.
- **Lasciare che il modello deduca le stagioni dalla conversazione**: fallito 4 volte su 4 (sopra).

## Conseguenze

- La domanda riscritta compare nel log del back end: è un limite dichiarato della demo online.
- Le stagioni sono scritte in due posti, nel prompt dell'orchestratore e in `data_agent/schema.py`: se cambia il dataset vanno aggiornate entrambe.
- Le conversazioni si verificano con conversazioni vere (valutazione automatica), non con history scritte a mano.

## Numeri

- 65.11 su 405, poi 66.18 su 400 (conversazione della demo): [Valori attesi](../TEST.md#valori-attesi).
- Versioni del prompt e prove: [DESIGN_ORCHESTRATORE.md](../DESIGN_ORCHESTRATORE.md), "Storico versioni".
- Valutazione automatica del 2026-11-04: 30 turni corretti su 30 nelle tre conversazioni ([corsa](../../back%20end/eval/risultati/corsa-20261104-1008.md)).

## Dove nel codice

- `back end/src/agent/systemPrompt.js`: sezione "COME CHIAMARE analyze_data".
- `back end/src/agent/tools.js`: descrizione del parametro `question`.
- `data_agent/agent.py`: forme con cui si indica un giocatore.
- `back end/eval/domande.json` (domande `conversazione_*`) e `data_agent/scripts/regression_check.py` (caso "giocatore con ID 70").
