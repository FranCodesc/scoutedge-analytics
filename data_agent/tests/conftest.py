"""Fixture condivise tra i file di test."""

from pathlib import Path

import pandas as pd
import pytest

import agent
from cleaning import clean_scouting_data

CSV = Path(__file__).resolve().parents[2] / "data" / "scouting_data.csv"


@pytest.fixture
def cartella_grafici(tmp_path, monkeypatch):
    """I grafici del test finiscono in una cartella temporanea, non in data_agent/charts/."""
    monkeypatch.setattr(agent, "CHARTS_DIR", tmp_path)
    return tmp_path


@pytest.fixture(scope="session")
def grezzo_reale():
    """Il CSV reale così com'è, letto una volta sola. I test non devono modificarlo."""
    return pd.read_csv(CSV)


@pytest.fixture(scope="session")
def pulito_reale(grezzo_reale):
    """(dataframe pulito, report) del CSV reale, calcolato una volta sola. Chi lo vuole
    modificare ne fa prima una copia."""
    return clean_scouting_data(grezzo_reale)
