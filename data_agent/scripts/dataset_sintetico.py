"""Genera dataset sintetici di scouting a partire dal CSV reale, a 1x, 10x, 100x...

Si produce il CSV GREZZO (con le stesse sporcizie del file vero), non quello pulito: così
la pulizia lavora come sul file vero. La copia 0 è il CSV reale; ogni copia k >= 1 ha
player_id nuovi (id + k * 1000), numeri con piccole variazioni dentro gli intervalli dello
schema e date spostate di pochi giorni dentro la stessa stagione.

Il rumore dipende dalla coppia (copia, giocatore, stagione) e non dalla singola riga: due
righe che erano duplicate nel file vero restano duplicate, quindi la pulizia ne rimuove la
stessa proporzione. Seme fisso: stessi file a ogni esecuzione.

Uso (da data_agent/):
    python scripts/dataset_sintetico.py 10 100            # scrive scouting_10x.csv, ...
    python scripts/dataset_sintetico.py 10 --cartella /percorso
"""

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cleaning import _parse_market_value  # noqa: E402

CSV_REALE = Path(__file__).resolve().parents[2] / "data" / "scouting_data.csv"
CARTELLA_PREDEFINITA = Path(tempfile.gettempdir()) / "scoutedge_benchmark"

SEME = 20261105
OFFSET_ID = 1000            # gli id reali vanno da 1 a 130: non collidono
VARIAZIONE = 0.03           # +-3% sui valori numerici
VARIAZIONE_VALORE = 0.05    # +-5% sul valore di mercato
SPOSTAMENTO_GIORNI = 10     # date spostate di al massimo +-10 giorni (restano nella stagione)
VARIAZIONE_RATING = 2       # scout_rating +-2

# Colonne decimali: (minimo, massimo, cifre decimali)
DECIMALI = {
    "weight_kg": (50, 120, 1), "xg": (0, None, 2), "xa": (0, None, 2),
    "duels_won_pct": (0, 100, 1), "aerial_duels_won_pct": (0, 100, 1),
    "distance_covered_km": (5, 15, 2), "injury_days_last_season": (0, 365, 0),
    "save_pct": (0, 100, 1),
}
# Colonne con anomalie nel file grezzo: (nome, minimo vero, massimo vero, cifre decimali)
PASS_ACCURACY = ("pass_accuracy_pct", 0, 100, 1)
VELOCITA = ("sprint_speed_kmh", 20, 40, 2)
ALTEZZA = ("height_cm", 150, 210, 0)

# Una colonna di rumore per ogni grandezza che varia.
COLONNE_RUMORE = (list(DECIMALI) + ["pass_accuracy_pct", "sprint_speed_kmh", "height_cm",
                                    "market_value_eur", "scout_rating", "minutes_played",
                                    "date"])
INDICE = {nome: i for i, nome in enumerate(COLONNE_RUMORE)}


def _varia(valori, u, minimo, massimo, decimali, ampiezza=VARIAZIONE):
    """Moltiplica per 1 +- ampiezza, limita a [minimo, massimo] e arrotonda. I mancanti
    (NaN) restano mancanti."""
    nuovi = valori * (1 + ampiezza * u)
    return nuovi.clip(lower=minimo, upper=massimo).round(decimali)


def _varia_con_anomalie(valori, u, nome, minimo, massimo, decimali):
    """Varia una colonna che nel file grezzo ha anomalie di range, rimettendole uguali.

    Si ricava il valore vero (passaggi/2, altezza/10, velocità in valore assoluto), lo si
    varia dentro i limiti e si riapplica l'errore: la proporzione di anomalie non cambia
    e la pulizia le corregge come nel file vero."""
    if nome == "pass_accuracy_pct":
        anomalo = valori > 100
        vero = valori.where(~anomalo, valori / 2)
        # un valore vero sotto 50 raddoppiato non supererebbe 100: non sarebbe più anomalo
        minimi = pd.Series(minimo, index=valori.index).where(~anomalo, 50.1)
        nuovo = _varia(vero, u, minimi, massimo, decimali)
        return nuovo.where(~anomalo, nuovo * 2)
    if nome == "height_cm":
        anomalo = valori > 210
        vero = valori.where(~anomalo, valori / 10)
        nuovo = _varia(vero, u, minimo, massimo, decimali)
        return nuovo.where(~anomalo, nuovo * 10).round().astype("int64")
    # sprint_speed_kmh: errore di segno
    negativo = valori < 0
    nuovo = _varia(valori.abs(), u, minimo, massimo, decimali)
    return nuovo.where(~negativo, -nuovo)


def _valore_mercato(testo, u):
    """Varia il valore di mercato e lo riscrive nello stesso formato della riga:
    italiano (11.415.000,00) o numero semplice (6439000). Arrotonda alle migliaia."""
    italiano = testo.astype(str).str.contains(",", regex=False)
    numeri = testo.map(_parse_market_value)
    nuovi = (numeri * (1 + VARIAZIONE_VALORE * u) / 1000).round().clip(lower=1) * 1000
    in_italiano = nuovi.map(
        lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    semplice = nuovi.astype("int64").astype(str)
    return in_italiano.where(italiano, semplice)


def _sposta_date(testo, giorni):
    """Sposta di `giorni` una colonna di date che mescola AAAA-MM-GG e GG/MM/AAAA,
    mantenendo per ogni riga il formato che aveva."""
    barra = testo.str.contains("/", regex=False)
    iso = pd.to_datetime(testo.where(~barra), format="%Y-%m-%d")
    ita = pd.to_datetime(testo.where(barra), format="%d/%m/%Y")
    data = iso.fillna(ita) + pd.to_timedelta(giorni, unit="D")
    return data.dt.strftime("%Y-%m-%d").where(~barra, data.dt.strftime("%d/%m/%Y"))


def _copia(base, k, coppia):
    """La copia numero k (>= 1) del file grezzo `base`. `coppia` è l'indice (giocatore,
    stagione) di ogni riga: righe della stessa coppia ricevono lo stesso rumore."""
    rng = np.random.default_rng([SEME, k])
    rumore = rng.uniform(-1, 1, size=(coppia.max() + 1, len(COLONNE_RUMORE)))

    def u(nome):
        return pd.Series(rumore[coppia, INDICE[nome]], index=base.index)

    nuova = base.copy()
    nuova["player_id"] = base["player_id"] + k * OFFSET_ID
    for nome, (minimo, massimo, decimali) in DECIMALI.items():
        nuova[nome] = _varia(base[nome], u(nome), minimo, massimo, decimali)
    for nome, minimo, massimo, decimali in (PASS_ACCURACY, VELOCITA, ALTEZZA):
        nuova[nome] = _varia_con_anomalie(base[nome], u(nome), nome, minimo, massimo, decimali)
    nuova["market_value_eur"] = _valore_mercato(base["market_value_eur"], u("market_value_eur"))
    nuova["scout_rating"] = (base["scout_rating"]
                             + np.rint(u("scout_rating") * VARIAZIONE_RATING)).clip(1, 99).astype("int64")
    minuti = np.rint(base["minutes_played"] * (1 + VARIAZIONE * u("minutes_played")))
    nuova["minutes_played"] = minuti.clip(lower=0, upper=base["matches_played"] * 120).astype("int64")
    giorni = np.rint(u("date") * SPOSTAMENTO_GIORNI).astype(int)
    nuova["observation_date"] = _sposta_date(base["observation_date"], giorni)
    nuova["contract_expiry"] = _sposta_date(base["contract_expiry"], giorni)
    return nuova


def genera(moltiplicatore, cartella=CARTELLA_PREDEFINITA, csv_reale=CSV_REALE):
    """Scrive scouting_<N>x.csv nella cartella e ne restituisce il percorso. Le copie si
    scrivono una alla volta: la memoria non dipende dalla dimensione."""
    base = pd.read_csv(csv_reale)
    coppia = base.groupby(["player_id", "season"], sort=False).ngroup().to_numpy()
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    percorso = cartella / f"scouting_{moltiplicatore}x.csv"
    with open(percorso, "w", newline="") as f:
        for k in range(moltiplicatore):
            blocco = base if k == 0 else _copia(base, k, coppia)
            blocco.to_csv(f, index=False, header=(k == 0))
    return percorso


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dimensioni", nargs="+", type=int, help="moltiplicatori, es. 10 100")
    parser.add_argument("--cartella", default=str(CARTELLA_PREDEFINITA))
    args = parser.parse_args()
    for n in args.dimensioni:
        print(genera(n, args.cartella))
