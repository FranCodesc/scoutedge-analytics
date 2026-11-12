"""Test sul CSV reale (data/scouting_data.csv): i numeri sono quelli di docs/TEST.md."""

from pathlib import Path

import qualita
import schema


def test_forma_e_conteggi(pulito_reale):
    df, _ = pulito_reale
    assert df.shape == (1185, 35)
    assert df["player_id"].nunique() == 130
    assert df["club"].nunique() == 25
    assert df["nationality"].nunique() == 24
    assert df.groupby("season").size().to_dict() == {
        "2023/24": 380, "2024/25": 400, "2025/26": 405}


def test_report_come_in_docs_test(pulito_reale):
    _, report = pulito_reale
    assert report["righe_originali"] == 1208
    assert report["righe_finali"] == 1185
    assert report["duplicati"] == {
        "rimossi_totale": 23, "identici_nel_file_grezzo": 13, "emersi_dopo_le_normalizzazioni": 10}
    assert (report["club"]["grafie_originali"], report["club"]["grafie_finali"]) == (74, 25)
    assert (report["nationality"]["grafie_originali"],
            report["nationality"]["grafie_finali"]) == (45, 24)
    assert report["osservazioni_stesso_giorno"]["coppie"] == 5
    assert report["osservazioni_stesso_giorno"]["player_id"] == [10, 33, 60, 70, 74]
    assert (report["nomi_con_titoli_rimossi"]["giocatori"],
            report["nomi_con_titoli_rimossi"]["righe"]) == (12, 113)


def test_valori_di_riferimento(pulito_reale):
    df, _ = pulito_reale
    ultima_stagione = df[df["season"] == "2025/26"]
    assert len(ultima_stagione) == 405
    assert round(ultima_stagione["scout_rating"].mean(), 2) == 65.11
    assert df["market_value_eur"].max() == 19_102_000.0


def test_il_csv_reale_rispetta_lo_schema(grezzo_reale, pulito_reale):
    assert schema.verifica_colonne_grezze(grezzo_reale) == []
    df, _ = pulito_reale
    schema.verifica_dati_puliti(df)  # nessuna eccezione = nessuna violazione


def test_profilo_di_riferimento_coerente_con_il_csv_reale(grezzo_reale, pulito_reale):
    riferimento = qualita.carica_riferimento()
    csv = Path(__file__).resolve().parents[2] / "data" / "scouting_data.csv"
    assert riferimento["csv"] == qualita.impronta_file(csv)
    df, _ = pulito_reale
    assert qualita.confronta(qualita.profilo(grezzo_reale, valori_aperti=False),
                             qualita.profilo(df), riferimento, grezzo_reale, df) == []


def test_valori_osservati_dentro_i_limiti(pulito_reale):
    df, _ = pulito_reale
    margini = [(v["regola"], m) for v in qualita.limiti_osservati(df)
               for m in (v["margine_min"], v["margine_max"]) if m is not None]
    assert [(regola, m) for regola, m in margini if m < 0] == []
