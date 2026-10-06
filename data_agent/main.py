"""Microservizio FastAPI del data agent di ScoutEdge Analytics.

Espone tre cose:
- GET /          controllo di stato (health check);
- POST /analyze  riceve una domanda in linguaggio naturale, la fa analizzare all'agente
                 (agent.py) e restituisce {answer, chart_url};
- /charts        i grafici PNG generati, serviti come file statici.

Al caricamento del servizio il CSV viene letto e pulito una sola volta (lifespan); l'agente
invece si costruisce a ogni richiesta, così ogni domanda parte da uno stato pulito.

Il front end non chiama mai questo servizio: parla solo con il back end Node, che inoltra le
domande qui e converte chart_url in chartUrl secondo il contratto API.

Avvio (con il venv attivo): da data_agent/ `uvicorn main:app --reload`, oppure dalla root
del repo `uvicorn --app-dir data_agent main:app`. Ascolta solo su 127.0.0.1.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
import re

import pandas as pd
from langchain_openai import ChatOpenAI

from cleaning import clean_scouting_data, format_cleaning_report
from agent import build_data_agent, CHARTS_DIR

load_dotenv()

# Path assoluto basato sulla posizione di questo file, non sulla working directory
# di avvio: cosi' funziona indipendentemente da dove viene lanciato 'uvicorn'.
BASE_DIR = Path(__file__).resolve().parent

# Stato condiviso dell'app: caricato una sola volta all'avvio, non ad ogni richiesta
state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prepara le risorse all'avvio e le libera allo spegnimento.

    Carica il CSV, lo pulisce con clean_scouting_data (che si ferma con un errore se i
    controlli finali falliscono: meglio un avvio fallito che dati sbagliati) e conserva in
    `state` dataframe pulito, modello e riepilogo delle correzioni.
    """
    df_raw = pd.read_csv(BASE_DIR / ".." / "data" / "scouting_data.csv")
    df_clean, cleaning_report = clean_scouting_data(df_raw)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    # L'agente NON si costruisce qui: ogni richiesta ne vuole uno nuovo (con il suo namespace
    # e la sua copia di df), così le richieste non si influenzano. Si conservano solo gli
    # ingredienti, che nessuna richiesta modifica.
    state["df"] = df_clean
    state["llm"] = llm
    state["cleaning_summary"] = format_cleaning_report(cleaning_report)
    print(f"Data agent pronto — dataframe caricato: {df_clean.shape}")

    yield  # l'app gira qui

    state.clear()


app = FastAPI(lifespan=lifespan)

# I grafici salvati da agent.py in charts/ diventano raggiungibili come file statici,
# es. charts/chart_xxxx.png -> http://localhost:8000/charts/chart_xxxx.png
app.mount("/charts", StaticFiles(directory=CHARTS_DIR), name="charts")


class Question(BaseModel):
    """Corpo della richiesta di POST /analyze: la domanda dell'utente."""
    question: str


class Answer(BaseModel):
    """Corpo della risposta: il testo e, se è stato generato un grafico, il suo URL relativo
    (es. /charts/chart_ab12cd34.png). chart_url è un campo interno: il back end lo converte
    in chartUrl per il front end."""
    answer: str
    chart_url: str | None = None


# Il nome deve avere esattamente la forma prevista dal contratto API:
# chart_ + 8 caratteri esadecimali + .png (stessa regola del back end).
CHART_NOTE_PATTERN = re.compile(r"\[Grafico salvato correttamente: (chart_[0-9a-f]{8}\.png)\]")


@app.get("/")
def health_check():
    """Verifica che il servizio sia attivo (non controlla l'agente né il modello)."""
    return {"status": "ok"}


@app.post("/analyze", response_model=Answer)
def analyze(payload: Question):
    """Fa analizzare la domanda all'agente e restituisce risposta e URL del grafico.

    Flusso: costruisce un agente nuovo, lo invoca con la domanda, prende il testo
    dell'ultimo messaggio come risposta e cerca nei messaggi del tool la nota che segnala
    un grafico salvato. In caso di errore dell'agente risponde 502; il dettaglio contiene
    il testo grezzo dell'eccezione, quindi il back end non deve inoltrarlo al browser.
    """
    # Agente nuovo a ogni richiesta: namespace e copia di df isolati dalle altre richieste.
    # Costruirlo costa pochi millisecondi vs i secondi della chiamata al modello.
    agent = build_data_agent(state["df"], state["llm"], state["cleaning_summary"])

    try:
        risposta = agent.invoke({
            "messages": [{"role": "user", "content": payload.question}]
        })
    except Exception as e:
        # Errore lato agente (es. rate limit OpenAI, timeout, errore di rete):
        # lo trasformiamo in una risposta HTTP leggibile invece di un 500 generico,
        # cosi' il back end Express che chiama questo endpoint puo' gestirlo.
        raise HTTPException(status_code=502, detail=f"Errore nell'agente: {e}")

    answer_text = risposta["messages"][-1].content

    # cerchiamo tra i messaggi del tool se e' stato salvato un grafico in questa richiesta
    # La nota arriva dal tool come testo: è l'unico canale con cui agent.py comunica il nome
    # del file. Se in una richiesta si generano più grafici, vale l'ultimo.
    chart_url = None
    for msg in risposta["messages"]:
        if getattr(msg, "type", None) == "tool":
            match = CHART_NOTE_PATTERN.search(msg.content or "")
            if match:
                chart_url = "/charts/" + match.group(1)  # es. /charts/chart_ab12cd34.png

    return Answer(answer=answer_text, chart_url=chart_url)
