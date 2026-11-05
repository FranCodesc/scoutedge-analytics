"""Riepilogo leggibile di una corsa di benchmark.py, con la regola di decisione applicata.

Legge il file JSON di una corsa e scrive accanto un file Markdown con: macchina e versioni,
tabella dimensione x misura, domande pandas contro DuckDB, verifica di uguaglianza, peso
del calcolo sul tempo di una risposta del modello e, per ogni dimensione, quali soglie
sono superate e se DuckDB (o Parquet) risolve il problema.

Uso (da data_agent/):
    python scripts/benchmark_riepilogo.py                       # l'ultima corsa
    python scripts/benchmark_riepilogo.py scripts/risultati_benchmark/corsa-....json
"""

import argparse
import json
from pathlib import Path

CARTELLA_RISULTATI = Path(__file__).resolve().parent / "risultati_benchmark"
VALUTAZIONE = (Path(__file__).resolve().parents[2] / "back end" / "eval" / "risultati"
               / "corsa-20261104-1008.json")

# Regola di decisione, fissata prima di misurare e non modificabile.
SOGLIA_DOMANDA_S = 1.0     # A: una domanda con pandas oltre questo tempo
SOGLIA_DATAFRAME_MB = 50   # B1: dataframe pulito oltre questa dimensione
SOGLIA_PICCO_MB = 250      # B2: picco di memoria dell'avvio oltre questo incremento
SOGLIA_AVVIO_S = 10.0      # C: avvio (lettura + pulizia + verifica) oltre questo tempo
MIGLIORAMENTO = 2          # l'alternativa deve migliorare la misura di almeno 2 volte

MODI = ("duckdb_dataframe", "duckdb_tabella", "duckdb_parquet")
NOMI_MODI = {"duckdb_dataframe": "DuckDB sul dataframe", "duckdb_tabella": "DuckDB tabella",
             "duckdb_parquet": "DuckDB su Parquet"}

# Domanda del benchmark -> turno della valutazione automatica con il modello che le somiglia.
CORRISPONDENZA = {
    "top10_valore_attuale": "top10_con_grafico#1",
    "rating_medio_per_stagione": "media_per_stagione#1",
    "top3_cb_duelli_attuali": "cb_metodologia_e_dati#1",
    "giocatori_per_club": "numero_giocatori#1",
    "giocatore_70_per_stagione": "rating_giocatore_70#1",
}


def _t(secondi):
    return f"{secondi * 1000:.1f} ms" if secondi < 1 else f"{secondi:.2f} s"


def _tabella(intestazioni, righe):
    linee = ["| " + " | ".join(intestazioni) + " |", "|" + "---|" * len(intestazioni)]
    linee += ["| " + " | ".join(str(c) for c in riga) + " |" for riga in righe]
    return "\n".join(linee)


def valuta(r):
    """Applica la regola a una dimensione. Restituisce le misure, i criteri superati e, per
    ognuno, se l'alternativa migliora la misura di almeno MIGLIORAMENTO volte."""
    lente = {nome: d["pandas"]["mediana_s"] for nome, d in r["domande"].items()}
    piu_lenta = max(lente, key=lente.get)
    misure = {"A": lente[piu_lenta], "B1": r["memoria"]["dataframe_pulito_mb"],
              "B2": r["memoria"]["incremento_picco_mb"], "C": r["avvio"]["totale"]["mediana_s"]}
    soglie = {"A": SOGLIA_DOMANDA_S, "B1": SOGLIA_DATAFRAME_MB, "B2": SOGLIA_PICCO_MB,
              "C": SOGLIA_AVVIO_S}
    superati = [k for k in misure if misure[k] > soglie[k]]

    alternativa = {}
    if "A" in superati:
        risolve, dettagli = True, []
        for nome, tempo in lente.items():
            if tempo <= SOGLIA_DOMANDA_S:
                continue
            # solo i modi il cui risultato è uguale a pandas: altrimenti il tempo non vale
            validi = [m for m in MODI if r["domande"][nome][m]["uguale_a_pandas"]]
            if not validi:
                risolve = False
                dettagli.append(f"{nome}: nessun modo DuckDB con risultato uguale")
                continue
            migliore = min(validi, key=lambda m: r["domande"][nome][m]["mediana_s"])
            t_duck = r["domande"][nome][migliore]["mediana_s"]
            risolve &= t_duck <= tempo / MIGLIORAMENTO
            dettagli.append(f"{nome}: pandas {_t(tempo)}, {NOMI_MODI[migliore]} {_t(t_duck)}")
        alternativa["A"] = (risolve, "; ".join(dettagli))
    if "B1" in superati:
        solo = r["duckdb_da_solo"]["incremento_finale_mb"]
        alternativa["B1"] = (solo <= misure["B1"] / MIGLIORAMENTO,
                             f"dataframe {misure['B1']:.1f} MB, DuckDB su Parquet {solo:.1f} MB")
    if "B2" in superati:
        solo = r["duckdb_da_solo"]["incremento_picco_mb"]
        alternativa["B2"] = (solo <= misure["B2"] / MIGLIORAMENTO,
                             f"avvio pandas {misure['B2']:.1f} MB, DuckDB su Parquet {solo:.1f} MB")
    if "C" in superati:
        da_parquet = r["avvio_alternativo"]["parquet_a_dataframe"]["mediana_s"]
        alternativa["C"] = (da_parquet <= SOGLIA_AVVIO_S,
                            f"avvio da CSV {misure['C']:.2f} s, da Parquet già pulito {da_parquet:.2f} s")
    return misure, soglie, superati, alternativa


NOMI_CRITERI = {"A": "domanda più lenta", "B1": "dataframe pulito",
                "B2": "picco di memoria dell'avvio", "C": "avvio"}
UNITA = {"A": "s", "B1": "MB", "B2": "MB", "C": "s"}


def scrivi_riepilogo(corsa, valutazione):
    dimensioni = corsa["dimensioni"]
    m = corsa["macchina"]
    righe = [
        f"# Benchmark del data agent: pandas e DuckDB ({corsa['data']})", "",
        f"Ripetizioni per misura: {corsa['ripetizioni']} (più una di riscaldamento, esclusa); "
        f"si riporta la mediana. Thread di DuckDB: {corsa['thread_duckdb']}. "
        "I MB sono milioni di byte. Il benchmark non usa il modello.", "",
        "## Macchina e versioni", "",
        _tabella(["Voce", "Valore"], [
            ["Sistema", m["sistema"]], ["Processore", m["processore"]],
            ["Core", m["core"]], ["Memoria", f"{m['memoria_totale_gb']} GB"],
            ["Python", m["python"]], ["pandas", m["pandas"]], ["numpy", m["numpy"]],
            ["duckdb", m["duckdb"]]]), "",
        "## Regola di decisione", "",
        "Una dimensione è oltre soglia se vale almeno una condizione:", "",
        f"- **A. Domanda**: una delle domande rappresentative supera {SOGLIA_DOMANDA_S} s con pandas.",
        f"- **B1. Dataframe**: il dataframe pulito (memory_usage deep) supera {SOGLIA_DATAFRAME_MB} MB.",
        f"- **B2. Picco di avvio**: il picco di memoria dell'avvio, meno la memoria iniziale del "
        f"processo, supera {SOGLIA_PICCO_MB} MB.",
        f"- **C. Avvio**: lettura, pulizia e verifica superano {SOGLIA_AVVIO_S:g} s.", "",
        f"Si cambia solo se l'alternativa migliora la misura che ha violato la soglia di almeno "
        f"{MIGLIORAMENTO} volte (A: DuckDB più veloce; B: DuckDB su Parquet più leggero; "
        "C: avvio da Parquet già pulito sotto la soglia).", "",
        "## Avvio e memoria", "",
    ]
    ordine = sorted(dimensioni, key=int)
    righe.append(_tabella(
        ["Dimensione", "Righe pulite", "Lettura", "Pulizia", "Verifica", "Avvio totale",
         "Dataframe pulito", "Dataframe grezzo", "Picco avvio (incremento)", "Copia per richiesta"],
        [[f"{n}x", dimensioni[n]["righe_pulite"],
          _t(dimensioni[n]["avvio"]["lettura"]["mediana_s"]),
          _t(dimensioni[n]["avvio"]["pulizia"]["mediana_s"]),
          _t(dimensioni[n]["avvio"]["verifica"]["mediana_s"]),
          _t(dimensioni[n]["avvio"]["totale"]["mediana_s"]),
          f"{dimensioni[n]['memoria']['dataframe_pulito_mb']:.1f} MB",
          f"{dimensioni[n]['memoria']['dataframe_grezzo_mb']:.1f} MB",
          f"{dimensioni[n]['memoria']['incremento_picco_mb']:.1f} MB",
          _t(dimensioni[n]["avvio"]["copia_per_richiesta"]["mediana_s"])] for n in ordine]))
    righe += ["", "Il dataframe grezzo resta in memoria accanto a quello pulito, perché nel "
              "lifespan è una variabile locale.", "",
              "## Domande: pandas contro DuckDB", ""]
    for n in ordine:
        r = dimensioni[n]
        righe += [f"### {n}x ({r['righe_pulite']} righe pulite)", ""]
        righe.append(_tabella(
            ["Domanda", "pandas", "DuckDB sul dataframe", "DuckDB tabella", "DuckDB su Parquet",
             "Risultati uguali"],
            [[nome, _t(d["pandas"]["mediana_s"])]
             + [_t(d[mo]["mediana_s"]) for mo in MODI]
             + ["sì" if all(d[mo]["uguale_a_pandas"] for mo in MODI) else "NO"]
             for nome, d in r["domande"].items()]))
        c, a = r["caricamento_duckdb"], r["avvio_alternativo"]
        righe += ["", f"Caricamento, misurato a parte: registrazione del dataframe "
                  f"{_t(c['registrazione_dataframe_s'])}; creazione della tabella "
                  f"{_t(c['creazione_tabella_s'])}; scrittura del Parquet "
                  f"{_t(c['scrittura_parquet_s'])} ({c['dimensione_parquet_mb']:.1f} MB su disco). "
                  f"Avvio da Parquet già pulito: a dataframe "
                  f"{_t(a['parquet_a_dataframe']['mediana_s'])}, a vista DuckDB "
                  f"{_t(a['parquet_a_vista_duckdb']['mediana_s'])}. "
                  f"Un processo con solo DuckDB su Parquet: incremento di memoria "
                  f"{r['duckdb_da_solo']['incremento_finale_mb']:.1f} MB "
                  f"(picco {r['duckdb_da_solo']['incremento_picco_mb']:.1f} MB).", ""]

    righe += ["## Verifica di uguaglianza e fedeltà dei dataset", ""]
    righe.append(_tabella(
        ["Dimensione", "Confronti pandas/DuckDB", "Tutti uguali", "Pulizia fedele al file reale"],
        [[f"{n}x", sum(len(MODI) for _ in dimensioni[n]["domande"]),
          "sì" if all(d[mo]["uguale_a_pandas"] for d in dimensioni[n]["domande"].values()
                      for mo in MODI) else "NO",
          "sì" if dimensioni[n]["fedelta_pulizia"]["ok"] else "NO"] for n in ordine]))
    righe += ["", "Pulizia fedele: ogni conteggio del riepilogo delle correzioni (duplicati, "
              "anomalie, date e valori convertiti, valori imputati) è esattamente N volte quello "
              "del file reale.", ""]

    righe += ["## Peso del calcolo sul tempo di una risposta", ""]
    if valutazione:
        turni = valutazione["riepilogo"]["perTurno"]
        medio = valutazione["riepilogo"]["totale"]["timeMeanMs"] / 1000
        righe.append(f"Tempi di una risposta completa con il modello ({valutazione['data']}, "
                     f"{valutazione['n']} ripetizioni): media su tutte le domande {medio:.1f} s. "
                     "Quota del calcolo pandas sul tempo medio della domanda corrispondente:")
        righe.append("")
        intestazioni = ["Domanda", "Risposta del modello"] + [f"{n}x" for n in ordine]
        corpo = []
        for nome, turno in CORRISPONDENZA.items():
            modello = turni[turno]["timeMeanMs"] / 1000
            riga = [nome, f"{modello:.1f} s"]
            for n in ordine:
                quota = dimensioni[n]["domande"][nome]["pandas"]["mediana_s"] / modello * 100
                riga.append(f"{quota:.2f}%")
            corpo.append(riga)
        righe.append(_tabella(intestazioni, corpo))
        righe.append("")

    righe += ["## Soglie per dimensione", ""]
    corpo, esiti = [], {}
    for n in ordine:
        misure, soglie, superati, alternativa = valuta(dimensioni[n])
        esiti[n] = (superati, alternativa)
        celle = [f"{n}x"]
        for k in ("A", "B1", "B2", "C"):
            segno = "SUPERATA" if k in superati else "ok"
            valore = _t(misure[k]) if UNITA[k] == "s" else f"{misure[k]:.1f} MB"
            celle.append(f"{valore} ({segno}, soglia {soglie[k]:g} {UNITA[k]})")
        corpo.append(celle)
    righe.append(_tabella(
        ["Dimensione"] + [f"{k}. {NOMI_CRITERI[k]}" for k in ("A", "B1", "B2", "C")], corpo))
    righe.append("")
    for n in ordine:
        superati, alternativa = esiti[n]
        for k in superati:
            risolve, dettaglio = alternativa[k]
            righe.append(f"- {n}x, {k}: l'alternativa {'risolve' if risolve else 'NON risolve'} "
                         f"({dettaglio}).")
    righe.append("")

    entro = [n for n in ordine if not esiti[n][0]]
    fuori = [n for n in ordine if esiti[n][0]]
    righe += ["## Esito della regola", ""]
    if not fuori:
        righe.append(f"Nessuna soglia superata fino a {ordine[-1]}x "
                     f"({dimensioni[ordine[-1]]['righe_pulite']} righe pulite).")
    else:
        prima = fuori[0]
        if entro:
            righe.append(f"Nessuna soglia superata fino a {entro[-1]}x "
                         f"({dimensioni[entro[-1]]['righe_pulite']} righe pulite). "
                         f"La prima dimensione oltre soglia è {prima}x "
                         f"({dimensioni[prima]['righe_pulite']} righe pulite): "
                         f"criteri superati {', '.join(esiti[prima][0])}. "
                         f"La soglia cade quindi tra {entro[-1]}x e {prima}x.")
        else:
            righe.append(f"Già {prima}x supera le soglie: {', '.join(esiti[prima][0])}.")
    righe.append("")
    return "\n".join(righe)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("corsa", nargs="?", help="file JSON della corsa (predefinito: l'ultimo)")
    parser.add_argument("--valutazione", default=str(VALUTAZIONE),
                        help="JSON della valutazione automatica con il modello")
    args = parser.parse_args()

    percorso = Path(args.corsa) if args.corsa else sorted(CARTELLA_RISULTATI.glob("corsa-*.json"))[-1]
    corsa = json.loads(percorso.read_text())
    valutazione = None
    if Path(args.valutazione).exists():
        valutazione = json.loads(Path(args.valutazione).read_text())
    uscita = percorso.with_suffix(".md")
    uscita.write_text(scrivi_riepilogo(corsa, valutazione))
    print(f"Riepilogo scritto in {uscita}")
