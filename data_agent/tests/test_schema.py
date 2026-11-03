"""Test dello schema (schema.py): un dataframe valido passa, ogni tipo di violazione viene
rilevato e nominato nel messaggio. Si parte dal CSV reale pulito e si rompe una copia."""

import pandas as pd
import pytest

import schema


@pytest.fixture
def pulito(pulito_reale):
    df, _ = pulito_reale
    return df.reset_index(drop=True).copy()


def _violazioni(df):
    """Testo dell'errore di schema; stringa vuota se il dataframe è valido."""
    try:
        schema.verifica_dati_puliti(df)
    except schema.SchemaError as e:
        return str(e)
    return ""


def test_un_dataframe_valido_passa(pulito):
    assert _violazioni(pulito) == ""


# (descrizione, colonna, valore sbagliato messo nella prima riga, testo atteso nel messaggio)
GUASTI = [
    ("altezza troppo alta", "height_cm", 2000, "height_cm: maggiore di 210"),
    ("altezza troppo bassa", "height_cm", 100, "height_cm: minore di 150"),
    ("percentuale oltre 100", "pass_accuracy_pct", 150.0, "pass_accuracy_pct: maggiore di 100"),
    ("percentuale negativa", "duels_won_pct", -1.0, "duels_won_pct: minore di 0"),
    ("rating oltre 99", "scout_rating", 100, "scout_rating: maggiore di 99"),
    ("rating zero", "scout_rating", 0, "scout_rating: minore di 1"),
    ("velocità negativa", "sprint_speed_kmh", -5.0, "sprint_speed_kmh: minore di 20"),
    ("valore di mercato zero", "market_value_eur", 0.0, "market_value_eur: minore di 1"),
    ("troppi cartellini rossi", "red_cards", 9, "red_cards: maggiore di 5"),
    ("ruolo inesistente", "position", "XX", "position: valore fuori dall'elenco ammesso"),
    ("piede inesistente", "preferred_foot", "mancino",
     "preferred_foot: valore fuori dall'elenco ammesso"),
    ("stagione inesistente", "season", "2030/31", "season: valore fuori dall'elenco ammesso"),
    ("club inventato", "club", "Club Inventato", "club: valore fuori dall'elenco ammesso"),
    ("valore mancante", "weight_kg", None, "weight_kg: valori mancanti non ammessi"),
    ("spazio finale", "scout_name", "Elena Conti ", "scout_name: spazi iniziali, finali o doppi"),
    ("titolo nel nome", "player_name", "Dr. Mario Rossi",
     "player_name: titolo o qualifica rimasti nel nome"),
    ("nome in kanji", "player_name", "佐藤 淳",
     "player_name: caratteri non latini rimasti nel nome"),
    ("data di nascita malformata", "date_of_birth", "03/02/1992",
     "date_of_birth: non è una data nel formato AAAA-MM-GG"),
    ("osservazione fuori stagione", "observation_date", pd.Timestamp("2020-01-01"),
     "observation_date: fuori dalla stagione"),
    ("contratto scaduto all'osservazione", "contract_expiry", pd.Timestamp("2000-01-01"),
     "contract_expiry: precedente alla data di osservazione"),
    ("minuti incompatibili con le partite", "minutes_played", 100000,
     "minutes_played: più di 120 minuti per partita"),
]


@pytest.mark.parametrize(
    "colonna, valore, atteso", [g[1:] for g in GUASTI], ids=[g[0] for g in GUASTI])
def test_violazione_rilevata_e_nominata(pulito, colonna, valore, atteso):
    pulito.loc[0, colonna] = valore
    assert atteso in _violazioni(pulito)


def test_valore_di_portiere_su_un_non_portiere(pulito):
    riga = pulito.index[pulito["position"] != "GK"][0]
    pulito.loc[riga, "saves"] = 40.0
    assert "saves: valorizzata per un non portiere" in _violazioni(pulito)


def test_portiere_senza_parate(pulito):
    riga = pulito.index[pulito["position"] == "GK"][0]
    pulito.loc[riga, "saves"] = None
    assert "saves: mancante per un portiere" in _violazioni(pulito)


def test_riga_duplicata(pulito):
    con_doppione = pd.concat([pulito, pulito.iloc[[0]]], ignore_index=True)
    assert "player_id: riga identica a un'altra" in _violazioni(con_doppione)


def test_attributo_che_cambia_per_lo_stesso_giocatore(pulito):
    riga = pulito.index[pulito.duplicated("player_id", keep=False)][0]
    pulito.loc[riga, "nationality"] = "Atlantide"
    assert "nationality: valore diverso per lo stesso player_id" in _violazioni(pulito)


def test_manca_un_club(pulito):
    senza_un_club = pulito[pulito["club"] != "Vallata Calcio"]
    assert "club: attesi 25 club distinti, trovati 24" in _violazioni(senza_un_club)


def test_tipo_sbagliato(pulito):
    pulito["height_cm"] = pulito["height_cm"].astype(str)
    assert "height_cm: tipo atteso numero" in _violazioni(pulito)


def test_colonna_mancante_nel_dataframe_pulito(pulito):
    with pytest.raises(schema.SchemaError, match="Colonne mancanti nel dataframe pulito: xg"):
        schema.verifica_dati_puliti(pulito.drop(columns=["xg"]))


def test_elenca_tutte_le_violazioni(pulito):
    pulito.loc[0, "height_cm"] = 2000
    pulito.loc[1, "pass_accuracy_pct"] = 150.0
    pulito.loc[2, "position"] = "XX"
    messaggio = _violazioni(pulito)
    assert "height_cm: maggiore di 210" in messaggio
    assert "pass_accuracy_pct: maggiore di 100" in messaggio
    assert "position: valore fuori dall'elenco ammesso" in messaggio


def test_gli_esempi_usano_player_id(pulito):
    pulito.loc[0, "height_cm"] = 2000
    assert f"player_id={pulito.loc[0, 'player_id']}: 2000" in _violazioni(pulito)


def test_colonna_mancante_nel_csv_grezzo(grezzo_reale):
    with pytest.raises(schema.SchemaError, match="Colonne mancanti nel CSV: xg"):
        schema.verifica_colonne_grezze(grezzo_reale.drop(columns=["xg"]))


def test_colonna_in_piu_nel_csv_grezzo_e_solo_segnalata(grezzo_reale):
    con_colonna_extra = grezzo_reale.assign(colonna_extra=1)
    assert schema.verifica_colonne_grezze(con_colonna_extra) == ["colonna_extra"]
