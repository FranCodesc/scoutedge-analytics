"""Traccia dell'esecuzione del data agent su una domanda.

Costruisce lo stesso agente di main.py (stessi dati puliti, stesso modello, stesso prompt),
lo invoca con la sola domanda, come fa POST /analyze, e stampa passo per passo il codice che
il modello manda a python_repl, l'output restituito dal tool e il testo del modello. Serve a
capire cosa ha eseguito l'agente quando una risposta è sbagliata, prima di toccare il prompt.

Uso (da data_agent/, con il venv attivo e la chiave API in data_agent/.env):
    python scripts/traccia_agente.py "Qual è il rating attuale del giocatore con ID 70?"

Ogni esecuzione chiama il modello OpenAI e consuma quindi crediti API. Lo script non scrive
file: stampa soltanto a video.
"""

import os
import sys

import pandas as pd
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

if len(sys.argv) < 2:
    sys.exit('Uso: python scripts/traccia_agente.py "<domanda>"')

# Si lancia da data_agent/: si aggiunge la cartella corrente al percorso di ricerca per poter
# importare cleaning e agent, che stanno lì e non nella cartella dello script.
sys.path.insert(0, os.getcwd())
load_dotenv(".env")  # la chiave API sta in data_agent/.env, mai nel codice

from cleaning import clean_scouting_data, format_cleaning_report
from agent import build_data_agent

domanda = sys.argv[1]

# Stessa preparazione di main.py (lifespan): CSV, pulizia, modello, riepilogo.
df_raw = pd.read_csv("../data/scouting_data.csv")
df_clean, report = clean_scouting_data(df_raw)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
riepilogo = format_cleaning_report(report)

# Stessa costruzione e stessa invocazione di POST /analyze.
agent = build_data_agent(df_clean, llm, riepilogo)
risposta = agent.invoke({"messages": [{"role": "user", "content": domanda}]})

print("=" * 70)
print("DOMANDA:", domanda)
for i, msg in enumerate(risposta["messages"]):
    if msg.type == "human":
        continue
    if msg.type == "ai":
        # Il codice scritto dal modello sta negli argomenti delle tool-call.
        for chiamata in getattr(msg, "tool_calls", []) or []:
            print(f"\n--- [{i}] CODICE ESEGUITO ---")
            print(chiamata["args"].get("code"))
        if msg.content:
            print(f"\n--- [{i}] TESTO DEL MODELLO ---")
            print(msg.content)
    elif msg.type == "tool":
        print(f"\n--- [{i}] OUTPUT DEL TOOL ---")
        print(msg.content)
print("=" * 70)
