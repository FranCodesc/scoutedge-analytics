"""Test del rapporto di qualità (qualita.py): profilo, percorso nella pulizia, limiti
osservati, avvisi del confronto con il riferimento e scrittura del JSON. Nessuna rete."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import qualita
import schema

CSV = Path(__file__).resolve().parents[2] / "data" / "scouting_data.csv"


@pytest.fixture(scope="module")
def riferimento(grezzo_reale, pulito_reale):
    """Un riferimento costruito sul CSV reale, come lo scrive lo script di aggiornamento."""
    df, report = pulito_reale
    return qualita.profilo_di_riferimento(CSV, grezzo_reale, df, report)


@pytest.fixture
def dati(grezzo_reale, pulito_reale):
    """Copie modificabili del grezzo e del pulito reali."""
    return grezzo_reale.copy(), pulito_reale[0].copy()


def _avvisi(riferimento, grezzo, pulito):
    return qualita.confronta(qualita.profilo(grezzo, valori_aperti=False),
                             qualita.profilo(pulito), riferimento, grezzo, pulito)


# --- impronta, profilo e percorso ---


def test_impronta_file(tmp_path):
    file = tmp_path / "dati.csv"
    file.write_bytes(b"a,b\n1,2\n")
    impronta = qualita.impronta_file(file)
    assert impronta == {"file": "dati.csv", "byte": 8,
                        "sha256": hashlib.sha256(b"a,b\n1,2\n").hexdigest()}
    file.write_bytes(b"a,b\n1,3\n")
    assert qualita.impronta_file(file)["sha256"] != impronta["sha256"]


def test_impronta_indipendente_dagli_a_capo(tmp_path):
    # Nessuna ipotesi sul CSV su disco: con Git su Windows può avere a capo CRLF.
    unix = CSV.read_bytes().replace(b"\r\n", b"\n")
    copie = {"unix.csv": unix, "windows.csv": unix.replace(b"\n", b"\r\n")}
    for nome, contenuto in copie.items():
        (tmp_path / nome).write_bytes(contenuto)
    atteso = qualita.impronta_file(CSV)
    for nome in copie:
        # blocchi di 7 byte: alcuni finiscono con il CR di un a capo CRLF
        for dimensione in (7, 1 << 20):
            copia = qualita.impronta_file(tmp_path / nome, dimensione_blocco=dimensione)
            assert (copia["sha256"], copia["byte"]) == (atteso["sha256"], atteso["byte"])


def test_profilo_su_dati_piccoli():
    df = pd.DataFrame({
        "player_id": [1, 1, 2, 3],
        "height_cm": [180.0, 180.0, None, 190.0],
        "nationality": ["Italy", "Italy", "Spain", None],
        "scout_name": ["Elena Conti"] * 4,
    })
    p = qualita.profilo(df)
    assert (p["righe"], p["giocatori"]) == (4, 3)
    assert p["colonne"]["height_cm"] == {"tipo": "float64", "mancanti": 1, "distinti": 2,
                                         "minimo": 180.0, "massimo": 190.0, "mediana": 180.0}
    assert p["colonne"]["nationality"]["mancanti"] == 1
    assert p["colonne"]["nationality"]["valori"] == ["Italy", "Spain"]
    assert "minimo" not in p["colonne"]["nationality"]   # niente statistiche sui testi


def test_profilo_per_stagione_e_contratti_scaduti():
    df = pd.DataFrame({
        "player_id": [1, 2, 2, 3],
        "season": ["2024/25", "2024/25", "2025/26", "2025/26"],
        "observation_date": pd.to_datetime(["2025-01-10"] * 4),
        "contract_expiry": pd.to_datetime(["2026-06-30", "2024-06-30", "2026-06-30",
                                           "2027-06-30"]),
    })
    p = qualita.profilo(df, valori_aperti=False)
    assert p["stagioni"] == {"2024/25": {"righe": 2, "giocatori": 2},
                             "2025/26": {"righe": 2, "giocatori": 2}}
    assert p["contratti_scaduti_all_osservazione"] == {"righe": 1, "player_id": [2]}
    assert p["colonne"]["observation_date"]["minimo"] == "2025-01-10"


def test_percorso_pulizia_sul_csv_reale(grezzo_reale, pulito_reale):
    df, report = pulito_reale
    percorso = qualita.percorso_pulizia(grezzo_reale, df, report)
    assert [p["righe"] for p in percorso["passi"]] == [1208, 1208, 1185, 1185]
    assert percorso["passi"][2]["rimosse"] == 23
    cambiati = {c: v["valori_cambiati"] for c, v in percorso["colonne"].items()}
    assert cambiati["height_cm"] == 12        # le altezze di 4 cifre divise per 10
    assert cambiati["pass_accuracy_pct"] == 51   # 18 dimezzati + 33 imputati
    assert cambiati["club"] == 151
    assert cambiati["market_value_eur"] == 120   # dal cleaning_report: cambia tipo
    assert cambiati["scout_rating"] == 0


def test_limiti_nel_rapporto_con_osservato_e_margine(pulito_reale):
    voci = {v["regola"]: v for v in qualita.limiti_osservati(pulito_reale[0])}
    assert set(voci) == set(schema.LIMITI)
    assert all(v["motivo"] and v["fonte"] for v in voci.values())
    altezza = voci["height_cm"]
    assert (altezza["osservato_min"], altezza["osservato_max"]) == (163, 198)
    assert (altezza["margine_min"], altezza["margine_max"]) == (13, 22)
    assert voci["minutes_played per partita"]["osservato_max"] == 93.0


# --- confronto con il riferimento ---


def test_nessun_avviso_con_dati_uguali_al_riferimento(riferimento, dati):
    assert _avvisi(riferimento, *dati) == []


def _meno_righe(grezzo, pulito):
    return grezzo, pulito.iloc[:-50]


def _righe_oltre_il_50(grezzo, pulito):
    copia = pulito.iloc[:600].assign(player_id=pulito["player_id"].iloc[:600] + 1000)
    return grezzo, pd.concat([pulito, copia])


def _meno_giocatori(grezzo, pulito):
    return grezzo, pulito[pulito["player_id"] != 1]


def _giocatori_oltre_il_20(grezzo, pulito):
    nuovi = pulito[pulito["player_id"] <= 30]
    return grezzo, pd.concat([pulito, nuovi.assign(player_id=nuovi["player_id"] + 1000)])


def _nazionalita_nuova(grezzo, pulito):
    pulito.loc[pulito.index[0], "nationality"] = "Atlantide"
    return grezzo, pulito


def _osservatore_nuovo(grezzo, pulito):
    pulito.loc[pulito.index[0], "scout_name"] = "Osservatore Nuovo"
    return grezzo, pulito


def _nazionalita_sparita(grezzo, pulito):
    pulito["nationality"] = pulito["nationality"].replace("Argentina", "Austria")
    return grezzo, pulito


def _mancanti_in_piu(grezzo, pulito):
    grezzo.loc[grezzo.index[:120], "xg"] = None   # circa +10 punti sul 4,9% del riferimento
    return grezzo, pulito


def _massimo_fuori(grezzo, pulito):
    pulito.loc[pulito.index[0], "weight_kg"] = 119.0   # soglia: 99,1 + 20% di 35 = 106,1
    return grezzo, pulito


def _minimo_fuori(grezzo, pulito):
    pulito.loc[pulito.index[0], "distance_covered_km"] = 5.0   # soglia: 7,57 - 20% di 5,41
    return grezzo, pulito


# (modifica, controllo atteso, testo atteso nel messaggio)
SCOSTAMENTI = [
    (_meno_righe, "righe", "righe: 1135 contro 1185 del riferimento (calo)"),
    (_righe_oltre_il_50, "righe", "oltre +50%"),
    (_meno_giocatori, "giocatori", "giocatori: 129 contro 130 del riferimento (calo)"),
    (_giocatori_oltre_il_20, "giocatori", "giocatori: 160 contro 130"),
    (_nazionalita_nuova, "categorie", "nationality: valori nuovi ['Atlantide']"),
    (_osservatore_nuovo, "categorie", "scout_name: valori nuovi ['Osservatore Nuovo']"),
    (_nazionalita_sparita, "categorie",
     "nationality: valori del riferimento assenti ['Argentina']"),
    (_mancanti_in_piu, "mancanti", "xg: "),
    (_massimo_fuori, "massimo", "weight_kg: massimo 119.0 oltre il riferimento 99.1"),
    (_minimo_fuori, "minimo", "distance_covered_km: minimo 5.0 sotto il riferimento 7.57"),
]


@pytest.mark.parametrize("modifica, controllo, testo", SCOSTAMENTI,
                         ids=[s[0].__name__.strip("_") for s in SCOSTAMENTI])
def test_avviso_generato(riferimento, dati, modifica, controllo, testo):
    avvisi = _avvisi(riferimento, *modifica(*dati))
    assert any(a["controllo"] == controllo and testo in a["messaggio"] for a in avvisi), avvisi


def _massimo_entro_la_tolleranza(grezzo, pulito):
    pulito.loc[pulito.index[0], "weight_kg"] = 106.0   # sotto la soglia di 106,1
    return grezzo, pulito


def _mancanti_entro_la_tolleranza(grezzo, pulito):
    con_valore = grezzo.index[grezzo["xg"].notna()][:48]   # circa +4 punti
    grezzo.loc[con_valore, "xg"] = None
    return grezzo, pulito


@pytest.mark.parametrize("modifica", [_massimo_entro_la_tolleranza,
                                      _mancanti_entro_la_tolleranza])
def test_scostamento_entro_la_tolleranza_senza_avvisi(riferimento, dati, modifica):
    assert _avvisi(riferimento, *modifica(*dati)) == []


def test_gli_avvisi_mostrano_player_id(riferimento, dati):
    grezzo, pulito = _massimo_fuori(*dati)
    pid = pulito.loc[pulito.index[0], "player_id"]
    [avviso] = _avvisi(riferimento, grezzo, pulito)
    assert f"player_id={pid}: 119.0" in avviso["messaggio"]


# --- scrittura del rapporto ---


def test_rapporto_json_scritto_e_leggibile(riferimento, grezzo_reale, pulito_reale, tmp_path):
    df, report = pulito_reale
    rapporto = qualita.crea_rapporto(CSV, grezzo_reale, df, report, riferimento)
    percorso = qualita.scrivi_rapporto(rapporto, tmp_path / "rapporti")
    testo = percorso.read_text(encoding="utf-8")
    letto = json.loads(testo)
    assert letto["confronto"] == {"riferimento": riferimento["csv"], "stesso_csv": True,
                                  "avvisi": []}
    assert letto["csv"]["file"] == "scouting_data.csv"
    assert str(CSV.parent) not in testo   # nessun percorso assoluto nel rapporto


def test_tiene_solo_gli_ultimi_10_rapporti(tmp_path):
    for i in range(12):
        qualita.scrivi_rapporto({"numero": i}, tmp_path)
    rimasti = sorted(tmp_path.glob("qualita_*.json"))
    assert len(rimasti) == 10
    assert [json.loads(p.read_text())["numero"] for p in rimasti] == list(range(2, 12))


def test_cartella_non_scrivibile_avvisa_e_prosegue(grezzo_reale, pulito_reale, tmp_path,
                                                   capsys):
    file = tmp_path / "un_file"
    file.write_text("")
    df, report = pulito_reale
    rapporto = qualita.genera_e_registra(CSV, grezzo_reale, df, report, file / "rapporti")
    assert rapporto["profilo"]["righe"] == 1185
    assert "Attenzione: rapporto di qualità non scritto" in capsys.readouterr().out


def test_percorso_della_cartella_rispetto_a_data_agent(tmp_path, monkeypatch):
    monkeypatch.delenv("QUALITY_REPORTS_DIR")
    assert qualita.cartella_rapporti(tmp_path) == tmp_path / "quality_reports"
    monkeypatch.setenv("QUALITY_REPORTS_DIR", "rapporti")   # relativo: rispetto a base_dir
    assert qualita.cartella_rapporti(tmp_path) == tmp_path / "rapporti"
    monkeypatch.setenv("QUALITY_REPORTS_DIR", "/tmp/rapporti")
    assert qualita.cartella_rapporti(tmp_path) == Path("/tmp/rapporti")
