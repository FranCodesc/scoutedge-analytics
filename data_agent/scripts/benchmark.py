"""Benchmark del data agent su dataset di dimensioni crescenti: pandas, DuckDB e SQLite.

Per ogni dimensione (1x = il CSV reale, 10x, 100x...) misura, in un processo separato così
che il picco di memoria di una dimensione non contamini la successiva:
- avvio: read_csv, clean_scouting_data, verifica_dati_puliti (mediana di N ripetizioni);
- memoria: dataframe pulito (memory_usage deep) e picco del processo durante l'avvio;
- domande rappresentative, scritte come codice pandas deterministico (nessun modello) e
  come SQL su DuckDB (sul dataframe, su una tabella DuckDB e su un file Parquet) e su
  SQLite (modulo sqlite3 della libreria standard: in memoria, su file e su file con
  indici), con controllo automatico che i risultati siano uguali;
- l'alternativa per l'avvio (caricare i dati già puliti da Parquet o da SQLite) e la memoria
  di un processo che usa solo DuckDB e di uno che usa solo SQLite.
Il risultato di una corsa è un file JSON; il riepilogo leggibile lo produce
benchmark_riepilogo.py. Nessuna chiamata al modello, nessuna chiave.

Uso (da data_agent/, con il venv attivo):
    python scripts/benchmark.py                          # 1x, 10x, 100x
    python scripts/benchmark.py --dimensioni 1 10        # scelta delle dimensioni
    python scripts/benchmark.py --ripetizioni 2          # prova veloce
"""

import argparse
import gc
import json
import os
import platform
import resource
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cleaning import clean_scouting_data  # noqa: E402
from dataset_sintetico import CARTELLA_PREDEFINITA, CSV_REALE, genera  # noqa: E402
from schema import verifica_dati_puliti  # noqa: E402

CARTELLA_RISULTATI = Path(__file__).resolve().parent / "risultati_benchmark"
MB = 1_000_000  # tutti i valori in MB sono in milioni di byte


# ---------------------------------------------------------------------------
# Domande rappresentative. Ogni domanda esiste in due versioni con lo stesso risultato:
# pandas (come lo scriverebbe il modello, vedi il prompt di agent.py) e SQL per DuckDB.
# Gli spareggi sono espliciti (player_id, club) perché il confronto sia deterministico.
# ---------------------------------------------------------------------------

def _attuale(df):
    """Una riga per giocatore: l'osservazione più recente (a parità di data, l'ultima)."""
    return df.sort_values("observation_date", kind="stable").drop_duplicates(
        subset="player_id", keep="last")


def top10_valore_attuale(df):
    return (_attuale(df)
            .sort_values(["market_value_eur", "player_id"], ascending=[False, True])
            .head(10)[["player_id", "player_name", "market_value_eur"]])


def rating_medio_per_stagione(df):
    return df.groupby("season").agg(
        rating_medio=("scout_rating", "mean"),
        osservazioni=("scout_rating", "size")).reset_index()


def top3_cb_duelli_attuali(df):
    att = _attuale(df)
    return (att[att["position"] == "CB"]
            .sort_values(["duels_won_pct", "player_id"], ascending=[False, True])
            .head(3)[["player_id", "player_name", "duels_won_pct"]])


def giocatori_per_club(df):
    return (df.groupby("club")["player_id"].nunique().rename("giocatori").reset_index()
            .sort_values(["giocatori", "club"], ascending=[False, True]))


def giocatore_70_per_stagione(df):
    return (df[df["player_id"] == 70].groupby("season").agg(
        rating_medio=("scout_rating", "mean"),
        osservazioni=("scout_rating", "size"),
        valore_max=("market_value_eur", "max")).reset_index())


DOMANDE_PANDAS = {
    "top10_valore_attuale": top10_valore_attuale,
    "rating_medio_per_stagione": rating_medio_per_stagione,
    "top3_cb_duelli_attuali": top3_cb_duelli_attuali,
    "giocatori_per_club": giocatori_per_club,
    "giocatore_70_per_stagione": giocatore_70_per_stagione,
}

# {t} è il nome della tabella o della vista; _ord è la posizione della riga nel dataframe,
# serve a scegliere l'ultima osservazione a parità di data come fa pandas.
_ATTUALE_SQL = """WITH att AS (
    SELECT * FROM {t}
    QUALIFY row_number() OVER (PARTITION BY player_id
                               ORDER BY observation_date DESC, _ord DESC) = 1)"""

DOMANDE_SQL = {
    "top10_valore_attuale": _ATTUALE_SQL + """
    SELECT player_id, player_name, market_value_eur FROM att
    ORDER BY market_value_eur DESC, player_id LIMIT 10""",
    "rating_medio_per_stagione": """
    SELECT season, avg(scout_rating) AS rating_medio, count(*) AS osservazioni
    FROM {t} GROUP BY season ORDER BY season""",
    "top3_cb_duelli_attuali": _ATTUALE_SQL + """
    SELECT player_id, player_name, duels_won_pct FROM att WHERE position = 'CB'
    ORDER BY duels_won_pct DESC, player_id LIMIT 3""",
    "giocatori_per_club": """
    SELECT club, count(DISTINCT player_id) AS giocatori FROM {t}
    GROUP BY club ORDER BY giocatori DESC, club""",
    "giocatore_70_per_stagione": """
    SELECT season, avg(scout_rating) AS rating_medio, count(*) AS osservazioni,
           max(market_value_eur) AS valore_max
    FROM {t} WHERE player_id = 70 GROUP BY season ORDER BY season""",
}

# SQLite non ha QUALIFY: la riga più recente per giocatore si sceglie con una sottoquery che
# numera le osservazioni e tiene la prima. Le altre tre domande sono identiche a quelle di
# DuckDB (la stessa SQL, senza estensioni).
_ATTUALE_SQLITE = """WITH att AS (
    SELECT * FROM (
        SELECT *, row_number() OVER (PARTITION BY player_id
                                     ORDER BY observation_date DESC, _ord DESC) AS _pos
        FROM {t})
    WHERE _pos = 1)"""

DOMANDE_SQLITE = {
    "top10_valore_attuale": _ATTUALE_SQLITE + """
    SELECT player_id, player_name, market_value_eur FROM att
    ORDER BY market_value_eur DESC, player_id LIMIT 10""",
    "rating_medio_per_stagione": DOMANDE_SQL["rating_medio_per_stagione"],
    "top3_cb_duelli_attuali": _ATTUALE_SQLITE + """
    SELECT player_id, player_name, duels_won_pct FROM att WHERE position = 'CB'
    ORDER BY duels_won_pct DESC, player_id LIMIT 3""",
    "giocatori_per_club": DOMANDE_SQL["giocatori_per_club"],
    "giocatore_70_per_stagione": DOMANDE_SQL["giocatore_70_per_stagione"],
}


# ---------------------------------------------------------------------------
# Strumenti di misura
# ---------------------------------------------------------------------------

def _statistiche(tempi):
    return {"mediana_s": statistics.median(tempi), "minimo_s": min(tempi),
            "massimo_s": max(tempi), "ripetizioni": len(tempi)}


def _misura(funzione, ripetizioni):
    """Una esecuzione di riscaldamento (esclusa), poi `ripetizioni` misurate."""
    funzione()
    tempi = []
    for _ in range(ripetizioni):
        t0 = time.perf_counter()
        funzione()
        tempi.append(time.perf_counter() - t0)
    return _statistiche(tempi)


def _picco_rss():
    """Picco della memoria residente del processo, in byte (macOS: byte; Linux: KB)."""
    valore = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return valore if sys.platform == "darwin" else valore * 1024


def _rss():
    import psutil
    return psutil.Process().memory_info().rss


def _uguali(a, b):
    """True se due risultati hanno colonne, righe e valori uguali (numeri con tolleranza
    relativa 1e-9, per l'ordine diverso delle somme)."""
    a, b = a.reset_index(drop=True), b.reset_index(drop=True)
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return False
    for colonna in a.columns:
        if pd.api.types.is_numeric_dtype(a[colonna]):
            if not np.allclose(a[colonna].to_numpy(float), b[colonna].to_numpy(float),
                               rtol=1e-9, equal_nan=True):
                return False
        elif not (a[colonna].astype(str).to_numpy() == b[colonna].astype(str).to_numpy()).all():
            return False
    return True


def _fedelta(report_reale, report, n):
    """Il dataset sintetico deve far lavorare la pulizia come il file vero: ogni conteggio
    intero del report deve essere N volte quello reale. Restituisce le differenze."""
    def piatto(d, prefisso=""):
        for chiave, valore in d.items():
            if isinstance(valore, dict):
                yield from piatto(valore, prefisso + chiave + ".")
            else:
                yield prefisso + chiave, valore
    reale, nuovo = dict(piatto(report_reale)), dict(piatto(report))
    escluse = ("grafie_originali", "grafie_finali", "nomi_distinti")
    return [(k, v * n, nuovo[k]) for k, v in reale.items()
            if isinstance(v, int) and not k.endswith(escluse) and nuovo[k] != v * n]

# Indici del terzo modo SQLite: uno per ciò che fanno le domande, non uno per colonna.
INDICI_SQLITE = {
    # partizione e ordine delle funzioni di finestra; il prefisso player_id serve anche al
    # filtro sul singolo giocatore
    "idx_giocatore_data": "player_id, observation_date DESC, _ord DESC",
    # raggruppamento per stagione e media: l'indice contiene già le due colonne
    "idx_stagione_rating": "season, scout_rating",
    # conteggio dei giocatori distinti per club
    "idx_club_giocatore": "club, player_id",
}


def _carica_sqlite(con, dati):
    """Scrive il dataframe nella tabella `dati` e restituisce i secondi impiegati."""
    t0 = time.perf_counter()
    dati.to_sql("dati", con, index=False)
    con.commit()
    return time.perf_counter() - t0


def _crea_indici_sqlite(con):
    """Crea gli indici di INDICI_SQLITE e aggiorna le statistiche del pianificatore
    (ANALYZE). Restituisce i secondi impiegati."""
    t0 = time.perf_counter()
    for nome, colonne in INDICI_SQLITE.items():
        con.execute(f"CREATE INDEX {nome} ON dati ({colonne})")
    con.execute("ANALYZE")
    con.commit()
    return time.perf_counter() - t0


def _domande_sqlite(con, modo, risultati_pandas, domande, ripetizioni):
    """Esegue le 5 domande su una connessione SQLite (tabella `dati`): tempo con la stessa
    `_misura` delle altre alternative e uguaglianza con pandas con la stessa `_uguali`.
    I numeri vanno in domande[nome_domanda][modo]."""
    for nome in DOMANDE_PANDAS:
        sql = DOMANDE_SQLITE[nome].format(t="dati")
        risultato = pd.read_sql_query(sql, con)
        statistiche = _misura(lambda s=sql: pd.read_sql_query(s, con), ripetizioni)
        statistiche["uguale_a_pandas"] = bool(_uguali(risultati_pandas[nome], risultato))
        domande[nome][modo] = statistiche


COLONNE_DATA = ["contract_expiry", "observation_date"]


def _sqlite_a_dataframe(file_sqlite):
    """Avvio alternativo: i dati già puliti dal file SQLite a un dataframe, con le due
    colonne di data riconvertite da testo a data. Si toglie `_ord`, che serve solo agli
    spareggi delle domande."""
    con = sqlite3.connect(file_sqlite)
    try:
        return pd.read_sql_query("SELECT * FROM dati", con,
                                 parse_dates=COLONNE_DATA).drop(columns="_ord")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Processo di misura 1: pandas, avvio, memoria e confronto con DuckDB
# ---------------------------------------------------------------------------

def _avvio_una_volta(csv):
    """read_csv, pulizia, verifica: come il lifespan di main.py. Tempi separati."""
    t0 = time.perf_counter()
    grezzo = pd.read_csv(csv)
    t1 = time.perf_counter()
    pulito, _ = clean_scouting_data(grezzo)
    t2 = time.perf_counter()
    verifica_dati_puliti(pulito)
    t3 = time.perf_counter()
    return t1 - t0, t2 - t1, t3 - t2


def lavora_pandas(csv, n, ripetizioni, thread, cartella_parquet):
    import duckdb

    rss_iniziale = _rss()

    # --- memoria: un solo avvio, in un processo che non ha ancora letto nulla.
    # Come in main.py, il dataframe grezzo resta vivo (è una variabile locale del lifespan).
    grezzo = pd.read_csv(csv)
    pulito, report = clean_scouting_data(grezzo)
    verifica_dati_puliti(pulito)
    picco = _picco_rss()
    rss_a_regime = _rss()
    memoria = {
        "dataframe_pulito_mb": pulito.memory_usage(deep=True).sum() / MB,
        "dataframe_grezzo_mb": grezzo.memory_usage(deep=True).sum() / MB,
        "rss_iniziale_mb": rss_iniziale / MB,
        "picco_rss_mb": picco / MB,
        "incremento_picco_mb": max(picco - rss_iniziale, 0) / MB,
        "rss_a_regime_con_grezzo_mb": rss_a_regime / MB,
    }
    righe_grezze, righe_pulite = len(grezzo), len(pulito)
    _, report_reale = clean_scouting_data(pd.read_csv(CSV_REALE))
    differenze = _fedelta(report_reale, report, n)
    del grezzo
    gc.collect()
    memoria["rss_senza_grezzo_mb"] = _rss() / MB

    # --- avvio: mediana su N ripetizioni dopo una di riscaldamento
    _avvio_una_volta(csv)
    prove = [_avvio_una_volta(csv) for _ in range(ripetizioni)]
    avvio = {
        "lettura": _statistiche([p[0] for p in prove]),
        "pulizia": _statistiche([p[1] for p in prove]),
        "verifica": _statistiche([p[2] for p in prove]),
        "totale": _statistiche([sum(p) for p in prove]),
    }

    # --- copia del dataframe: agent.py ne fa una a ogni richiesta
    avvio["copia_per_richiesta"] = _misura(lambda: pulito.copy(), ripetizioni)

    # --- domande con pandas
    risultati_pandas, domande = {}, {}
    for nome, funzione in DOMANDE_PANDAS.items():
        risultati_pandas[nome] = funzione(pulito)
        domande[nome] = {"pandas": _misura(lambda f=funzione: f(pulito), ripetizioni)}

    # --- domande con DuckDB, in tre modi
    con = duckdb.connect()
    con.execute(f"SET threads TO {thread}")
    con.execute("SET enable_progress_bar = false")
    con_ord = pulito.assign(_ord=np.arange(len(pulito)))  # posizione della riga, per gli spareggi

    caricamento = {}
    t0 = time.perf_counter()
    con.register("sul_dataframe", con_ord)
    caricamento["registrazione_dataframe_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    con.execute("CREATE TABLE tabella AS SELECT * FROM sul_dataframe")
    caricamento["creazione_tabella_s"] = time.perf_counter() - t0

    cartella_parquet = Path(cartella_parquet)
    cartella_parquet.mkdir(parents=True, exist_ok=True)
    parquet = cartella_parquet / f"pulito_{n}x.parquet"
    t0 = time.perf_counter()
    con.execute(f"COPY (SELECT * FROM sul_dataframe) TO '{parquet}' (FORMAT PARQUET)")
    caricamento["scrittura_parquet_s"] = time.perf_counter() - t0
    caricamento["dimensione_parquet_mb"] = parquet.stat().st_size / MB
    con.execute(f"CREATE VIEW da_parquet AS SELECT * FROM read_parquet('{parquet}')")

    modi = {"duckdb_dataframe": "sul_dataframe", "duckdb_tabella": "tabella",
            "duckdb_parquet": "da_parquet"}
    for nome in DOMANDE_PANDAS:
        for modo, tabella in modi.items():
            sql = DOMANDE_SQL[nome].format(t=tabella)
            risultato = con.execute(sql).df()
            statistiche = _misura(lambda s=sql: con.execute(s).df(), ripetizioni)
            statistiche["uguale_a_pandas"] = bool(_uguali(risultati_pandas[nome], risultato))
            domande[nome][modo] = statistiche

    # --- domande con SQLite (modulo della libreria standard), in tre modi. Il file è nella
    # cartella dei dataset sintetici. Il terzo modo riusa lo stesso file: gli indici si creano
    # dopo aver misurato il secondo.
    caricamento_sqlite = {}
    file_sqlite = cartella_parquet / f"pulito_{n}x.db"
    file_sqlite.unlink(missing_ok=True)

    con_memoria = sqlite3.connect(":memory:")
    caricamento_sqlite["to_sql_memoria_s"] = _carica_sqlite(con_memoria, con_ord)
    _domande_sqlite(con_memoria, "sqlite_memoria", risultati_pandas, domande, ripetizioni)
    con_memoria.close()

    con_file = sqlite3.connect(file_sqlite)
    caricamento_sqlite["to_sql_file_s"] = _carica_sqlite(con_file, con_ord)
    caricamento_sqlite["dimensione_file_mb"] = file_sqlite.stat().st_size / MB
    _domande_sqlite(con_file, "sqlite_file", risultati_pandas, domande, ripetizioni)

    caricamento_sqlite["creazione_indici_s"] = _crea_indici_sqlite(con_file)
    caricamento_sqlite["dimensione_file_con_indici_mb"] = file_sqlite.stat().st_size / MB
    _domande_sqlite(con_file, "sqlite_file_indici", risultati_pandas, domande, ripetizioni)
    con_file.close()

    # --- alternativa per l'avvio: dati già puliti su Parquet o su SQLite. Da SQLite il
    # dataframe deve essere uguale a quello pulito (indice a parte: riparte da 0).
    letto = _sqlite_a_dataframe(file_sqlite)
    try:
        pd.testing.assert_frame_equal(letto, pulito.reset_index(drop=True))
        sqlite_uguale = True
    except AssertionError:
        sqlite_uguale = False
    del letto
    avvio_alternativo = {
        "parquet_a_dataframe": _misura(
            lambda: duckdb.connect().execute(
                f"SELECT * FROM read_parquet('{parquet}')").df(), ripetizioni),
        "parquet_a_vista_duckdb": _misura(
            lambda: duckdb.connect().execute(
                f"CREATE VIEW v AS SELECT * FROM read_parquet('{parquet}')"), ripetizioni),
        "sqlite_a_dataframe": dict(
            _misura(lambda: _sqlite_a_dataframe(file_sqlite), ripetizioni),
            uguale_al_pulito=sqlite_uguale),
    }

    return {
        "righe_grezze": righe_grezze, "righe_pulite": righe_pulite,
        "fedelta_pulizia": {"ok": not differenze, "differenze": differenze},
        "memoria": memoria, "avvio": avvio, "avvio_alternativo": avvio_alternativo,
        "caricamento_duckdb": caricamento, "caricamento_sqlite": caricamento_sqlite,
        "domande": domande, "parquet": str(parquet), "sqlite_file": str(file_sqlite),
    }


# ---------------------------------------------------------------------------
# Processo di misura 2: solo DuckDB su Parquet, senza dataframe in memoria
# ---------------------------------------------------------------------------

def lavora_duckdb(parquet, thread):
    import duckdb

    rss_iniziale = _rss()
    con = duckdb.connect()
    con.execute(f"SET threads TO {thread}")
    con.execute(f"CREATE VIEW da_parquet AS SELECT * FROM read_parquet('{parquet}')")
    for sql in DOMANDE_SQL.values():
        con.execute(sql.format(t="da_parquet")).fetchall()
    picco, finale = _picco_rss(), _rss()
    return {"rss_iniziale_mb": rss_iniziale / MB, "picco_rss_mb": picco / MB,
            "incremento_picco_mb": max(picco - rss_iniziale, 0) / MB,
            "incremento_finale_mb": max(finale - rss_iniziale, 0) / MB}


# ---------------------------------------------------------------------------
# Processo di misura 3: solo SQLite su file, senza dataframe in memoria
# ---------------------------------------------------------------------------

def lavora_sqlite(file_sqlite):
    rss_iniziale = _rss()
    con = sqlite3.connect(file_sqlite)
    for sql in DOMANDE_SQLITE.values():
        con.execute(sql.format(t="dati")).fetchall()
    picco, finale = _picco_rss(), _rss()
    con.close()
    return {"rss_iniziale_mb": rss_iniziale / MB, "picco_rss_mb": picco / MB,
            "incremento_picco_mb": max(picco - rss_iniziale, 0) / MB,
            "incremento_finale_mb": max(finale - rss_iniziale, 0) / MB}


# ---------------------------------------------------------------------------
# Coordinatore
# ---------------------------------------------------------------------------

def _macchina_e_versioni():
    import duckdb
    import psutil
    marca = platform.processor() or platform.machine()
    if sys.platform == "darwin":
        try:
            marca = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                   capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    return {
        "sistema": platform.platform(), "processore": marca,
        "core": os.cpu_count(), "memoria_totale_gb": round(psutil.virtual_memory().total / 1e9, 1),
        "python": platform.python_version(), "pandas": pd.__version__,
        "numpy": np.__version__, "duckdb": duckdb.__version__,
        "sqlite": sqlite3.sqlite_version,
    }


def _lancia(modo, argomenti):
    """Esegue un processo di misura e ne legge il risultato da un file JSON temporaneo."""
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as f:
        uscita = f.name
    try:
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--processo", modo,
                        "--uscita-processo", uscita] + argomenti, check=True)
        return json.loads(Path(uscita).read_text())
    finally:
        os.unlink(uscita)


def coordina(args):
    cartella = Path(args.cartella)
    corsa = {"data": datetime.now().strftime("%Y-%m-%d %H:%M"), "ripetizioni": args.ripetizioni,
             "thread_duckdb": args.thread, "macchina": _macchina_e_versioni(), "dimensioni": {}}
    CARTELLA_RISULTATI.mkdir(exist_ok=True)
    percorso = CARTELLA_RISULTATI / f"corsa-{datetime.now():%Y%m%d-%H%M}.json"
    for n in args.dimensioni:
        csv = cartella / f"scouting_{n}x.csv"
        if args.rigenera or not csv.exists():
            print(f"[{n}x] genero {csv} ...", flush=True)
            genera(n, cartella)
        print(f"[{n}x] misure con pandas, DuckDB e SQLite ...", flush=True)
        comuni = ["--csv", str(csv), "--n", str(n), "--ripetizioni", str(args.ripetizioni),
                  "--thread", str(args.thread), "--cartella", str(cartella)]
        risultato = _lancia("pandas", comuni)
        print(f"[{n}x] memoria di DuckDB da solo ...", flush=True)
        risultato["duckdb_da_solo"] = _lancia(
            "duckdb", ["--parquet", risultato["parquet"], "--thread", str(args.thread)])
        print(f"[{n}x] memoria di SQLite da solo ...", flush=True)
        risultato["sqlite_da_solo"] = _lancia(
            "sqlite", ["--file-sqlite", risultato["sqlite_file"]])
        # il file serve solo alla misura: si cancella e non se ne conserva il percorso
        Path(risultato.pop("sqlite_file")).unlink(missing_ok=True)
        # il parquet serve solo alla misura: si cancella e non se ne conserva il percorso
        Path(risultato.pop("parquet")).unlink(missing_ok=True)
        corsa["dimensioni"][str(n)] = risultato
        # si salva dopo ogni dimensione: se una fallisce, le precedenti non si perdono
        percorso.write_text(json.dumps(corsa, indent=2, ensure_ascii=False))

    print(f"\nRisultati salvati in {percorso}")
    _stampa(corsa)


def _stampa(corsa):
    print(f"\n{'dim':>6} {'righe':>9} {'avvio s':>8} {'df MB':>7} {'picco MB':>9} "
          f"{'domanda max s':>14} {'uguali':>7}")
    for n, r in corsa["dimensioni"].items():
        massimo = max(d["pandas"]["mediana_s"] for d in r["domande"].values())
        uguali = all(m["uguale_a_pandas"] for d in r["domande"].values()
                     for k, m in d.items() if k != "pandas")
        print(f"{n + 'x':>6} {r['righe_pulite']:>9} {r['avvio']['totale']['mediana_s']:>8.2f} "
              f"{r['memoria']['dataframe_pulito_mb']:>7.1f} "
              f"{r['memoria']['incremento_picco_mb']:>9.1f} {massimo:>14.4f} {str(uguali):>7}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dimensioni", nargs="+", type=int, default=[1, 10, 100])
    parser.add_argument("--ripetizioni", type=int, default=5)
    parser.add_argument("--thread", type=int, default=2, help="thread di DuckDB")
    parser.add_argument("--cartella", default=str(CARTELLA_PREDEFINITA))
    parser.add_argument("--rigenera", action="store_true", help="rigenera i dataset")
    # uso interno: i processi di misura
    parser.add_argument("--processo", choices=["pandas", "duckdb", "sqlite"])
    parser.add_argument("--uscita-processo")
    parser.add_argument("--csv")
    parser.add_argument("--n", type=int)
    parser.add_argument("--parquet")
    parser.add_argument("--file-sqlite")
    args = parser.parse_args()

    if args.processo == "pandas":
        r = lavora_pandas(args.csv, args.n, args.ripetizioni, args.thread, args.cartella)
        Path(args.uscita_processo).write_text(json.dumps(r))
    elif args.processo == "duckdb":
        r = lavora_duckdb(args.parquet, args.thread)
        Path(args.uscita_processo).write_text(json.dumps(r))
    elif args.processo == "sqlite":
        r = lavora_sqlite(args.file_sqlite)
        Path(args.uscita_processo).write_text(json.dumps(r))
    else:
        coordina(args)
