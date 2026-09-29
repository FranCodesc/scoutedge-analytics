import io
import contextlib
import ast
import uuid
import os

import matplotlib
matplotlib.use("Agg")  # backend non interattivo: necessario in un processo server, senza display
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from langchain_core.tools import tool
from langchain.agents import create_agent

CHARTS_DIR = "charts"
os.makedirs(CHARTS_DIR, exist_ok=True)


def make_python_tool(df):
    """Costruisce il tool 'python_repl' per un dataframe specifico.
    Lo stato (local_vars) e' creato una sola volta qui e condiviso tra tutte le chiamate
    al tool, cosi' le variabili definite da una tool-call restano disponibili nelle successive."""
    local_vars = {"df": df, "pd": pd, "plt": plt, "sns": sns}

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
            tree = ast.parse(code)
            *body, last = tree.body if tree.body else [None]

            with contextlib.redirect_stdout(output):
                if body:
                    exec(compile(ast.Module(body=body, type_ignores=[]), "<code>", "exec"), {}, local_vars)
                if last is not None:
                    if isinstance(last, ast.Expr):
                        result = eval(compile(ast.Expression(last.value), "<code>", "eval"), {}, local_vars)
                        if result is not None:
                            print(repr(result))
                    else:
                        exec(compile(ast.Module(body=[last], type_ignores=[]), "<code>", "exec"), {}, local_vars)

                if plt.get_fignums():
                    filename = f"{CHARTS_DIR}/chart_{uuid.uuid4().hex[:8]}.png"
                    plt.savefig(filename, bbox_inches="tight")
                    plt.close("all")
                    chart_note = f"\n[Grafico salvato correttamente in: {filename}]"
        except Exception as e:
            plt.close("all")
            return f"Errore nell'esecuzione: {e}"
        return (output.getvalue() or "Codice eseguito senza output.") + chart_note
    return python_repl


def build_data_agent(df, llm):
    """Costruisce un agente ReAct per l'analisi del dataframe 'df'.
    Restituisce l'agente pronto per .invoke()."""

    python_tool = make_python_tool(df)

    system_prompt_text = f"""Colonne disponibili nel dataframe 'df': {list(df.columns)}

Nota importante sulla struttura dei dati: ogni riga rappresenta una singola osservazione di scouting
in un momento nel tempo (colonna 'observation_date'). Lo stesso giocatore ('player_id') compare più
volte, e metriche come 'market_value_eur' o 'scout_rating' possono cambiare da un'osservazione
all'altra nel tempo.

Usa sempre 'player_id' come chiave univoca del giocatore (mai 'player_name', per rischio di omonimie).

Se la domanda riguarda lo stato ATTUALE di un giocatore (es. valore di mercato attuale, ultimo rating),
NON prendere il valore massimo/minimo storico. Usa esattamente questo procedimento per ottenere
la riga più recente per ciascun giocatore:
    df.sort_values('observation_date').drop_duplicates(subset='player_id', keep='last')
Poi applica eventuali filtri o ordinamenti richiesti dalla domanda su questo sottoinsieme.

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
dall'applicazione, non dalla tua risposta."""

    return create_agent(llm, [python_tool], system_prompt=system_prompt_text)
