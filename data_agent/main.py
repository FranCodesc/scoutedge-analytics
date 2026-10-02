import os
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
    df_raw = pd.read_csv(BASE_DIR / ".." / "data" / "scouting_data.csv")
    df_clean, cleaning_report = clean_scouting_data(df_raw)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    agent = build_data_agent(df_clean, llm, format_cleaning_report(cleaning_report))

    state["agent"] = agent
    print(f"Data agent pronto — dataframe caricato: {df_clean.shape}")

    yield  # l'app gira qui

    state.clear()


app = FastAPI(lifespan=lifespan)

# I grafici salvati da agent.py in charts/ diventano raggiungibili come file statici,
# es. charts/chart_xxxx.png -> http://localhost:8000/charts/chart_xxxx.png
app.mount("/charts", StaticFiles(directory=CHARTS_DIR), name="charts")


class Question(BaseModel):
    question: str


class Answer(BaseModel):
    answer: str
    chart_url: str | None = None


CHART_NOTE_PATTERN = re.compile(r"\[Grafico salvato correttamente in: (.+?)\]")


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/analyze", response_model=Answer)
def analyze(payload: Question):
    agent = state["agent"]

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
    chart_url = None
    for msg in risposta["messages"]:
        if getattr(msg, "type", None) == "tool":
            match = CHART_NOTE_PATTERN.search(msg.content or "")
            if match:
                chart_path = match.group(1)  # es. "charts/chart_xxxx.png"
                chart_url = "/" + chart_path

    return Answer(answer=answer_text, chart_url=chart_url)