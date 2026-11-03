"""Test della pulizia automatica dei grafici (conservazione di 2 ore, massimo 200 file)."""

import os
import time

import agent


def _crea_grafico(cartella, nome, eta_s, adesso):
    """Crea un file finto con data di modifica `eta_s` secondi prima di `adesso`."""
    percorso = cartella / nome
    percorso.write_bytes(b"x")
    os.utime(percorso, (adesso - eta_s, adesso - eta_s))
    return percorso


def test_cancella_i_grafici_troppo_vecchi(cartella_grafici):
    adesso = time.time()
    vecchio = _crea_grafico(cartella_grafici, "chart_00000001.png", 3 * 3600, adesso)
    recente = _crea_grafico(cartella_grafici, "chart_00000002.png", 60, adesso)

    agent.pulisci_grafici(adesso=adesso)

    assert not vecchio.exists()
    assert recente.exists()


def _cinque_grafici(cartella, adesso):
    # età crescente: il primo è il più recente, l'ultimo il più vecchio
    return [
        _crea_grafico(cartella, f"chart_0000000{i}.png", eta, adesso)
        for i, eta in enumerate([10, 20, 30, 40, 50], start=1)
    ]


def test_limite_di_file_toglie_i_piu_vecchi(cartella_grafici, monkeypatch):
    monkeypatch.setattr(agent, "MAX_GRAFICI", 3)  # limite basso: il test resta veloce
    adesso = time.time()
    file = _cinque_grafici(cartella_grafici, adesso)

    agent.pulisci_grafici(adesso=adesso)

    # restano i 3 più recenti; spariscono i 2 più vecchi
    assert [f.exists() for f in file] == [True, True, True, False, False]


def test_spazio_per_il_nuovo_grafico(cartella_grafici, monkeypatch):
    monkeypatch.setattr(agent, "MAX_GRAFICI", 3)
    adesso = time.time()
    file = _cinque_grafici(cartella_grafici, adesso)

    agent.pulisci_grafici(spazio_per_nuovo=1, adesso=adesso)

    # con un posto riservato al nuovo file ne restano 2 (poi il salvataggio porta a 3)
    assert [f.exists() for f in file] == [True, True, False, False, False]


def test_i_file_estranei_non_si_toccano(cartella_grafici):
    adesso = time.time()
    tre_ore = 3 * 3600
    grafico = _crea_grafico(cartella_grafici, "chart_00000001.png", tre_ore, adesso)
    estranei = [
        _crea_grafico(cartella_grafici, nome, tre_ore, adesso)
        for nome in ["note.txt", "chart_pippo.png", "chart_00000009.png.bak"]
    ]

    agent.pulisci_grafici(adesso=adesso)

    assert not grafico.exists()
    assert all(f.exists() for f in estranei)


def test_bordo_delle_due_ore(cartella_grafici):
    # Ora fissa e intera: nessun arrotondamento tra la data scritta sul file e quella letta,
    # così il confronto esatto sul bordo è affidabile.
    adesso = 1_700_000_000.0
    al_limite = _crea_grafico(
        cartella_grafici, "chart_00000001.png", agent.CONSERVAZIONE_GRAFICI_S, adesso)
    oltre = _crea_grafico(
        cartella_grafici, "chart_00000002.png", agent.CONSERVAZIONE_GRAFICI_S + 1, adesso)

    agent.pulisci_grafici(adesso=adesso)

    assert al_limite.exists()  # vecchio esattamente 2 ore: si cancella solo ciò che è più vecchio
    assert not oltre.exists()
    