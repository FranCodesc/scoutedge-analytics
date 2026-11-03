"""Test delle funzioni pure di cleaning.py (nessuna rete, nessuna chiave)."""

import math

import pandas as pd
import pytest

from cleaning import _normalize_club, _parse_market_value, _parse_mixed_date, _strip_titles, clean_scouting_data


@pytest.mark.parametrize("grezzo, atteso", [
    (6439000, 6439000.0),            # numero semplice
    ("6439000", 6439000.0),
    ("6439000.5", 6439000.5),        # punto decimale
    ("11.415.000,00", 11415000.0),   # formato italiano: punti = migliaia, virgola = decimali
    (" 1.234,50 ", 1234.5),          # spazi attorno
    ("0", 0.0),
])
def test_parse_market_value_formati_validi(grezzo, atteso):
    assert _parse_market_value(grezzo) == atteso


@pytest.mark.parametrize("grezzo", ["abc", "", "1,5", "6.439.000"])
def test_parse_market_value_formati_non_riconosciuti(grezzo):
    # Né un numero semplice né il formato italiano completo (punto E virgola): non si
    # indovina, si segnala un errore invece di produrre un valore sbagliato.
    with pytest.raises(ValueError):
        _parse_market_value(grezzo)


def test_parse_market_value_mancante_resta_mancante():
    # Nessun errore: il valore mancante resta NaN. Lo blocca lo schema, più avanti.
    assert math.isnan(_parse_market_value(float("nan")))


NOMI = [
    ("Dr. Rene Mühle MBA.", "Rene Mühle"),       # titolo davanti e qualifica in coda, con punti
    ("Herr Hans Müller", "Hans Müller"),
    ("mr john smith", "john smith"),             # maiuscole indifferenti, il resto non si tocca
    ("Dr. Dr. Anna Rossi", "Anna Rossi"),        # più titoli di fila
    ("Luca Bianchi MBA PhD", "Luca Bianchi"),    # più qualifiche di fila
    ("Dr(a) Maria Lopez", "Maria Lopez"),
    ("Maria B.A", "Maria"),
    ("Anna  Rossi", "Anna Rossi"),               # spazi doppi normalizzati
    ("Prof. Marco Doctor", "Marco Doctor"),      # solo i termini dell'elenco
    ("Anna Dr Rossi", "Anna Dr Rossi"),          # solo alla prima e all'ultima parola
    ("Maarten Van de Velde", "Maarten Van de Velde"),   # un nome senza titoli non cambia
    ("Dr", "Dr"),                                # una parola sola non diventa mai vuota
    ("", ""),
]


@pytest.mark.parametrize("nome, atteso", NOMI)
def test_strip_titles(nome, atteso):
    assert _strip_titles(nome) == atteso


@pytest.mark.parametrize("nome, atteso", NOMI)
def test_strip_titles_e_idempotente(nome, atteso):
    # Lo schema controlla che nei nomi puliti non restino titoli: ripassare un nome
    # già pulito non deve cambiarlo.
    assert _strip_titles(_strip_titles(nome)) == _strip_titles(nome)


@pytest.mark.parametrize("grezzo", ["vallata calcio", "  VALLATA   CALCIO ", "Vallata Calcio"])
def test_normalize_club_riconduce_alla_grafia_canonica(grezzo):
    assert _normalize_club(grezzo) == "Vallata Calcio"


@pytest.mark.parametrize("grezzo", ["Club Inesistente", "", None])
def test_normalize_club_sconosciuto(grezzo):
    with pytest.raises(ValueError, match="Club sconosciuto"):
        _normalize_club(grezzo)


@pytest.mark.parametrize("grezzo", ["2025-03-04", "04/03/2025", " 2025-03-04 "])
def test_parse_mixed_date_formati_validi(grezzo):
    assert _parse_mixed_date(grezzo) == pd.Timestamp(2025, 3, 4)


def test_parse_mixed_date_giorno_prima_del_mese():
    # 03/04/2025 è il 3 aprile, non il 4 marzo: per questo i formati sono espliciti.
    assert _parse_mixed_date("03/04/2025") == pd.Timestamp(2025, 4, 3)


@pytest.mark.parametrize("grezzo", ["2025-13-01", "03-04-2025", "abc"])
def test_parse_mixed_date_formati_non_riconosciuti(grezzo):
    with pytest.raises(ValueError):
        _parse_mixed_date(grezzo)


def test_parse_mixed_date_mancante_diventa_nat():
    # Nessun errore: il valore mancante diventa NaT. Lo blocca lo schema, più avanti.
    assert pd.isna(_parse_mixed_date(float("nan")))


# --- clean_scouting_data su un piccolo DataFrame grezzo costruito a mano ---


def _riga(**modifiche):
    """Una riga grezza valida (centrocampista, stagione 2024/25): i test cambiano solo ciò che serve."""
    riga = {
        "player_id": 1, "player_name": "Mario Rossi", "club": "Vallata Calcio",
        "nationality": "Italy", "position": "CM", "season": "2024/25",
        "height_cm": 180, "weight_kg": 75.0, "xg": 1.0, "xa": 1.0,
        "pass_accuracy_pct": 80.0, "sprint_speed_kmh": 30.0,
        "injury_days_last_season": 5.0,
        "saves": float("nan"), "save_pct": float("nan"), "clean_sheets": float("nan"),
        "market_value_eur": "1000000",
        "observation_date": "2025-01-10", "contract_expiry": "2027-06-30",
    }
    riga.update(modifiche)
    return riga


@pytest.fixture
def grezzo():
    """7 righe grezze con anomalie note: dopo la pulizia ne restano 5."""
    return pd.DataFrame([
        _riga(),                                                  # r0: riferimento
        _riga(),                                                  # r1: identica a r0
        _riga(player_id=2, player_name="Dr. Luigi Verdi MBA",     # r2: titoli nel nome, club e
              club=" vallata  calcio", nationality="  italy",     #     nazionalità scritti male,
              market_value_eur="11.415.000,00", xg=4.0,           #     formato italiano,
              observation_date="10/01/2025",                      #     date GG/MM/AAAA
              contract_expiry="30/06/2027"),
        _riga(player_id=3, player_name="佐藤 淳",                   # r3: portiere, nome in kanji,
              club="ARENA MERIDIANA FC", nationality="japan",     #     tre errori di range
              position="GK", height_cm=1820, pass_accuracy_pct=160.0,
              sprint_speed_kmh=-31.0, saves=50.0, save_pct=70.0, clean_sheets=5.0),
        _riga(player_id=4, player_name="Paolo Neri",              # r4: xg mancante
              xg=float("nan"), observation_date="2025-02-01"),
        _riga(player_id=2, player_name="Dr. Luigi Verdi MBA",     # r5: come r2 solo dopo le
              xg=4.0, market_value_eur="11.415.000,00"),          #     normalizzazioni
        _riga(xg=2.0),                                            # r6: stesso giorno di r0, xg diverso
    ])


def test_dataframe_pulito_sul_dataframe_costruito_a_mano(grezzo):
    df, _ = clean_scouting_data(grezzo)
    # r1 (identica) e r5 (identica dopo le normalizzazioni) sono sparite, l'ordine resta
    assert df["player_id"].tolist() == [1, 2, 3, 4, 1]
    assert df["player_name"].tolist() == [
        "Mario Rossi", "Luigi Verdi", "Sato Jun", "Paolo Neri", "Mario Rossi"]
    assert df["club"].tolist() == [
        "Vallata Calcio", "Vallata Calcio", "Arena Meridiana FC", "Vallata Calcio", "Vallata Calcio"]
    assert df["nationality"].tolist() == ["Italy", "Italy", "Japan", "Italy", "Italy"]
    assert df["market_value_eur"].tolist() == [1000000.0, 11415000.0, 1000000.0, 1000000.0, 1000000.0]
    assert df["observation_date"].tolist()[1] == pd.Timestamp(2025, 1, 10)
    assert df["contract_expiry"].tolist()[1] == pd.Timestamp(2027, 6, 30)

    portiere = df[df["player_id"] == 3].iloc[0]
    assert portiere["pass_accuracy_pct"] == 80.0   # 160 dimezzato
    assert portiere["sprint_speed_kmh"] == 31.0    # segno corretto
    assert portiere["height_cm"] == 182            # 1820 diviso per 10

    # mediana dell'xg dei centrocampisti 2024/25 con valore: 1.0, 4.0, 2.0 → 2.0
    assert df.loc[df["player_id"] == 4, "xg"].iloc[0] == 2.0
    # saves, save_pct e clean_sheets restano vuoti per i 4 non portieri (non imputati)
    assert df["saves"].isna().sum() == 4
    assert not df.duplicated().any()


def test_report_sul_dataframe_costruito_a_mano(grezzo):
    _, report = clean_scouting_data(grezzo)
    assert report["righe_originali"] == 7
    assert report["righe_finali"] == 5
    assert report["giocatori_unici"] == 4
    assert report["duplicati"] == {
        "rimossi_totale": 2, "identici_nel_file_grezzo": 1, "emersi_dopo_le_normalizzazioni": 1}
    assert report["nationality"] == {"grafie_originali": 3, "grafie_finali": 2, "righe_modificate": 2}
    assert report["club"] == {"grafie_originali": 3, "grafie_finali": 2, "righe_modificate": 2}
    assert report["market_value_eur"] == {"righe_in_formato_italiano_convertite": 2}
    assert report["date_formato_gg_mm_aaaa_convertite"] == {"observation_date": 1, "contract_expiry": 1}
    assert report["correzioni_range"] == {
        "pass_accuracy_pct_dimezzati": 1, "sprint_speed_kmh_resi_positivi": 1,
        "height_cm_divisi_per_10": 1}
    assert report["nomi_traslitterati"] == {"righe": 1, "nomi_distinti": 1}
    assert report["nomi_con_titoli_rimossi"] == {
        "righe": 2, "giocatori": 1, "esempio": "Dr. Luigi Verdi MBA -> Luigi Verdi"}
    assert report["valori_imputati_con_mediana_ruolo_stagione"] == {
        "weight_kg": 0, "xg": 1, "xa": 0, "pass_accuracy_pct": 0,
        "sprint_speed_kmh": 0, "injury_days_last_season": 0}
    assert report["mancanti_non_imputati_non_portieri"] == {
        "saves": 4, "save_pct": 4, "clean_sheets": 4}
    assert report["osservazioni_stesso_giorno"] == {
        "coppie": 1, "righe_coinvolte": 2, "player_id": [1]}


def test_il_dataframe_grezzo_non_viene_modificato(grezzo):
    copia = grezzo.copy()
    clean_scouting_data(grezzo)
    pd.testing.assert_frame_equal(grezzo, copia)


def test_club_sconosciuto_ferma_la_pulizia():
    with pytest.raises(ValueError, match="Club sconosciuto"):
        clean_scouting_data(pd.DataFrame([_riga(club="Club Inventato")]))
