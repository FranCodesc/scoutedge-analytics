"""Crea o aggiorna il profilo di riferimento del rapporto di qualità (qualita_riferimento.json).

Senza argomenti confronta il CSV attuale con il riferimento in vigore e mostra gli avvisi,
senza scrivere niente. Con --conferma riscrive il riferimento: è un'azione voluta, da
rivedere e committare, mai automatica all'avvio del servizio.

Uso (da data_agent/, con il venv attivo):
    python scripts/aggiorna_riferimento_qualita.py              # anteprima
    python scripts/aggiorna_riferimento_qualita.py --conferma   # scrive il file
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qualita  # noqa: E402
from cleaning import clean_scouting_data  # noqa: E402
from schema import verifica_colonne_grezze, verifica_dati_puliti  # noqa: E402

CSV = Path(__file__).resolve().parents[2] / "data" / "scouting_data.csv"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--conferma", action="store_true", help="riscrive il riferimento")
    args = parser.parse_args()

    df_raw = pd.read_csv(CSV)
    verifica_colonne_grezze(df_raw)
    df_clean, report = clean_scouting_data(df_raw)
    verifica_dati_puliti(df_clean)  # un riferimento si crea solo da dati che passano lo schema

    attuale = qualita.carica_riferimento()
    if attuale is None:
        print(f"Riferimento assente: {qualita.RIFERIMENTO.name}")
    else:
        avvisi = qualita.confronta(qualita.profilo(df_raw, valori_aperti=False),
                                   qualita.profilo(df_clean), attuale, df_raw, df_clean)
        stesso = attuale["csv"]["sha256"] == qualita.impronta_file(CSV)["sha256"]
        print(f"Riferimento in vigore: generato il {attuale['generato_il']}, "
              f"{'stesso CSV' if stesso else 'CSV diverso'}; {len(avvisi)} avvisi")
        for avviso in avvisi:
            print(f"  avviso: {avviso['messaggio']}")

    if not args.conferma:
        print("Anteprima: nessun file scritto. Per aggiornare il riferimento: --conferma")
        return
    nuovo = qualita.profilo_di_riferimento(CSV, df_raw, df_clean, report)
    qualita.RIFERIMENTO.write_text(json.dumps(nuovo, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    print(f"Riferimento scritto: {qualita.RIFERIMENTO.name} "
          f"({qualita.RIFERIMENTO.stat().st_size} byte)")


if __name__ == "__main__":
    main()
