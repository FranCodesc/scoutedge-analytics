"""Regressione del data agent: manda domande a POST /analyze e controlla le risposte.

Richiede il data agent acceso sulla porta 8000 (da data_agent/, con il venv attivo:
uvicorn main:app). Lo script usa solo la libreria standard: nessuna dipendenza da installare.
Ogni domanda passa dal modello OpenAI, quindi l'esecuzione consuma chiamate a OpenAI (la
batteria completa ne fa decine). Lo script non scrive file.

Uso (da data_agent/):
    python scripts/regression_check.py                      # esegue tutti i casi
    python scripts/regression_check.py giocatore            # solo i casi il cui nome contiene "giocatore"
    RIPETI=3 python scripts/regression_check.py "giocatore 33"   # ripete ogni caso 3 volte
"""

import json
import os
import re
import sys
import urllib.request

URL = "http://127.0.0.1:8000"
TIMEOUT = 120  # secondi per richiesta: l'agente può chiamare il modello più volte

# Ogni caso: nome, domanda, numero di ripetizioni (n), pattern che DEVONO comparire tutti
# ("deve") e pattern che NON devono comparire ("non_deve"). Sono espressioni regolari senza
# distinzione tra maiuscole e minuscole. I numeri accettano punto o virgola come
# separatore, perché il modello a volte scrive 65.11 e a volte 65,11.
CASI = [
    {
        "nome": "ultima stagione",
        "domanda": "Qual è lo scout_rating medio nell'ultima stagione?",
        "n": 3,
        "deve": [r"65[.,]11", r"\b405\b"],
        "non_deve": [r"65[.,]21"],  # 65.21 = media sulle ultime osservazioni: sbagliato
    },
    {
        "nome": "portieri ultima stagione",
        "domanda": "Qual è lo scout_rating medio dei portieri nell'ultima stagione?",
        "n": 1,
        "deve": [r"68[.,]91", r"\b46\b"],
        "non_deve": [],
    },
    {
        "nome": "tre stagioni",
        "domanda": "Com'è cambiato lo scout_rating medio nelle tre stagioni?",
        "n": 1,
        "deve": [r"66[.,]59", r"66[.,]18", r"65[.,]11"],
        "non_deve": [],
    },
    {
        "nome": "valore attuale piu alto",
        "domanda": "Qual è il valore di mercato attuale più alto?",
        "n": 2,
        "deve": [r"18[.,]?680[.,]?000"],
        "non_deve": [r"19[.,]?102[.,]?000"],  # massimo storico: sbagliato per "attuale"
    },
    {
        "nome": "valore massimo storico",
        "domanda": "Qual è il valore di mercato più alto mai registrato?",
        "n": 1,
        "deve": [r"19[.,]?102[.,]?000"],
        "non_deve": [],
    },
    {
        "nome": "valore medio osservazione piu recente",
        "domanda": "Qual è il valore di mercato medio considerando l'osservazione più recente di ogni giocatore?",
        "n": 1,
        "deve": [r"6[.,]?887[.,]?985"],
        "non_deve": [],
    },
    {
        "nome": "giocatore 70",
        "domanda": "Qual è lo scout_rating attuale del giocatore 70?",
        "n": 2,
        "deve": [r"\b66\b", r"Marini", r"\b57\b", r"Russo"],
        # gli altri scout compaiono solo se il modello elenca la storia del giocatore
        "non_deve": [r"Valeria Costa|Chiara Fontana|Marco Ferrari|Giulia Ricci"],
    },
    {
        "nome": "giocatore con ID 70",
        "domanda": "Qual è il rating attuale del giocatore con ID 70?",
        "n": 3,
        "deve": [r"\b66\b", r"Marini", r"\b57\b", r"Russo"],
        # stessi controlli del caso "giocatore 70": la forma "con ID" è quella che usa
        # l'orchestratore quando divide una domanda su più giocatori
        "non_deve": [r"Valeria Costa|Chiara Fontana|Marco Ferrari|Giulia Ricci"],
    },
    {
        "nome": "giocatore 33",
        "domanda": "Qual è lo scout_rating attuale del giocatore 33?",
        "n": 1,
        "deve": [r"\b80\b"],
        "non_deve": [r"Marini", r"più osservazioni", r"più di un"],
    },
    {
        "nome": "3 difensori centrali (A)",
        "domanda": "Quali sono i 3 difensori centrali con il duels_won_pct più alto nell'osservazione più recente?",
        "n": 5,
        "deve": [r"Pereira.*Balaguer.*Ito Yuta", r"72[.,]0", r"67[.,]9", r"64[.,]1"],
        "non_deve": [],
    },
    {
        "nome": "3 difensori centrali (B)",
        "domanda": "Mostrami i 3 difensori centrali con il duels_won_pct più alto nell'osservazione più recente.",
        "n": 3,
        "deve": [r"Pereira.*Balaguer.*Ito Yuta", r"72[.,]0", r"67[.,]9", r"64[.,]1"],
        "non_deve": [],
    },
]

# Casi per ruolo: stessa struttura, ultima stagione. Si chiede il numero di osservazioni
# perché il conteggio è metà del controllo.
RUOLI = [
    ("difensori centrali", r"62[.,]34", r"\b41\b"),
    ("terzini", r"63[.,]53", r"\b86\b"),
    ("difensori", r"63[.,]15", r"\b127\b"),
    ("attaccanti", r"63[.,]93", r"\b76\b"),
    ("centrocampisti", r"66[.,]16", r"\b156\b"),
]
for ruolo, media, osservazioni in RUOLI:
    CASI.append({
        "nome": f"ruolo {ruolo}",
        "domanda": f"Qual è lo scout_rating medio dei {ruolo} nell'ultima stagione? "
                   "Indica quante osservazioni hai considerato.",
        "n": 1,
        "deve": [media, osservazioni],
        "non_deve": [],
    })


def chiedi(domanda):
    """Invia la domanda a POST /analyze e restituisce il testo della risposta."""
    corpo = json.dumps({"question": domanda}).encode("utf-8")
    richiesta = urllib.request.Request(
        URL + "/analyze",
        data=corpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(richiesta, timeout=TIMEOUT) as risposta:
        return json.loads(risposta.read().decode("utf-8"))["answer"]


def controlla(risposta, caso):
    """Restituisce l'elenco dei problemi trovati (vuoto = risposta corretta)."""
    flags = re.IGNORECASE | re.DOTALL  # DOTALL: il '.*' deve poter attraversare gli a capo
    problemi = []
    for pattern in caso["deve"]:
        if not re.search(pattern, risposta, flags):
            problemi.append(f"manca: {pattern}")
    for pattern in caso["non_deve"]:
        if re.search(pattern, risposta, flags):
            problemi.append(f"non dovrebbe comparire: {pattern}")
    return problemi


def main():
    filtro = " ".join(sys.argv[1:]).lower()
    ripeti = int(os.environ.get("RIPETI", "0"))  # 0 = usa le ripetizioni previste dal caso
    casi = [c for c in CASI if filtro in c["nome"].lower()]
    if not casi:
        print(f"Nessun caso contiene '{filtro}'.")
        sys.exit(1)

    # Controllo preliminare: se il servizio non risponde, inutile continuare.
    try:
        urllib.request.urlopen(URL + "/", timeout=5)
    except Exception as errore:
        print(f"Il servizio non risponde su {URL}: {errore}")
        sys.exit(1)

    totali = 0
    falliti = []
    for caso in casi:
        n = ripeti or caso["n"]
        for i in range(1, n + 1):
            totali += 1
            etichetta = f"{caso['nome']} ({i}/{n})"
            try:
                risposta = chiedi(caso["domanda"])
                problemi = controlla(risposta, caso)
            except Exception as errore:
                risposta = ""
                problemi = [f"errore nella richiesta: {errore}"]

            if problemi:
                falliti.append(etichetta)
                print(f"KO  {etichetta}")
                for problema in problemi:
                    print(f"      {problema}")
                print(f"      risposta: {risposta!r}")
            else:
                print(f"OK  {etichetta}")

    print()
    print(f"Totale: {totali - len(falliti)}/{totali} ok")
    if falliti:
        print("Falliti:", ", ".join(falliti))
        sys.exit(1)


if __name__ == "__main__":
    main()
