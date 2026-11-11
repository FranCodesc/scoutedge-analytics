"""Riepilogo leggibile di una corsa di benchmark.py, con la regola di decisione applicata.

Legge il file JSON di una corsa e scrive accanto un file Markdown con: macchina e versioni,
tabella dimensione x misura, domande pandas contro DuckDB e SQLite, verifica di uguaglianza, peso
del calcolo sul tempo di una risposta del modello e, per ogni dimensione, quali soglie
sono superate e se DuckDB (o Parquet) e se SQLite risolvono il problema.

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
MODI_SQLITE = ("sqlite_memoria", "sqlite_file", "sqlite_file_indici")
NOMI_MODI = {"duckdb_dataframe": "DuckDB sul dataframe", "duckdb_tabella": "DuckDB tabella",
             "duckdb_parquet": "DuckDB su Parquet", "sqlite_memoria": "SQLite in memoria",
             "sqlite_file": "SQLite su file", "sqlite_file_indici": "SQLite su file con indici"}

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


def _risolve_a(r, lente, modi):
    """Criterio A per un gruppo di modi: per ogni domanda oltre soglia, il modo con risultato
    uguale a pandas e tempo minore deve essere almeno MIGLIORAMENTO volte più veloce."""
    risolve, dettagli = True, []
    for nome, tempo in lente.items():
        if tempo <= SOGLIA_DOMANDA_S:
            continue
        # solo i modi il cui risultato è uguale a pandas: altrimenti il tempo non vale
        validi = [m for m in modi if r["domande"][nome][m]["uguale_a_pandas"]]
        if not validi:
            risolve = False
            dettagli.append(f"{nome}: nessun modo con risultato uguale")
            continue
        migliore = min(validi, key=lambda m: r["domande"][nome][m]["mediana_s"])
        t_alt = r["domande"][nome][migliore]["mediana_s"]
        risolve &= t_alt <= tempo / MIGLIORAMENTO
        dettagli.append(f"{nome}: pandas {_t(tempo)}, {NOMI_MODI[migliore]} {_t(t_alt)}")
    return risolve, "; ".join(dettagli)


def valuta(r):
    """Applica la regola a una dimensione. Restituisce le misure, i criteri superati e, per
    ognuno, se DuckDB e se SQLite migliorano la misura di almeno MIGLIORAMENTO volte."""
    lente = {nome: d["pandas"]["mediana_s"] for nome, d in r["domande"].items()}
    piu_lenta = max(lente, key=lente.get)
    misure = {"A": lente[piu_lenta], "B1": r["memoria"]["dataframe_pulito_mb"],
              "B2": r["memoria"]["incremento_picco_mb"], "C": r["avvio"]["totale"]["mediana_s"]}
    soglie = {"A": SOGLIA_DOMANDA_S, "B1": SOGLIA_DATAFRAME_MB, "B2": SOGLIA_PICCO_MB,
              "C": SOGLIA_AVVIO_S}
    superati = [k for k in misure if misure[k] > soglie[k]]

    duck, sql = r["duckdb_da_solo"], r["sqlite_da_solo"]
    alternativa = {}
    if "A" in superati:
        alternativa["A"] = {"DuckDB": _risolve_a(r, lente, MODI),
                            "SQLite": _risolve_a(r, lente, MODI_SQLITE)}
    if "B1" in superati:
        limite = misure["B1"] / MIGLIORAMENTO
        alternativa["B1"] = {
            "DuckDB": (duck["incremento_finale_mb"] <= limite,
                       f"dataframe {misure['B1']:.1f} MB, DuckDB su Parquet "
                       f"{duck['incremento_finale_mb']:.1f} MB"),
            "SQLite": (sql["incremento_finale_mb"] <= limite,
                       f"dataframe {misure['B1']:.1f} MB, SQLite su file "
                       f"{sql['incremento_finale_mb']:.1f} MB")}
    if "B2" in superati:
        limite = misure["B2"] / MIGLIORAMENTO
        alternativa["B2"] = {
            "DuckDB": (duck["incremento_picco_mb"] <= limite,
                       f"avvio pandas {misure['B2']:.1f} MB, DuckDB su Parquet "
                       f"{duck['incremento_picco_mb']:.1f} MB"),
            "SQLite": (sql["incremento_picco_mb"] <= limite,
                       f"avvio pandas {misure['B2']:.1f} MB, SQLite su file "
                       f"{sql['incremento_picco_mb']:.1f} MB")}
    if "C" in superati:
        da_parquet = r["avvio_alternativo"]["parquet_a_dataframe"]["mediana_s"]
        da_sqlite = r["avvio_alternativo"]["sqlite_a_dataframe"]["mediana_s"]
        alternativa["C"] = {
            "DuckDB": (da_parquet <= SOGLIA_AVVIO_S,
                       f"avvio da CSV {misure['C']:.2f} s, da Parquet già pulito "
                       f"{da_parquet:.2f} s"),
            "SQLite": (da_sqlite <= SOGLIA_AVVIO_S,
                       f"avvio da CSV {misure['C']:.2f} s, da SQLite già pulito "
                       f"{da_sqlite:.2f} s")}
    return misure, soglie, superati, alternativa


NOMI_CRITERI = {"A": "domanda più lenta", "B1": "dataframe pulito",
                "B2": "picco di memoria dell'avvio", "C": "avvio"}
UNITA = {"A": "s", "B1": "MB", "B2": "MB", "C": "s"}


def scrivi_riepilogo(corsa, valutazione):
    dimensioni = corsa["dimensioni"]
    m = corsa["macchina"]
    righe = [
        f"# Benchmark del data agent: pandas, DuckDB e SQLite ({corsa['data']})", "",
        f"Ripetizioni per misura: {corsa['ripetizioni']} (più una di riscaldamento, esclusa); "
        f"si riporta la mediana. Thread di DuckDB: {corsa['thread_duckdb']}. "
        "I MB sono milioni di byte. Il benchmark non usa il modello.", "",
        "## Macchina e versioni", "",
        _tabella(["Voce", "Valore"], [
            ["Sistema", m["sistema"]], ["Processore", m["processore"]],
            ["Core", m["core"]], ["Memoria", f"{m['memoria_totale_gb']} GB"],
            ["Python", m["python"]], ["pandas", m["pandas"]], ["numpy", m["numpy"]],
            ["duckdb", m["duckdb"]], ["sqlite", m["sqlite"]]]), "",
        "## Regola di decisione", "",
        "Una dimensione è oltre soglia se vale almeno una condizione:", "",
        f"- **A. Domanda**: una delle domande rappresentative supera {SOGLIA_DOMANDA_S} s con pandas.",
        f"- **B1. Dataframe**: il dataframe pulito (memory_usage deep) supera {SOGLIA_DATAFRAME_MB} MB.",
        f"- **B2. Picco di avvio**: il picco di memoria dell'avvio, meno la memoria iniziale del "
        f"processo, supera {SOGLIA_PICCO_MB} MB.",
        f"- **C. Avvio**: lettura, pulizia e verifica superano {SOGLIA_AVVIO_S:g} s.", "",
        f"Si cambia solo se l'alternativa migliora la misura che ha violato la soglia di almeno "
        f"{MIGLIORAMENTO} volte (A: DuckDB o SQLite più veloce; B: DuckDB su Parquet o SQLite "
        "su file più leggero; C: avvio da Parquet o da SQLite già pulito sotto la soglia).", "",
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
              "## Memoria con il solo motore e avvio alternativo", "",
              "Memoria: incremento rispetto all'inizio del processo. pandas: dataframe pulito e "
              "picco dell'avvio. Solo DuckDB e solo SQLite: processo che apre il file (Parquet, "
              "oppure SQLite con gli indici), esegue le 5 domande e non ha nessun dataframe.", ""]
    corpo_memoria, corpo_avvio = [], []
    for n in ordine:
        dim = dimensioni[n]
        mem, duck, sql = dim["memoria"], dim["duckdb_da_solo"], dim["sqlite_da_solo"]
        corpo_memoria.append([
            f"{n}x", f"{mem['dataframe_pulito_mb']:.1f} MB",
            f"{mem['incremento_picco_mb']:.1f} MB",
            f"{duck['incremento_finale_mb']:.1f} MB ({duck['incremento_picco_mb']:.1f} MB)",
            f"{sql['incremento_finale_mb']:.1f} MB ({sql['incremento_picco_mb']:.1f} MB)"])
        cd, cs, alt = dim["caricamento_duckdb"], dim["caricamento_sqlite"], dim["avvio_alternativo"]
        corpo_avvio.append([
            f"{n}x", _t(dim["avvio"]["totale"]["mediana_s"]),
            _t(alt["parquet_a_dataframe"]["mediana_s"]),
            _t(alt["sqlite_a_dataframe"]["mediana_s"]),
            f"{_t(cd['scrittura_parquet_s'])} ({cd['dimensione_parquet_mb']:.1f} MB)",
            f"{_t(cs['to_sql_file_s'])} ({cs['dimensione_file_mb']:.1f} MB)",
            f"{_t(cs['creazione_indici_s'])} ({cs['dimensione_file_con_indici_mb']:.1f} MB)"])
    righe.append(_tabella(
        ["Dimensione", "pandas: dataframe pulito", "pandas: picco dell'avvio",
         "Solo DuckDB: finale (picco)", "Solo SQLite: finale (picco)"], corpo_memoria))
    righe += ["", "Avvio dai dati grezzi (lettura, pulizia, verifica) o da dati già puliti, e "
              "costo di preparare il file. Tra parentesi la dimensione del file su disco.", ""]
    righe.append(_tabella(
        ["Dimensione", "Da CSV (pandas)", "Da Parquet a dataframe", "Da SQLite a dataframe",
         "Scrittura del Parquet", "SQLite: to_sql su file", "SQLite: indici e ANALYZE"],
        corpo_avvio))
    righe += ["", "Note sulla misura di SQLite:", "",
              "- il processo che usa solo SQLite lavora sul file con gli indici;",
              "- SQLite usa la cache di pagine predefinita (circa 2 MB) e la memoria misurata "
              "non comprende la cache del sistema operativo: il confronto con il dataframe è "
              "tra un dato tutto in memoria e un dato letto dal disco a richiesta;",
              "- i tre indici sono quelli di INDICI_SQLITE in benchmark.py; il tempo della "
              "colonna indici comprende ANALYZE;",
              "- il dataframe letto da SQLite ha le date riconvertite da testo e un indice nuovo "
              "da 0 a N-1, mentre quello pulito conserva i numeri di riga del CSV; valori e tipi "
              "sono uguali.", "",
              "## Domande: pandas, DuckDB e SQLite", ""]
    for n in ordine:
        r = dimensioni[n]
        righe += [f"### {n}x ({r['righe_pulite']} righe pulite)", ""]
        righe.append(_tabella(
            ["Domanda", "pandas", "DuckDB sul dataframe", "DuckDB tabella", "DuckDB su Parquet",
             "SQLite in memoria", "SQLite su file", "SQLite su file con indici",
             "Risultati uguali"],
            [[nome, _t(d["pandas"]["mediana_s"])]
             + [_t(d[mo]["mediana_s"]) for mo in MODI + MODI_SQLITE]
             + ["sì" if all(d[mo]["uguale_a_pandas"] for mo in MODI + MODI_SQLITE) else "NO"]
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
        cs = r["caricamento_sqlite"]
        righe += [f"Caricamento in SQLite, misurato a parte: `to_sql` in memoria "
                  f"{_t(cs['to_sql_memoria_s'])}; `to_sql` su file {_t(cs['to_sql_file_s'])} "
                  f"({cs['dimensione_file_mb']:.1f} MB su disco); creazione dei 3 indici e "
                  f"ANALYZE {_t(cs['creazione_indici_s'])} (file con indici "
                  f"{cs['dimensione_file_con_indici_mb']:.1f} MB). Avvio da SQLite già pulito, "
                  f"con le due colonne di data riconvertite: "
                  f"{_t(a['sqlite_a_dataframe']['mediana_s'])} (dataframe uguale al pulito, a "
                  f"parte l'indice: "
                  f"{'sì' if a['sqlite_a_dataframe']['uguale_al_pulito'] else 'NO'}). "
                  f"Un processo con solo SQLite su file con indici: incremento di memoria "
                  f"{r['sqlite_da_solo']['incremento_finale_mb']:.1f} MB "
                  f"(picco {r['sqlite_da_solo']['incremento_picco_mb']:.1f} MB).", ""]

    righe += ["## Verifica di uguaglianza e fedeltà dei dataset", ""]
    righe.append(_tabella(
        ["Dimensione", "Confronti con pandas (DuckDB e SQLite)", "Tutti uguali",
         "Avvio da SQLite uguale al pulito", "Pulizia fedele al file reale"],
        [[f"{n}x", sum(len(MODI + MODI_SQLITE) for _ in dimensioni[n]["domande"]),
          "sì" if all(d[mo]["uguale_a_pandas"] for d in dimensioni[n]["domande"].values()
                      for mo in MODI + MODI_SQLITE) else "NO",
          "sì" if dimensioni[n]["avvio_alternativo"]["sqlite_a_dataframe"]["uguale_al_pulito"]
          else "NO",
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
            for motore, (risolve, dettaglio) in alternativa[k].items():
                righe.append(f"- {n}x, {k}, {motore}: l'alternativa "
                             f"{'risolve' if risolve else 'NON risolve'} ({dettaglio}).")
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
