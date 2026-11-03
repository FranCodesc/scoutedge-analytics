import pytest

import agent


@pytest.fixture
def cartella_grafici(tmp_path, monkeypatch):
    """I grafici del test finiscono in una cartella temporanea, non in data_agent/charts/."""
    monkeypatch.setattr(agent, "CHARTS_DIR", tmp_path)
    return tmp_path
