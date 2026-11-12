"""Schema e controlli di qualità del dataset di scouting (data/scouting_data.csv).

Due controlli, entrambi eseguiti all'avvio del data agent:
- in ingresso, sul CSV grezzo: le colonne attese ci sono tutte (quelle in più si segnalano);
- in uscita, sul dataframe pulito: tipi, intervalli, domini, valori mancanti e relazioni
  tra colonne. Se qualcosa non torna, l'errore elenca TUTTE le violazioni.
I limiti numerici sono di plausibilità: abbastanza larghi da non fermare dati veri,
abbastanza stretti da prendere gli errori che la pulizia corregge (percentuali oltre 100,
altezze con uno zero in più, velocità negative). Ogni limite dichiara il motivo e la fonte;
i valori osservati e il margine sui dati reali compaiono nel rapporto di qualità (qualita.py).
"""

from typing import NamedTuple

import pandas as pd

from cleaning import CLUB_CANONICI, _strip_titles

COLONNE_ATTESE = [
    "player_id", "player_name", "club", "nationality", "date_of_birth", "position",
    "preferred_foot", "height_cm", "weight_kg", "season", "matches_played",
    "minutes_played", "goals", "assists", "xg", "xa", "pass_accuracy_pct",
    "duels_won_pct", "aerial_duels_won_pct", "tackles_won", "key_passes",
    "dribbles_completed", "yellow_cards", "red_cards", "distance_covered_km",
    "sprint_speed_kmh", "saves", "save_pct", "clean_sheets", "market_value_eur",
    "contract_expiry", "scout_rating", "injury_days_last_season", "observation_date",
    "scout_name",
]

# Tipo atteso nel dataframe pulito. "intero" = tipo intero; "numero" = intero o decimale
# (una colonna numerica può essere decimale solo perché ha valori mancanti o imputati).
TIPI = {
    "player_id": "intero", "player_name": "testo", "club": "testo",
    "nationality": "testo", "date_of_birth": "testo", "position": "testo",
    "preferred_foot": "testo", "height_cm": "numero", "weight_kg": "numero",
    "season": "testo", "matches_played": "intero", "minutes_played": "intero",
    "goals": "intero", "assists": "intero", "xg": "numero", "xa": "numero",
    "pass_accuracy_pct": "numero", "duels_won_pct": "numero",
    "aerial_duels_won_pct": "numero", "tackles_won": "intero", "key_passes": "intero",
    "dribbles_completed": "intero", "yellow_cards": "intero", "red_cards": "intero",
    "distance_covered_km": "numero", "sprint_speed_kmh": "numero", "saves": "numero",
    "save_pct": "numero", "clean_sheets": "numero", "market_value_eur": "numero",
    "contract_expiry": "data", "scout_rating": "intero",
    "injury_days_last_season": "numero", "observation_date": "data",
    "scout_name": "testo",
}


class Limite(NamedTuple):
    """Un limite di plausibilità: estremi inclusi (None = nessun limite da quel lato), il
    motivo e la fonte. La fonte inizia con una delle voci di FONTI; più fonti si separano
    con ";"."""
    minimo: object
    massimo: object
    motivo: str
    fonte: str


# Da dove viene un limite. "ordine di grandezza" = valore reale non verificato con una
# fonte citabile: lo si dichiara come tale invece di dare un numero preciso.
FONTI = ("definizione", "regola del gioco", "ordine di grandezza", "pulizia")

_CONTEGGIO = Limite(0, None, "conteggio non negativo; nessun massimo, perché nessuna fonte "
                    "dà un tetto: i valori alti li segnala il rapporto di qualità",
                    "definizione (manuale §4)")
_SOMMA_DI_PROBABILITA = Limite(0, None, "somma di probabilità, quindi non negativa; nessun "
                               "massimo: i valori alti li segnala il rapporto di qualità",
                               "definizione (manuale §3.2, §4)")
_PERCENTUALE = Limite(0, 100, "percentuale", "definizione (manuale §4)")

# Intervalli ammessi per colonna.
INTERVALLI = {
    "player_id": Limite(1, None, "identificatore intero positivo",
                        "definizione (chiave del dataset)"),
    "scout_rating": Limite(1, 99, "scala del rating", "definizione (manuale §3.1, §4)"),
    "pass_accuracy_pct": Limite(
        0, 100, "percentuale; i valori sopra 100 li dimezza la pulizia: se restano sopra "
        "100 è un errore diverso", "definizione (manuale §4, §6 punto 6); pulizia"),
    "duels_won_pct": _PERCENTUALE,
    "aerial_duels_won_pct": _PERCENTUALE,
    "save_pct": Limite(0, 100, "percentuale, solo per i portieri", "definizione (manuale §4)"),
    "height_cm": Limite(
        150, 220, "i calciatori professionisti più bassi stanno intorno a 1,55-1,60 m, i più "
        "alti poco oltre i 2 m; la pulizia divide per 10 solo le altezze di 4 cifre, quindi "
        "un giocatore vero sopra 210 cm passa", "ordine di grandezza; pulizia"),
    "weight_kg": Limite(50, 120, "i calciatori professionisti pesano tra circa 55 kg e poco "
                        "oltre 100 kg", "ordine di grandezza"),
    "sprint_speed_kmh": Limite(
        20, 40, "le velocità di punta nel calcio stanno intorno a 36-38 km/h; i valori "
        "negativi li rende positivi la pulizia: sotto 20 è un errore diverso",
        "ordine di grandezza; pulizia"),
    "distance_covered_km": Limite(
        5, 15, "media per partita: giocatori di movimento intorno a 10-13 km, portieri molto "
        "meno", "definizione (manuale §4); ordine di grandezza"),
    "market_value_eur": Limite(
        1, 200_000_000, "stima interna sempre positiva (zero sarebbe un valore mancante); "
        "massimo all'ordine di grandezza delle valutazioni più alte del mercato",
        "definizione (manuale §8); ordine di grandezza"),
    "matches_played": Limite(
        0, 80, "38 partite sono un campionato a 20 squadre; con coppe e nazionale i più "
        "impiegati arrivano intorno a 60-70", "ordine di grandezza"),
    "minutes_played": Limite(0, None, "conteggio non negativo; il tetto viene dalla relazione "
                             "con le partite (MASSIMI_PER_PARTITA)", "definizione (manuale §4)"),
    "goals": _CONTEGGIO, "assists": _CONTEGGIO,
    "xg": _SOMMA_DI_PROBABILITA, "xa": _SOMMA_DI_PROBABILITA,
    "tackles_won": _CONTEGGIO, "key_passes": _CONTEGGIO, "dribbles_completed": _CONTEGGIO,
    "yellow_cards": Limite(0, 30, "i più ammoniti di una stagione restano sotto i 20; il tetto "
                           "per partita è in MASSIMI_PER_PARTITA", "ordine di grandezza"),
    "red_cards": Limite(0, 5, "un rosso porta squalifiche di più giornate: più di qualche "
                        "rosso in una stagione è eccezionale", "ordine di grandezza"),
    "saves": _CONTEGGIO, "clean_sheets": _CONTEGGIO,
    "injury_days_last_season": Limite(0, 365, "giorni di indisponibilità in una stagione",
                                      "definizione (manuale §4)"),
}

# Valori ammessi per le colonne a elenco chiuso.
DOMINI = {
    "position": {"CAM", "CB", "CDM", "CM", "GK", "LB", "LM", "LW", "RB", "RM", "RW", "ST"},
    "preferred_foot": {"destro", "sinistro", "ambidestro"},
    "season": {"2023/24", "2024/25", "2025/26"},
    "club": set(CLUB_CANONICI),
}

# Vuote per costruzione per chi non è portiere (manuale, sezione 4): mancanti se e solo se
# la posizione non è GK. Tutte le altre colonne non possono avere valori mancanti.
COLONNE_SOLO_PORTIERI = ["saves", "save_pct", "clean_sheets"]

# Attributi che non cambiano per lo stesso player_id (il club sì: i giocatori cambiano squadra).
ATTRIBUTI_FISSI = ["player_name", "nationality", "date_of_birth", "position", "preferred_foot"]

# Relazioni con le partite giocate: valore della colonna <= massimo × matches_played.
# I conteggi sono di stagione, quindi il controllo vale sulla media per partita.
MASSIMI_PER_PARTITA = {
    "minutes_played": Limite(None, 120, "90 minuti più 30 di supplementari; è una media "
                             "sulla stagione, il recupero delle singole partite non ci arriva",
                             "regola del gioco"),
    "yellow_cards": Limite(None, 2, "il secondo giallo nella stessa partita è un'espulsione",
                           "regola del gioco"),
    "red_cards": Limite(None, 1, "dopo un rosso il giocatore lascia la partita",
                        "regola del gioco"),
    "clean_sheets": Limite(None, 1, "una porta inviolata è una partita giocata",
                           "regola del gioco"),
}

# Età all'osservazione (anni, da date_of_birth a observation_date).
ETA_ALL_OSSERVAZIONE = Limite(15, 45, "i professionisti esordiscono intorno ai 16-17 anni "
                              "e raramente giocano oltre i 40", "ordine di grandezza")

# Finestra di una stagione AAAA/AA: (mese, giorno) di inizio nell'anno iniziale e di fine
# nell'anno dopo.
FINESTRA_STAGIONE = Limite((7, 1), (6, 30), "anno sportivo dei contratti, che scadono al 30 "
                           "giugno: un'osservazione di luglio (per esempio nei turni "
                           "preliminari) è già nella stagione nuova", "ordine di grandezza")

# Un contratto già scaduto alla data di osservazione NON è una violazione: per il manuale
# (sezione 8, FAQ) indica un giocatore svincolato o in scadenza, un segnale utile e non un
# dato sporco. Lo conta il rapporto di qualità.

# Tutti i limiti con un nome leggibile: li usano i test e il rapporto di qualità.
LIMITI = {
    **INTERVALLI,
    **{f"{col} per partita": lim for col, lim in MASSIMI_PER_PARTITA.items()},
    "età all'osservazione": ETA_ALL_OSSERVAZIONE,
    "finestra della stagione": FINESTRA_STAGIONE,
}


class SchemaError(ValueError):
    """Il dataset non rispetta lo schema. Il messaggio elenca tutte le violazioni trovate."""


def verifica_colonne_grezze(df_raw):
    """Controlla le colonne del CSV grezzo. Se ne manca qualcuna solleva SchemaError;
    restituisce l'elenco di quelle in più, da segnalare senza bloccare l'avvio."""
    mancanti = [c for c in COLONNE_ATTESE if c not in df_raw.columns]
    if mancanti:
        raise SchemaError(f"Colonne mancanti nel CSV: {', '.join(mancanti)}")
    return [c for c in df_raw.columns if c not in COLONNE_ATTESE]


def _segnala(violazioni, df, maschera, colonna, regola):
    """Aggiunge una violazione alla lista se la maschera ha righe a True. Gli esempi
    mostrano player_id (la chiave) e il valore, mai solo il nome."""
    n = int(maschera.sum())
    if n:
        righe = df.loc[maschera]
        esempi = ", ".join(
            f"player_id={pid}: {valore!r}"
            for pid, valore in zip(righe["player_id"].head(3), righe[colonna].head(3))
        )
        violazioni.append(f"{colonna}: {regola} ({n} righe; es. {esempi})")


def _finestra_stagione(stagione):
    """Inizio e fine della stagione secondo FINESTRA_STAGIONE (es. 2024/25: dal 1° luglio
    2024 al 30 giugno 2025)."""
    anno = int(stagione[:4])
    (mese_inizio, giorno_inizio), (mese_fine, giorno_fine) = FINESTRA_STAGIONE[:2]
    return (pd.Timestamp(anno, mese_inizio, giorno_inizio),
            pd.Timestamp(anno + 1, mese_fine, giorno_fine))


def eta_all_osservazione(df):
    """Età in anni alla data di osservazione. Una data di nascita non valida dà NaN (la
    segnala un altro controllo)."""
    nascita = pd.to_datetime(df["date_of_birth"], format="%Y-%m-%d", errors="coerce")
    return (df["observation_date"] - nascita).dt.days / 365.25


_CONTROLLI_TIPO = {
    "intero": pd.api.types.is_integer_dtype,
    "numero": pd.api.types.is_numeric_dtype,
    "data": pd.api.types.is_datetime64_any_dtype,
    "testo": pd.api.types.is_string_dtype,
}


def verifica_dati_puliti(df):
    """Controlla il dataframe pulito. Solleva SchemaError con TUTTE le violazioni."""
    mancanti = [c for c in COLONNE_ATTESE if c not in df.columns]
    if mancanti:
        raise SchemaError(f"Colonne mancanti nel dataframe pulito: {', '.join(mancanti)}")

    violazioni = []

    # Tipi. I controlli successivi su una colonna si fanno solo se il suo tipo è giusto:
    # confrontare un testo con un numero darebbe un errore di Python, non una violazione.
    tipo_ok = set()
    for col, tipo in TIPI.items():
        if _CONTROLLI_TIPO[tipo](df[col]):
            tipo_ok.add(col)
        else:
            violazioni.append(f"{col}: tipo atteso {tipo}, trovato {df[col].dtype}")

    # Valori mancanti: ammessi solo nelle tre colonne dei portieri, e solo per i non portieri.
    non_portiere = df["position"] != "GK"
    for col in COLONNE_ATTESE:
        if col in COLONNE_SOLO_PORTIERI:
            _segnala(violazioni, df, non_portiere & df[col].notna(), col,
                     "valorizzata per un non portiere")
            _segnala(violazioni, df, ~non_portiere & df[col].isna(), col,
                     "mancante per un portiere")
        else:
            _segnala(violazioni, df, df[col].isna(), col, "valori mancanti non ammessi")

    # Intervalli numerici. I mancanti non sono violazioni di intervallo: sono già segnalati sopra.
    for col, limite in INTERVALLI.items():
        if col not in tipo_ok:
            continue
        if limite.minimo is not None:
            _segnala(violazioni, df, df[col] < limite.minimo, col, f"minore di {limite.minimo}")
        if limite.massimo is not None:
            _segnala(violazioni, df, df[col] > limite.massimo, col,
                     f"maggiore di {limite.massimo}")

    # Domini a elenco chiuso.
    for col, ammessi in DOMINI.items():
        _segnala(violazioni, df, df[col].notna() & ~df[col].isin(ammessi), col,
                 "valore fuori dall'elenco ammesso")
    n_club = df["club"].nunique()
    if n_club != len(CLUB_CANONICI):
        violazioni.append(f"club: attesi {len(CLUB_CANONICI)} club distinti, trovati {n_club}")

    # Nessuna riga completamente identica a un'altra.
    _segnala(violazioni, df, df.duplicated(), "player_id",
             "riga identica a un'altra")

    # Relazioni tra colonne.
    for col, limite in MASSIMI_PER_PARTITA.items():
        if {col, "matches_played"} <= tipo_ok:
            _segnala(violazioni, df, df[col] > df["matches_played"] * limite.massimo, col,
                     f"più di {limite.massimo} per partita giocata")
    if "observation_date" in tipo_ok:
        for stagione in DOMINI["season"]:
            inizio, fine = _finestra_stagione(stagione)
            fuori = (df["season"] == stagione) & (
                (df["observation_date"] < inizio) | (df["observation_date"] > fine))
            _segnala(violazioni, df, fuori, "observation_date",
                     f"fuori dalla stagione {stagione} ({inizio.date()} .. {fine.date()})")
    if {"date_of_birth", "observation_date"} <= tipo_ok:
        eta = eta_all_osservazione(df)
        _segnala(violazioni, df,
                 (eta < ETA_ALL_OSSERVAZIONE.minimo) | (eta > ETA_ALL_OSSERVAZIONE.massimo),
                 "date_of_birth",
                 f"età all'osservazione fuori da {ETA_ALL_OSSERVAZIONE.minimo}-"
                 f"{ETA_ALL_OSSERVAZIONE.massimo} anni")
    for col in ATTRIBUTI_FISSI:
        valori_per_giocatore = df.groupby("player_id")[col].nunique()
        incoerenti = valori_per_giocatore[valori_per_giocatore > 1].index
        _segnala(violazioni, df, df["player_id"].isin(incoerenti), col,
                 "valore diverso per lo stesso player_id")

    # Qualità dei testi: ciò che la pulizia deve aver garantito.
    for col in [c for c, tipo in TIPI.items() if tipo == "testo" and c in tipo_ok]:
        s = df[col]
        _segnala(violazioni, df,
                 s.notna() & ((s != s.str.strip()) | s.str.contains("  ", regex=False)),
                 col, "spazi iniziali, finali o doppi")
    if "player_name" in tipo_ok:
        nomi = df["player_name"]
        _segnala(violazioni, df, nomi.notna() & (nomi.apply(_strip_titles) != nomi),
                 "player_name", "titolo o qualifica rimasti nel nome")
        _segnala(violazioni, df,
                 nomi.str.contains(r"[\u3040-\u30ff\u3400-\u9fff]", regex=True, na=False),
                 "player_name", "caratteri non latini rimasti nel nome")
    if "date_of_birth" in tipo_ok:
        data_ok = pd.to_datetime(df["date_of_birth"], format="%Y-%m-%d", errors="coerce")
        _segnala(violazioni, df, data_ok.isna(), "date_of_birth",
                 "non è una data nel formato AAAA-MM-GG")

    if violazioni:
        raise SchemaError(
            f"Il dataset pulito non rispetta lo schema ({len(violazioni)} violazioni):\n- "
            + "\n- ".join(violazioni))
