"""Test di concorrenza del tool python_repl.

Due richieste che arrivano insieme (FastAPI esegue `analyze` in un pool di thread) non devono
mescolare output e grafici, e alla fine le funzioni di matplotlib e sys.stdout devono essere
quelle originali.
"""

import re
import sys
import threading

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from matplotlib.figure import Figure

import agent

# Il codice che ogni thread fa eseguire al tool: crea una figura diversa, aspetta (così le
# due esecuzioni restano sovrapposte se non c'è nessuna protezione) e stampa il proprio marcatore.
CODICE = """
import time
plt.figure()
plt.plot([1, 2, 3], [1, 2, 3], color='{colore}')
plt.title('{marcatore}')
time.sleep(0.3)
print('{marcatore}')
"""

NOTA = re.compile(r"\[Grafico salvato correttamente: (chart_[0-9a-f]{8}\.png)\]")


@pytest.fixture(autouse=True)
def originali():
    """Fotografa le funzioni che il tool sostituisce temporaneamente e le rimette a posto
    alla fine di ogni test: se il codice è sbagliato e le lascia vuote, il danno non si
    propaga ai test successivi. Restituisce la fotografia per i confronti."""
    stato = {
        "plt.savefig": plt.savefig,
        "plt.close": plt.close,
        "plt.show": plt.show,
        "Figure.savefig": Figure.savefig,
        "sys.stdout": sys.stdout,
    }
    yield stato
    plt.savefig = stato["plt.savefig"]
    plt.close = stato["plt.close"]
    plt.show = stato["plt.show"]
    Figure.savefig = stato["Figure.savefig"]
    sys.stdout = stato["sys.stdout"]
    plt.close("all")


def _nuovo_tool():
    # Come fa build_data_agent a ogni richiesta: un tool nuovo con la sua copia del dataframe.
    return agent.make_python_tool(pd.DataFrame({"x": [1, 2]}))


def test_una_esecuzione(cartella_grafici):
    """Sanità: il tool si chiama senza il modello e salva un grafico."""
    risultato = _nuovo_tool().invoke({"code": CODICE.format(marcatore="SOLO", colore="red")})
    assert "SOLO" in risultato
    nota = NOTA.search(risultato)
    assert nota is not None
    assert (cartella_grafici / nota.group(1)).exists()


def _esegui(chiave, colore, barriera, risultati):
    try:
        tool = _nuovo_tool()
        barriera.wait(timeout=10)  # i due thread partono nello stesso momento
        risultati[chiave] = tool.invoke({"code": CODICE.format(marcatore=chiave, colore=colore)})
    except Exception as e:
        risultati[chiave] = f"ECCEZIONE nel thread: {e!r}"


@pytest.mark.parametrize("giro", range(20))
def test_due_esecuzioni_parallele(cartella_grafici, originali, giro):
    risultati = {}
    barriera = threading.Barrier(2)
    thread = [
        threading.Thread(target=_esegui, args=("MARCATORE_A", "red", barriera, risultati)),
        threading.Thread(target=_esegui, args=("MARCATORE_B", "blue", barriera, risultati)),
    ]
    for t in thread:
        t.start()
    for t in thread:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in thread), "un thread non è terminato"

    a, b = risultati["MARCATORE_A"], risultati["MARCATORE_B"]

    # Ogni risultato contiene solo il proprio marcatore.
    assert "MARCATORE_A" in a and "MARCATORE_B" not in a
    assert "MARCATORE_B" in b and "MARCATORE_A" not in b

    # Ognuno ha la propria nota del grafico, con nomi diversi.
    nota_a, nota_b = NOTA.search(a), NOTA.search(b)
    assert nota_a is not None and nota_b is not None
    assert nota_a.group(1) != nota_b.group(1)

    # I due PNG esistono, sono gli unici nella cartella e hanno contenuto diverso.
    file_a = cartella_grafici / nota_a.group(1)
    file_b = cartella_grafici / nota_b.group(1)
    assert file_a.exists() and file_b.exists()
    assert len(list(cartella_grafici.glob("*.png"))) == 2
    assert file_a.read_bytes() != file_b.read_bytes()

    # Alla fine le funzioni e sys.stdout sono quelli originali.
    assert plt.savefig is originali["plt.savefig"]
    assert plt.close is originali["plt.close"]
    assert plt.show is originali["plt.show"]
    assert Figure.savefig is originali["Figure.savefig"]
    assert sys.stdout is originali["sys.stdout"]


def test_lock_occupato_restituisce_errore_leggibile(cartella_grafici, monkeypatch):
    """Se il lock resta preso oltre il tempo massimo, il tool risponde con un errore
    leggibile per il modello invece di restare in attesa."""
    monkeypatch.setattr(agent, "ATTESA_MASSIMA_LOCK_S", 0.1)
    agent._lock_esecuzione.acquire()
    try:
        risultato = _nuovo_tool().invoke({"code": "print('ciao')"})
    finally:
        agent._lock_esecuzione.release()
    assert "occupato" in risultato
    assert "ciao" not in risultato


def test_lock_rilasciato_dopo_un_errore(cartella_grafici, monkeypatch):
    """Un codice che solleva un'eccezione non deve lasciare il lock preso: la richiesta
    successiva deve funzionare."""
    # Attesa breve: se il lock restasse preso, il test fallisce subito invece di aspettare 30 s.
    monkeypatch.setattr(agent, "ATTESA_MASSIMA_LOCK_S", 0.1)
    tool = _nuovo_tool()
    errore = tool.invoke({"code": "1/0"})
    assert errore.startswith("Errore nell'esecuzione")
    assert "ok" in tool.invoke({"code": "print('ok')"})
