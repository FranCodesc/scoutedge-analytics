"""Agente di analisi dati di ScoutEdge Analytics (ReAct con un solo tool, `python_repl`).

Il modulo costruisce l'agente che risponde alle domande sul dataset di scouting
generando ed eseguendo codice pandas. Si compone di tre parti:

1. CHARTS_DIR: la cartella (percorso assoluto) in cui vengono salvati i grafici PNG.
2. make_python_tool(df): crea il tool `python_repl`, un piccolo interprete che esegue il
   codice scritto dal modello su una copia del dataframe e salva in automatico i grafici.
3. build_data_agent(df, llm, cleaning_summary): assembla l'agente con il suo system prompt,
   che contiene le regole di analisi e il riepilogo delle correzioni applicate ai dati.

main.py chiama build_data_agent a ogni richiesta: ogni domanda ha quindi uno stato
pulito, senza variabili o filtri lasciati da richieste precedenti.

Limite di sicurezza noto: il codice generato dal modello viene eseguito con exec/eval
nel processo del servizio, senza sandbox. È accettabile solo in un contesto locale e
didattico (vedi la sezione sulla sicurezza nella documentazione del progetto).
"""

import io
import contextlib
import ast
import uuid
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend non interattivo: necessario in un processo server, senza display
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from langchain_core.tools import tool
from langchain.agents import create_agent


# Cartella dei grafici: percorso assoluto basato sulla posizione di questo file e non
# sulla cartella da cui viene avviato uvicorn. Con un percorso relativo, avviare il
# servizio da un'altra cartella farebbe salvare i PNG (e poi cercarli) nel posto sbagliato.
CHARTS_DIR = Path(__file__).resolve().parent / "charts"
CHARTS_DIR.mkdir(exist_ok=True) # crea cartella se manca


def make_python_tool(df):
    """Costruisce il tool 'python_repl' per un dataframe specifico.

    Il namespace (con una COPIA di df) viene creato qui: ogni chiamata a questa funzione
    produce quindi uno stato nuovo. build_data_agent la richiama a ogni richiesta, così le
    variabili persistono tra le tool-call della stessa richiesta ma non passano alla successiva.

    Il tool è un REPL "alla Jupyter": esegue il codice scritto dal modello, mostra il valore
    dell'ultima espressione e, se il codice ha creato un grafico, lo salva in CHARTS_DIR.
    Restituisce la funzione-tool (decorata con @tool) da passare a create_agent.
    """

    # Un solo dizionario fa da globals e da locals di exec/eval. Con due dizionari separati
    # le funzioni, le lambda e le list comprehension scritte dal modello (che hanno un proprio
    # ambito e cercano i nomi nei globals) non vedrebbero 'df' e 'pd': NameError.
    namespace = {"df": df.copy(), "pd": pd, "plt": plt, "sns": sns}

    @tool
    def python_repl(code: str) -> str:
        """Esegue codice Python per analizzare il dataframe (disponibile come variabile 'df').
        Disponibili anche 'pd', 'plt' (matplotlib.pyplot) e 'sns' (seaborn) per creare grafici:
        se il codice genera una figura matplotlib, viene salvata automaticamente come PNG
        (non serve chiamare plt.savefig() né plt.show()).
        Le variabili definite in una chiamata restano disponibili nelle chiamate successive
        (come in un notebook Jupyter).
        Si comporta come un REPL: se l'ultima riga è un'espressione, il suo valore viene mostrato
        automaticamente, altrimenti usa print()."""
        output = io.StringIO()
        chart_note = ""
        try:
            # Il codice viene analizzato come albero sintattico (AST) invece di darlo
            # direttamente a exec. Serve per separare l'ultima istruzione dalle altre: se è
            # un'espressione (es. `df.shape`) se ne valuta e mostra il valore come fa un REPL,
            # altrimenti il modello dovrebbe scrivere print() ogni volta. Se il codice è vuoto
            # `tree.body` è vuoto: il segnaposto [None] evita l'errore di spacchettamento.
            tree = ast.parse(code)
            *body, last = tree.body if tree.body else [None]

            # Tutto ciò che il codice stampa viene catturato in `output` invece di finire sul
            # terminale del server: è il testo che il tool restituisce al modello.
            with contextlib.redirect_stdout(output):
                if body:
                    exec(compile(ast.Module(body=body, type_ignores=[]), "<code>", "exec"), namespace)
                if last is not None:
                    if isinstance(last, ast.Expr):
                        result = eval(compile(ast.Expression(last.value), "<code>", "eval"), namespace)
                        if result is not None:
                            print(repr(result))
                    else:
                        exec(compile(ast.Module(body=[last], type_ignores=[]), "<code>", "exec"), namespace)

                if plt.get_fignums():
                    # Solo il nome del file: nella nota per il modello non deve comparire
                    # nessun percorso del disco (fuga di informazioni e romperebbe l'URL).
                    filename = f"chart_{uuid.uuid4().hex[:8]}.png"
                    plt.savefig(CHARTS_DIR / filename, bbox_inches="tight")
                    plt.close("all")
                    chart_note = f"\n[Grafico salvato correttamente: {filename}]"

        # L'errore non interrompe il servizio: viene restituito al modello come testo, così può
        # leggerlo e correggere il codice al giro successivo (tipico del ciclo ReAct di auto-correzione).
        # Le figure rimaste aperte si chiudono per non contaminare la richiesta successiva.
        except Exception as e:
            plt.close("all")
            return f"Errore nell'esecuzione: {e}"
        return (output.getvalue() or "Codice eseguito senza output.") + chart_note
    return python_repl


def build_data_agent(df, llm, cleaning_summary):
    """Costruisce un agente ReAct per l'analisi del dataframe 'df'.

    Parametri:
        df: dataframe già pulito (output di clean_scouting_data).
        llm: modello di linguaggio (ChatOpenAI) usato dall'agente.
        cleaning_summary: testo (da format_cleaning_report) che riassume le correzioni
            applicate ai dati; viene inserito nel system prompt.

    Va richiamata a ogni richiesta (non una volta sola all'avvio): lo stato del
    tool è isolato per richiesta.
    Restituisce l'agente pronto per .invoke().
    """

    python_tool = make_python_tool(df)

    # System prompt: ogni sezione è nata per correggere un comportamento sbagliato osservato
    # nei test, quindi l'ordine e la formulazione contano. Principio emerso dal lavoro sul
    # controllo D8: le regole condizionali ("se... allora...") il modello non le esegue in
    # modo affidabile, mentre le procedure con codice esatto da lanciare sempre e un ordine
    # fisso della risposta sì. Per questo gli esempi di codice usano segnaposto espliciti
    # (<...>) e non valori reali, che il modello potrebbe copiare.
    #
    # Sezioni, in ordine:
    # 1. Colonne di 'df': evita che il modello inventi nomi di colonne.
    # 2. Struttura dei dati: ogni riga è un'osservazione nel tempo, quindi un giocatore compare
    #    più volte e metriche come valore di mercato e rating cambiano.
    # 3. Chiave del giocatore: sempre 'player_id', mai 'player_name' (omonimie).
    # 4. Periodo oppure stato "attuale". Prima si distingue: se la domanda indica un periodo
    #    (stagione, anno, mese, intervallo di date), si filtra df sul periodo e si usano TUTTE le
    #    sue osservazioni (regressione D7: "scout_rating medio nell'ultima stagione" veniva
    #    calcolato sulle ultime osservazioni dei giocatori, 65.21, invece che su tutte le 405
    #    della stagione, 65.11). Se invece si chiede lo stato attuale senza periodo, vale la
    #    procedura esatta con ordinamento stabile (kind='stable'), anche per massimi, minimi e
    #    classifiche su tutti i giocatori (bug D7: "valore attuale più alto nel dataset"
    #    restituiva il massimo storico). Il criterio è deterministico: a parità di data vince
    #    la riga registrata per ultima.
    # 5. Controllo D8: per giocatori specifici stampa tutte le osservazioni della data più
    #    recente e segnala i casi con più righe, con ordine fisso (prima il valore attuale,
    #    poi la segnalazione). Senza l'ordine fisso il modello a volte ometteva il valore.
    #    La segnalazione si limita alle righe stampate dal controllo (tutte della stessa data):
    #    in una prova su quattro della regressione D7 elencava l'intera storia del giocatore.
    # 6. Anti-allucinazione: se un'informazione non è tra le colonne, lo dice invece di
    #    rispondere con conoscenza generale.
    # 7. Valori categoriali: controlla con .unique() prima di filtrare (bug osservato:
    #    cercava 'Goalkeeper' invece di 'GK' e concludeva che i portieri non esistevano).
    # 8. Anti-link: niente link o percorsi dell'immagine nel testo; il grafico viene
    #    consegnato a parte da main.py tramite chart_url.
    # 9. Riepilogo delle correzioni (D3): i numeri del cleaning non si possono ricostruire
    #    dal dataframe già pulito, quindi stanno nel prompt, con la regola di usare solo quelli
    #    e di dichiararne la base di calcolo.
    # Le graffe di cleaning_summary e delle colonne sono sostituite da Python (f-string).
    system_prompt_text = f"""Colonne disponibili nel dataframe 'df': {list(df.columns)}

Nota importante sulla struttura dei dati: ogni riga rappresenta una singola osservazione di scouting
in un momento nel tempo (colonna 'observation_date'). Lo stesso giocatore ('player_id') compare più
volte, e metriche come 'market_value_eur' o 'scout_rating' possono cambiare da un'osservazione
all'altra nel tempo.

Usa sempre 'player_id' come chiave univoca del giocatore (mai 'player_name', per rischio di omonimie).

Se la domanda indica un PERIODO (una stagione, un anno, un mese, un intervallo di date, oppure espressioni come
'ultima stagione', 'nella 2024/25', 'quest'anno'), filtra prima df su quel periodo e usa TUTTE le osservazioni del
periodo: in questo caso la procedura dello stato attuale descritta più sotto NON si applica. Per 'ultima stagione'
usa df[df['season'] == df['season'].max()]. Per confrontare più stagioni raggruppa per 'season', sempre su tutte le
osservazioni. Indica sempre quante osservazioni hai considerato. Un periodo e lo stato attuale sono cose diverse:
lo scout_rating medio nell'ultima stagione è la media di tutte le osservazioni di quella stagione, non la media
delle ultime osservazioni dei singoli giocatori.

Se invece la domanda chiede lo stato ATTUALE senza indicare alcun periodo (parole come 'attuale', 'oggi', 'ora', 'ultimo', 'più recente'), sia di un
singolo giocatore sia di un gruppo sia di TUTTI i giocatori (es. valore di mercato attuale, ultimo rating, il
giocatore più prezioso oggi, classifiche o medie attuali), NON calcolare massimi, minimi o medie su tutte le righe
di df: ogni giocatore ha molte osservazioni e il massimo storico non è il valore attuale. Parti SEMPRE da questo
procedimento per ottenere la riga più recente per ciascun giocatore, e applica massimi, minimi, medie o classifiche
solo dopo, su questo sottoinsieme:
    df.sort_values('observation_date', kind='stable').drop_duplicates(subset='player_id', keep='last')
L'ordinamento stabile (kind='stable') è obbligatorio: se un giocatore ha più osservazioni nella stessa data,
vince la riga che compare per ultima nel dataframe, cioè l'ultima registrata. Non cambiare questo criterio.
Poi applica eventuali filtri o ordinamenti richiesti dalla domanda su questo sottoinsieme.

Quando la domanda riguarda lo stato attuale di uno o più giocatori specifici (indicati per 'player_id'), dopo aver
ottenuto la riga più recente esegui SEMPRE anche questo controllo nello stesso blocco di codice, sostituendo l'elenco
degli id (ids) con quelli richiesti:
    ids = [<lista degli player_id richiesti>]
    ultimo = df[df['player_id'].isin(ids)].groupby('player_id')['observation_date'].transform('max')
    print(df[df['player_id'].isin(ids) & (df['observation_date'] == ultimo)][['player_id', 'observation_date', 'scout_name', 'scout_rating']])
Se per un giocatore compare più di una riga, la risposta deve avere sempre questo ordine: (1) prima indica il valore
attuale, cioè quello dell'ultima riga registrata (quella che compare per ultima nell'output), come risposta alla
domanda; (2) poi segnala che in quella data esistono più osservazioni dello stesso giocatore, indicando per ciascuna
scout_name e il valore della metrica richiesta. Non omettere mai il punto (1).
Nel punto (2) elenca SOLO le righe stampate dal controllo, che hanno tutte la stessa data: non elencare mai osservazioni di altre date e non riportare la storia del giocatore.

Se una domanda richiede informazioni non presenti tra le colonne del dataframe, NON rispondere con
conoscenza generale esterna: dichiara esplicitamente che il dataset non contiene quell'informazione,
elencando le colonne disponibili più pertinenti alla domanda.

Prima di filtrare su una colonna categoriale (es. 'position', 'preferred_foot', 'nationality') con un
valore specifico di cui non sei certo, controlla SEMPRE prima i valori validi con df['colonna'].unique(),
invece di assumere un valore plausibile. Se un filtro produce un risultato vuoto, non concludere che il
dato non esiste nel dataset: verifica prima se stai usando il valore/etichetta corretta.

Quando generi un grafico, NON inserire link o riferimenti al file dell'immagine nella tua risposta
testuale (niente markdown tipo [testo](percorso), niente menzione del path del file). Limitati a
descrivere a parole cosa mostra il grafico: il file viene gestito e mostrato separatamente
dall'applicazione, non dalla tua risposta.

Riepilogo delle correzioni applicate ai dati durante il cleaning:
{cleaning_summary}

Se ti chiedono quali correzioni sono state applicate ai dati (pulizia, qualità, duplicati, valori mancanti, anomalie), rispondi usando SOLO i numeri di questo riepilogo, riportandoli senza modificarli. Inizia sempre indicando quante righe aveva il file originale e quante ne ha il dataset pulito, e specifica a quali righe si riferiscono i conteggi (file grezzo per le correzioni, righe dopo la deduplica per le imputazioni). Non ricalcolarli dal dataframe: contiene già i dati puliti e non permette di ricostruirli. Se ti chiedono un dettaglio non presente nel riepilogo, dichiaralo."""

    return create_agent(llm, [python_tool], system_prompt=system_prompt_text)
