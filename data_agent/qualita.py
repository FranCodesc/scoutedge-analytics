"""Rapporto di qualità dei dati, generato a ogni caricamento del data agent.

Rende osservabile cosa succede ai dati, senza bloccare l'avvio (a bloccare è lo schema):
1. percorso nella pulizia: righe prima e dopo ogni passo e valori cambiati per colonna,
   con il profilo del CSV grezzo accanto a quello del dataframe pulito;
2. profilo del dataframe pulito: per colonna mancanti, minimo, massimo, mediana e valori
   distinti; per stagione righe e giocatori;
3. limiti dello schema con il valore osservato e il margine;
4. confronto con un profilo di riferimento committato (qualita_riferimento.json): gli
   scostamenti oltre le tolleranze diventano avvisi, che non bloccano l'avvio.
Il rapporto completo si scrive in JSON nella cartella dei rapporti; nel log va un riepilogo.
Il riferimento si aggiorna solo a mano, con scripts/aggiorna_riferimento_qualita.py.
"""

import hashlib
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import schema

VERSIONE_FORMATO = 1
RIFERIMENTO = Path(__file__).resolve().parent / "qualita_riferimento.json"
RAPPORTI_DA_TENERE = 10
PREFISSO = "Qualità dei dati — "

# Colonne di testo libero: lo schema non ne chiude i valori, quindi una grafia nuova
# sfuggita alla normalizzazione passerebbe senza errori. Le controlla il confronto.
COLONNE_APERTE = ["nationality", "scout_name"]

# Tolleranze degli avvisi. Calibrate togliendo dal riferimento una stagione alla volta
# (2023/24, 2024/25, 2025/26) e trattando il dataset completo come un caricamento nuovo.
# Gli avvisi sono informativi: qualche avviso su dati buoni è atteso.
AUMENTO_RIGHE = 0.50       # una stagione nuova vale circa +34%: oltre, più di una stagione
AUMENTO_GIOCATORI = 0.20   # la rosa è stabile: 130 giocatori in ogni stagione
PUNTI_MANCANTI = 5.0       # tra le stagioni la quota di mancanti varia al massimo di 2,2 punti
QUOTA_AMPIEZZA = 0.20      # minimi e massimi: con il 20% dell'ampiezza 4, 0 e 1 avvisi sulle
                           # tre prove (con il 10% 6, 2 e 2; con lo 0% 14, 8 e 4)


def _valore(x):
    """Un valore scrivibile in JSON: numeri di numpy in numeri Python, date in testo,
    mancanti in None."""
    if x is None:
        return None
    if isinstance(x, pd.Timestamp):
        return None if pd.isna(x) else x.date().isoformat()
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, float):
        return None if math.isnan(x) else round(x, 4)
    return x


def impronta_file(percorso, dimensione_blocco=1 << 20):
    """Impronta del contenuto, indipendente dagli a capo di Windows o Unix: SHA-256 e numero
    di byte calcolati con gli a capo CRLF ridotti a LF (Git su Windows può scrivere il CSV
    con CRLF). Il file si legge a blocchi; un CR a fine blocco si tiene da parte finché non
    si vede il byte successivo."""
    h = hashlib.sha256()
    byte = 0
    sospeso = b""
    with open(percorso, "rb") as f:
        for blocco in iter(lambda: f.read(dimensione_blocco), b""):
            blocco = sospeso + blocco
            sospeso = b""
            if blocco.endswith(b"\r"):
                blocco, sospeso = blocco[:-1], b"\r"
            blocco = blocco.replace(b"\r\n", b"\n")
            h.update(blocco)
            byte += len(blocco)
    h.update(sospeso)
    byte += len(sospeso)
    return {"file": Path(percorso).name, "sha256": h.hexdigest(), "byte": byte}


def profilo(df, valori_aperti=True):
    """Statistiche del dataframe: totali, per stagione e per colonna. Con valori_aperti
    aggiunge l'elenco dei valori delle colonne aperte (serve al confronto)."""
    colonne = {}
    for col in df.columns:
        s = df[col]
        voce = {"tipo": str(s.dtype), "mancanti": int(s.isna().sum()),
                "distinti": int(s.nunique())}
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            presenti = s.dropna()
            if len(presenti):
                voce.update(minimo=_valore(presenti.min()), massimo=_valore(presenti.max()),
                            mediana=_valore(presenti.median()))
        colonne[col] = voce
    if valori_aperti:
        for col in COLONNE_APERTE:
            if col in df.columns:
                colonne[col]["valori"] = sorted(df[col].dropna().astype(str).unique().tolist())

    risultato = {"righe": len(df), "giocatori": int(df["player_id"].nunique())}
    if "season" in df.columns:
        risultato["stagioni"] = {
            str(stagione): {"righe": len(gruppo), "giocatori": int(gruppo["player_id"].nunique())}
            for stagione, gruppo in df.groupby("season", sort=True)
        }
    if all(c in df.columns and pd.api.types.is_datetime64_any_dtype(df[c])
           for c in ("contract_expiry", "observation_date")):
        # Indicatore, non errore: per il manuale (sezione 8) un contratto già scaduto
        # all'osservazione indica un giocatore svincolato o in scadenza.
        scaduti = df["contract_expiry"] < df["observation_date"]
        risultato["contratti_scaduti_all_osservazione"] = {
            "righe": int(scaduti.sum()),
            "player_id": sorted(int(p) for p in df.loc[scaduti, "player_id"].unique()),
        }
    risultato["colonne"] = colonne
    return risultato


def _famiglia(s):
    if pd.api.types.is_datetime64_any_dtype(s):
        return "data"
    if pd.api.types.is_numeric_dtype(s):
        return "numero"
    return "testo"


def percorso_pulizia(df_raw, df_clean, report):
    """Righe dopo ogni passo della pulizia e valori cambiati per colonna.

    La deduplica conserva le etichette dell'indice del grezzo, quindi le righe rimaste si
    confrontano cella per cella con le stesse righe del grezzo. Per le colonne che cambiano
    tipo (testo -> numero o data) il conteggio viene dal cleaning_report."""
    dup = report["duplicati"]
    righe_dopo_deduplica = report["righe_originali"] - dup["rimossi_totale"]
    passi = [
        {"passo": "lettura del CSV", "righe": report["righe_originali"]},
        {"passo": "normalizzazioni (testi, formati, range, nomi)",
         "righe": report["righe_originali"]},
        {"passo": "rimozione dei duplicati", "righe": righe_dopo_deduplica,
         "rimosse": dup["rimossi_totale"],
         "identiche_nel_grezzo": dup["identici_nel_file_grezzo"],
         "emerse_dopo_le_normalizzazioni": dup["emersi_dopo_le_normalizzazioni"]},
        {"passo": "imputazione con la mediana per ruolo e stagione",
         "righe": report["righe_finali"],
         "valori_imputati": sum(report["valori_imputati_con_mediana_ruolo_stagione"].values())},
    ]

    dal_report = {
        "market_value_eur": report["market_value_eur"]["righe_in_formato_italiano_convertite"],
        **report["date_formato_gg_mm_aaaa_convertite"],
    }
    rimaste = df_raw.loc[df_clean.index]
    colonne = {}
    for col in df_clean.columns:
        grezza, pulita = rimaste[col], df_clean[col]
        if _famiglia(grezza) == _famiglia(pulita):
            diversi = ~((grezza == pulita) | (grezza.isna() & pulita.isna()))
            colonne[col] = {"valori_cambiati": int(diversi.sum()),
                            "base": "righe rimaste, cella per cella"}
        else:
            colonne[col] = {"valori_cambiati": dal_report.get(col),
                            "base": "righe del CSV grezzo, dal cleaning_report"}
    return {"passi": passi, "colonne": colonne}


def limiti_osservati(df):
    """Per ogni limite dello schema: il limite, il valore osservato e il margine."""
    def voce(nome, limite, serie, unita=None):
        presenti = serie.dropna()
        oss_min = _valore(presenti.min()) if len(presenti) else None
        oss_max = _valore(presenti.max()) if len(presenti) else None
        return {
            "regola": nome, "unita": unita, "minimo": limite.minimo, "massimo": limite.massimo,
            "osservato_min": oss_min, "osservato_max": oss_max,
            "margine_min": (_valore(oss_min - limite.minimo)
                            if limite.minimo is not None and oss_min is not None else None),
            "margine_max": (_valore(limite.massimo - oss_max)
                            if limite.massimo is not None and oss_max is not None else None),
            "motivo": limite.motivo, "fonte": limite.fonte,
        }

    voci = [voce(col, lim, df[col]) for col, lim in schema.INTERVALLI.items()]
    partite = df["matches_played"].where(df["matches_played"] > 0)
    for col, lim in schema.MASSIMI_PER_PARTITA.items():
        voci.append(voce(f"{col} per partita", lim, df[col] / partite, "per partita giocata"))
    voci.append(voce("età all'osservazione", schema.ETA_ALL_OSSERVAZIONE,
                     schema.eta_all_osservazione(df), "anni"))

    # Finestra della stagione: margini in giorni tra le osservazioni e i bordi della stagione.
    lim = schema.FINESTRA_STAGIONE
    dopo_inizio, prima_fine = [], []
    for stagione, gruppo in df.groupby("season"):
        inizio, fine = schema._finestra_stagione(stagione)
        dopo_inizio.append((gruppo["observation_date"].min() - inizio).days)
        prima_fine.append((fine - gruppo["observation_date"].max()).days)
    voci.append({
        "regola": "finestra della stagione", "unita": "giorni",
        "minimo": "%02d-%02d" % lim.minimo, "massimo": "%02d-%02d" % lim.massimo,
        "osservato_min": None, "osservato_max": None,
        "margine_min": min(dopo_inizio) if dopo_inizio else None,
        "margine_max": min(prima_fine) if prima_fine else None,
        "motivo": lim.motivo, "fonte": lim.fonte,
    })
    return voci


def _esempi(df, maschera, colonna):
    """Fino a 3 esempi con la chiave: 'player_id=7: valore'."""
    righe = df.loc[maschera].head(3)
    return ", ".join(f"player_id={pid}: {valore!r}"
                     for pid, valore in zip(righe["player_id"], righe[colonna]))


def confronta(prof_grezzo, prof_pulito, riferimento, df_raw, df_clean):
    """Avvisi (non bloccanti) sugli scostamenti dal riferimento oltre le tolleranze."""
    avvisi = []

    def avviso(controllo, messaggio):
        avvisi.append({"controllo": controllo, "messaggio": messaggio})

    rif = riferimento["pulito"]
    for chiave, aumento in (("righe", AUMENTO_RIGHE), ("giocatori", AUMENTO_GIOCATORI)):
        ora, prima = prof_pulito[chiave], rif[chiave]
        if ora < prima:
            avviso(chiave, f"{chiave}: {ora} contro {prima} del riferimento (calo)")
        elif ora > prima * (1 + aumento):
            avviso(chiave, f"{chiave}: {ora} contro {prima} del riferimento "
                           f"(+{(ora / prima - 1) * 100:.0f}%, oltre +{aumento * 100:.0f}%)")

    for stagione, valori in rif.get("stagioni", {}).items():
        ora = prof_pulito.get("stagioni", {}).get(stagione, {}).get("righe", 0)
        if ora < valori["righe"]:
            avviso("righe per stagione", f"stagione {stagione}: {ora} righe contro "
                                         f"{valori['righe']} del riferimento (calo)")

    righe_grezze = prof_grezzo["righe"]
    for col, quota_rif in riferimento["mancanti_grezzo_pct"].items():
        if col not in prof_grezzo["colonne"] or not righe_grezze:
            continue
        quota = prof_grezzo["colonne"][col]["mancanti"] / righe_grezze * 100
        if quota > quota_rif + PUNTI_MANCANTI:
            avviso("mancanti", f"{col}: {quota:.1f}% di mancanti nel CSV grezzo contro "
                               f"{quota_rif:.1f}% del riferimento (oltre +{PUNTI_MANCANTI:.0f} "
                               f"punti; es. {_esempi(df_raw, df_raw[col].isna(), col)})")

    for col in COLONNE_APERTE:
        ora = set(prof_pulito["colonne"][col].get("valori", []))
        prima = set(rif["colonne"][col].get("valori", []))
        nuove, sparite = sorted(ora - prima), sorted(prima - ora)
        if nuove:
            maschera = df_clean[col].astype(str).isin(nuove)
            avviso("categorie", f"{col}: valori nuovi {nuove} ({int(maschera.sum())} righe; "
                                f"es. {_esempi(df_clean, maschera, col)})")
        if sparite:
            avviso("categorie", f"{col}: valori del riferimento assenti {sparite}")

    for col in schema.INTERVALLI:
        if col == "player_id":   # giocatori nuovi hanno id nuovi: il massimo cresce
            continue
        ora, prima = prof_pulito["colonne"].get(col, {}), rif["colonne"].get(col, {})
        if "minimo" not in ora or "minimo" not in prima:
            continue
        tolleranza = (prima["massimo"] - prima["minimo"]) * QUOTA_AMPIEZZA
        sopra, sotto = prima["massimo"] + tolleranza, prima["minimo"] - tolleranza
        if ora["massimo"] > sopra:
            maschera = df_clean[col] > sopra
            avviso("massimo", f"{col}: massimo {ora['massimo']} oltre il riferimento "
                              f"{prima['massimo']} + {QUOTA_AMPIEZZA:.0%} dell'ampiezza "
                              f"({_valore(sopra)}; "
                              f"{int(maschera.sum())} righe; es. "
                              f"{_esempi(df_clean, maschera, col)})")
        if ora["minimo"] < sotto:
            maschera = df_clean[col] < sotto
            avviso("minimo", f"{col}: minimo {ora['minimo']} sotto il riferimento "
                             f"{prima['minimo']} - {QUOTA_AMPIEZZA:.0%} dell'ampiezza "
                             f"({_valore(sotto)}; "
                             f"{int(maschera.sum())} righe; es. "
                             f"{_esempi(df_clean, maschera, col)})")
    return avvisi


def carica_riferimento(percorso=RIFERIMENTO):
    """Il profilo di riferimento, o None se il file non c'è."""
    percorso = Path(percorso)
    if not percorso.exists():
        return None
    return json.loads(percorso.read_text(encoding="utf-8"))


def profilo_di_riferimento(percorso_csv, df_raw, df_clean, report):
    """Il contenuto di qualita_riferimento.json: solo statistiche, nessuna riga del dataset."""
    imputate = report["valori_imputati_con_mediana_ruolo_stagione"]
    return {
        "versione_formato": VERSIONE_FORMATO,
        "generato_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pandas": pd.__version__,
        "csv": impronta_file(percorso_csv),
        "mancanti_grezzo_pct": {col: round(df_raw[col].isna().mean() * 100, 2)
                                for col in imputate},
        "pulito": profilo(df_clean),
    }


def crea_rapporto(percorso_csv, df_raw, df_clean, report, riferimento):
    """Il rapporto completo (un dizionario scrivibile in JSON)."""
    inizio = time.perf_counter()
    csv = impronta_file(percorso_csv)
    prof_grezzo = profilo(df_raw, valori_aperti=False)
    prof_pulito = profilo(df_clean)
    if riferimento is None:
        confronto = {"riferimento": None, "stesso_csv": None, "avvisi": []}
    else:
        confronto = {
            "riferimento": riferimento["csv"],
            "stesso_csv": riferimento["csv"]["sha256"] == csv["sha256"],
            "avvisi": confronta(prof_grezzo, prof_pulito, riferimento, df_raw, df_clean),
        }
    rapporto = {
        "versione_formato": VERSIONE_FORMATO,
        "generato_il": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "csv": csv,
        "percorso_pulizia": percorso_pulizia(df_raw, df_clean, report),
        "cleaning_report": report,
        "profilo_grezzo": prof_grezzo,
        "profilo": prof_pulito,
        "limiti": limiti_osservati(df_clean),
        "confronto": confronto,
    }
    rapporto["durata_ms"] = round((time.perf_counter() - inizio) * 1000, 1)
    return rapporto


def _migliaia(n):
    return f"{n:,}".replace(",", ".")


def riepilogo(rapporto, max_avvisi=10):
    """Le righe del riepilogo per il log."""
    csv, prof = rapporto["csv"], rapporto["profilo"]
    passi = rapporto["percorso_pulizia"]["passi"]
    righe = [
        f"CSV {csv['file']} sha256 {csv['sha256'][:12]}… ({_migliaia(csv['byte'])} byte): "
        f"{_migliaia(passi[0]['righe'])} righe grezze → {_migliaia(prof['righe'])} pulite, "
        f"{prof['giocatori']} giocatori",
        "stagioni: " + " · ".join(f"{s} {v['righe']} righe/{v['giocatori']} giocatori"
                                  for s, v in prof.get("stagioni", {}).items()),
    ]
    dedup = passi[2]
    cambiati = sorted(((c, v["valori_cambiati"]) for c, v in
                       rapporto["percorso_pulizia"]["colonne"].items() if v["valori_cambiati"]),
                      key=lambda x: -x[1])
    righe.append(f"pulizia: {dedup['rimosse']} duplicati rimossi "
                 f"({dedup['identiche_nel_grezzo']} identici, "
                 f"{dedup['emerse_dopo_le_normalizzazioni']} emersi); valori cambiati: "
                 + ", ".join(f"{c} {n}" for c, n in cambiati[:6])
                 + (f" e altre {len(cambiati) - 6} colonne" if len(cambiati) > 6 else ""))

    # Margini più stretti tra i limiti con entrambi gli estremi, in proporzione all'ampiezza.
    # Un minimo a zero o che viene da una definizione (lo zero di un conteggio, l'1 della
    # scala, il valore di mercato positivo) si salta: raggiungerlo è normale.
    stretti = []
    for v in rapporto["limiti"]:
        if v["regola"] not in schema.INTERVALLI or v["minimo"] is None \
                or v["massimo"] is None or v["osservato_max"] is None:
            continue
        ampiezza = v["massimo"] - v["minimo"]
        lati = [v["margine_max"]]
        if v["minimo"] != 0 and not v["fonte"].startswith("definizione"):
            lati.append(v["margine_min"])
        stretti.append((min(lati) / ampiezza, v))
    stretti.sort(key=lambda x: x[0])
    righe.append(f"limiti dello schema: {len(rapporto['limiti'])} regole rispettate; margini "
                 "più stretti: " + ", ".join(
                     f"{v['regola']} {v['osservato_min']}-{v['osservato_max']} "
                     f"su {v['minimo']}-{v['massimo']}" for _, v in stretti[:3]))
    scaduti = prof.get("contratti_scaduti_all_osservazione")
    if scaduti is not None:
        righe.append(f"contratti già scaduti alla data di osservazione: {scaduti['righe']} "
                     "(indicatore, non errore: manuale §8)")

    confronto = rapporto["confronto"]
    if confronto["riferimento"] is None:
        righe.append("profilo di riferimento assente: nessun confronto")
    else:
        stesso = "stesso CSV" if confronto["stesso_csv"] else "CSV diverso dal riferimento"
        avvisi = confronto["avvisi"]
        righe.append(f"confronto con il riferimento ({stesso}): {len(avvisi)} avvisi")
        righe += [f"  avviso: {a['messaggio']}" for a in avvisi[:max_avvisi]]
        if len(avvisi) > max_avvisi:
            righe.append(f"  … e altri {len(avvisi) - max_avvisi} avvisi (vedi il rapporto)")
    return [PREFISSO + r for r in righe]


def cartella_rapporti(base_dir):
    """La cartella dei rapporti: QUALITY_REPORTS_DIR se impostata, altrimenti
    <base_dir>/quality_reports. Un percorso relativo nella variabile si intende rispetto a
    base_dir (la cartella data_agent/), non alla cartella da cui si lancia uvicorn."""
    valore = os.environ.get("QUALITY_REPORTS_DIR", "").strip()
    if not valore:
        return Path(base_dir) / "quality_reports"
    percorso = Path(valore).expanduser()
    return percorso if percorso.is_absolute() else Path(base_dir) / percorso


def scrivi_rapporto(rapporto, cartella, da_tenere=RAPPORTI_DA_TENERE):
    """Scrive il rapporto in JSON e tiene solo gli ultimi `da_tenere`. Restituisce il percorso."""
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    nome = f"qualita_{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    percorso = cartella / nome
    percorso.write_text(json.dumps(rapporto, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    for vecchio in sorted(cartella.glob("qualita_*.json"))[:-da_tenere]:
        vecchio.unlink()
    return percorso


def genera_e_registra(percorso_csv, df_raw, df_clean, report, cartella,
                      riferimento_path=RIFERIMENTO):
    """Crea il rapporto, stampa il riepilogo e scrive il JSON. Se la cartella non è
    scrivibile stampa un avviso e prosegue: il rapporto non deve mai fermare l'avvio."""
    rapporto = crea_rapporto(percorso_csv, df_raw, df_clean, report,
                             carica_riferimento(riferimento_path))
    for riga in riepilogo(rapporto):
        print(riga)
    try:
        percorso = scrivi_rapporto(rapporto, cartella)
        print(f"{PREFISSO}rapporto completo: {percorso} ({rapporto['durata_ms']} ms)")
    except OSError as e:
        print(f"Attenzione: rapporto di qualità non scritto in {cartella} "
              f"({type(e).__name__}: {e}); il servizio parte lo stesso")
    return rapporto
