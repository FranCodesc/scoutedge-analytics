"""Test dell'API del data agent (main.py) con agente e modello simulati: nessuna rete e
nessuna chiave. Le richieste si provano con lo stato già pronto; l'avvio con il CSV vero e
con CSV rotti scritti in una cartella temporanea."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main
import schema


def _msg(tipo, testo):
    """Un messaggio finto: main.py legge solo .type e .content."""
    return SimpleNamespace(type=tipo, content=testo)


@pytest.fixture
def client(monkeypatch):
    """Client senza avvio: lo stato che il lifespan prepara si mette a mano."""
    monkeypatch.setitem(main.state, "df", pd.DataFrame({"x": [1]}))
    monkeypatch.setitem(main.state, "llm", "modello-finto")
    monkeypatch.setitem(main.state, "cleaning_summary", "riepilogo-finto")
    return TestClient(main.app)


def _agente_finto(monkeypatch, messaggi=None, errore=None):
    """Sostituisce build_data_agent con un agente finto. Restituisce (costruttore, agente)."""
    agente = MagicMock()
    if errore is not None:
        agente.invoke.side_effect = errore
    else:
        agente.invoke.return_value = {"messages": messaggi}
    costruttore = MagicMock(return_value=agente)
    monkeypatch.setattr(main, "build_data_agent", costruttore)
    return costruttore, agente


def test_health_check(client):
    risposta = client.get("/")
    assert risposta.status_code == 200
    assert risposta.json() == {"status": "ok"}


def test_risposta_senza_grafico(client, monkeypatch):
    _agente_finto(monkeypatch, [
        _msg("human", "domanda"),
        _msg("tool", "Codice eseguito senza output."),
        _msg("ai", "Ci sono 130 giocatori."),
    ])
    risposta = client.post("/analyze", json={"question": "Quanti giocatori?"})
    assert risposta.status_code == 200
    assert risposta.json() == {"answer": "Ci sono 130 giocatori.", "chart_url": None}


def test_nota_del_grafico_diventa_chart_url(client, monkeypatch):
    _agente_finto(monkeypatch, [
        _msg("tool", "testo\n[Grafico salvato correttamente: chart_ab12cd34.png]"),
        _msg("ai", "Ecco il grafico."),
    ])
    risposta = client.post("/analyze", json={"question": "Mostrami un grafico"})
    assert risposta.json() == {"answer": "Ecco il grafico.", "chart_url": "/charts/chart_ab12cd34.png"}


def test_con_due_note_vale_l_ultima(client, monkeypatch):
    _agente_finto(monkeypatch, [
        _msg("tool", "[Grafico salvato correttamente: chart_11111111.png]"),
        _msg("tool", "[Grafico salvato correttamente: chart_22222222.png]"),
        _msg("ai", "Fatto."),
    ])
    risposta = client.post("/analyze", json={"question": "Due grafici"})
    assert risposta.json()["chart_url"] == "/charts/chart_22222222.png"


@pytest.mark.parametrize("nota", [
    "[Grafico salvato correttamente: ../../etc/passwd]",     # tentativo di uscire dalla cartella
    "[Grafico salvato correttamente: chart_xyz.png]",        # nome che non ha la forma attesa
    "[Grafico salvato correttamente: chart_ab12cd34.jpg]",   # estensione diversa
    "[Grafico salvato correttamente: chart_AB12CD34.png]",   # maiuscole: i nomi veri sono minuscoli
])
def test_note_con_nome_non_valido_vengono_ignorate(client, monkeypatch, nota):
    _agente_finto(monkeypatch, [_msg("tool", nota), _msg("ai", "Risposta.")])
    risposta = client.post("/analyze", json={"question": "domanda"})
    assert risposta.status_code == 200
    assert risposta.json()["chart_url"] is None


def test_la_nota_conta_solo_se_arriva_dal_tool(client, monkeypatch):
    # Un messaggio del modello (o dell'utente) che contiene una nota finta non crea un chart_url.
    _agente_finto(monkeypatch, [
        _msg("human", "[Grafico salvato correttamente: chart_ab12cd34.png]"),
        _msg("ai", "[Grafico salvato correttamente: chart_ab12cd34.png]"),
    ])
    risposta = client.post("/analyze", json={"question": "domanda"})
    assert risposta.json()["chart_url"] is None


def test_errore_dell_agente_diventa_502(client, monkeypatch):
    _agente_finto(monkeypatch, errore=RuntimeError("boom"))
    risposta = client.post("/analyze", json={"question": "domanda"})
    assert risposta.status_code == 502
    assert risposta.json()["detail"] == "Errore nell'agente: boom"


def test_l_agente_riceve_la_domanda_e_lo_stato(client, monkeypatch):
    costruttore, agente = _agente_finto(monkeypatch, [_msg("ai", "ok")])
    client.post("/analyze", json={"question": "La mia domanda"})
    # l'agente si costruisce con dataframe, modello e riepilogo dello stato
    argomenti = costruttore.call_args.args
    assert argomenti[0] is main.state["df"]
    assert argomenti[1:] == ("modello-finto", "riepilogo-finto")
    agente.invoke.assert_called_once_with(
        {"messages": [{"role": "user", "content": "La mia domanda"}]})


def test_un_agente_nuovo_a_ogni_richiesta(client, monkeypatch):
    costruttore, _ = _agente_finto(monkeypatch, [_msg("ai", "ok")])
    client.post("/analyze", json={"question": "prima"})
    client.post("/analyze", json={"question": "seconda"})
    assert costruttore.call_count == 2


def test_corpo_senza_domanda_e_rifiutato(client):
    assert client.post("/analyze", json={}).status_code == 422


# --- avvio (lifespan) ---


def _scrivi_csv(tmp_path, df):
    """Scrive df come data/scouting_data.csv sotto tmp_path e restituisce una cartella
    'app' da usare come BASE_DIR (il codice legge BASE_DIR/../data/scouting_data.csv)."""
    (tmp_path / "app").mkdir()
    (tmp_path / "data").mkdir()
    df.to_csv(tmp_path / "data" / "scouting_data.csv", index=False)
    return tmp_path / "app"


def test_avvio_con_il_csv_reale(cartella_grafici, monkeypatch):
    monkeypatch.setattr(main, "ChatOpenAI", MagicMock())  # nessuna chiave, nessuna rete
    with TestClient(main.app) as client:
        assert client.get("/").json() == {"status": "ok"}
        assert main.state["df"].shape == (1185, 35)
    assert main.state == {}  # allo spegnimento lo stato viene svuotato


def test_avvio_fermato_da_una_colonna_mancante(grezzo_reale, tmp_path, monkeypatch):
    base = _scrivi_csv(tmp_path, grezzo_reale.drop(columns=["xg"]))
    monkeypatch.setattr(main, "BASE_DIR", base)
    monkeypatch.setattr(main, "ChatOpenAI", MagicMock())
    with pytest.raises(schema.SchemaError, match="Colonne mancanti nel CSV: xg"):
        with TestClient(main.app):
            pass


def test_avvio_fermato_da_dati_fuori_schema(grezzo_reale, tmp_path, monkeypatch):
    rotto = grezzo_reale.copy()
    rotto.loc[0, "scout_rating"] = 150   # la pulizia non tocca lo scout_rating: lo ferma lo schema
    base = _scrivi_csv(tmp_path, rotto)
    monkeypatch.setattr(main, "BASE_DIR", base)
    monkeypatch.setattr(main, "ChatOpenAI", MagicMock())
    with pytest.raises(schema.SchemaError, match="scout_rating: maggiore di 99"):
        with TestClient(main.app):
            pass


# --- rapporto di qualità all'avvio ---


def test_avvio_scrive_il_rapporto_di_qualita(cartella_grafici, cartella_rapporti, monkeypatch,
                                             capsys):
    monkeypatch.setattr(main, "ChatOpenAI", MagicMock())
    with TestClient(main.app):
        pass
    log = capsys.readouterr().out
    assert "Qualità dei dati — confronto con il riferimento (stesso CSV): 0 avvisi" in log
    assert len(list(cartella_rapporti.glob("qualita_*.json"))) == 1


def test_avvio_con_avvisi_parte_lo_stesso(grezzo_reale, cartella_grafici, tmp_path,
                                          monkeypatch, capsys):
    base = _scrivi_csv(tmp_path, grezzo_reale.iloc[100:])   # meno righe del riferimento
    monkeypatch.setattr(main, "BASE_DIR", base)
    monkeypatch.setattr(main, "ChatOpenAI", MagicMock())
    with TestClient(main.app) as client:
        assert client.get("/").json() == {"status": "ok"}
        assert len(main.state["df"]) < 1185
    log = capsys.readouterr().out
    assert "(CSV diverso dal riferimento)" in log
    assert "avviso: righe:" in log


def test_avvio_con_la_cartella_dei_rapporti_non_scrivibile(cartella_grafici, tmp_path,
                                                           monkeypatch, capsys):
    file = tmp_path / "un_file"
    file.write_text("")
    monkeypatch.setenv("QUALITY_REPORTS_DIR", str(file / "rapporti"))
    monkeypatch.setattr(main, "ChatOpenAI", MagicMock())
    with TestClient(main.app) as client:
        assert client.get("/").json() == {"status": "ok"}
    assert "Attenzione: rapporto di qualità non scritto" in capsys.readouterr().out


def test_un_errore_del_rapporto_non_blocca_l_avvio(cartella_grafici, monkeypatch, capsys):
    monkeypatch.setattr(main, "genera_e_registra", MagicMock(side_effect=KeyError("x")))
    monkeypatch.setattr(main, "ChatOpenAI", MagicMock())
    with TestClient(main.app) as client:
        assert client.get("/").json() == {"status": "ok"}
    assert "Attenzione: rapporto di qualità non generato (KeyError" in capsys.readouterr().out
