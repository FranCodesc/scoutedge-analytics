"""Schema e controlli di qualità del dataset di scouting (data/scouting_data.csv).

Due controlli, entrambi eseguiti all'avvio del data agent:
- in ingresso, sul CSV grezzo: le colonne attese ci sono tutte (quelle in più si segnalano);
- in uscita, sul dataframe pulito: tipi, intervalli, domini, valori mancanti e relazioni
  tra colonne. Se qualcosa non torna, l'errore elenca TUTTE le violazioni.
I limiti numerici sono di plausibilità: abbastanza larghi da non fermare dati veri,
abbastanza stretti da prendere gli errori che la pulizia corregge (percentuali oltre 100,
altezze con uno zero in più, velocità negative).
"""

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

# Intervalli ammessi (minimo, massimo), estremi inclusi; None = nessun limite da quel lato.
INTERVALLI = {
    "player_id": (1, None),
    "scout_rating": (1, 99),                       # manuale, sezione 3.1
    "pass_accuracy_pct": (0, 100), "duels_won_pct": (0, 100),
    "aerial_duels_won_pct": (0, 100), "save_pct": (0, 100),   # manuale, sezione 6
    "height_cm": (150, 210), "weight_kg": (50, 120),
    "sprint_speed_kmh": (20, 40), "distance_covered_km": (5, 15),
    "market_value_eur": (1, 200_000_000),
    "matches_played": (0, 60), "minutes_played": (0, None),
    "goals": (0, None), "assists": (0, None), "xg": (0, None), "xa": (0, None),
    "tackles_won": (0, None), "key_passes": (0, None), "dribbles_completed": (0, None),
    "yellow_cards": (0, 30), "red_cards": (0, 5),
    "saves": (0, None), "clean_sheets": (0, None),
    "injury_days_last_season": (0, 365),
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

# 90 minuti più eventuali supplementari: oltre questo, minuti e partite non tornano.
MINUTI_MASSIMI_PER_PARTITA = 120


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
    """Dal 1° agosto dell'anno iniziale al 30 giugno dell'anno dopo (es. 2024/25)."""
    anno = int(stagione[:4])
    return pd.Timestamp(anno, 8, 1), pd.Timestamp(anno + 1, 6, 30)


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
    for col, (minimo, massimo) in INTERVALLI.items():
        if col not in tipo_ok:
            continue
        if minimo is not None:
            _segnala(violazioni, df, df[col] < minimo, col, f"minore di {minimo}")
        if massimo is not None:
            _segnala(violazioni, df, df[col] > massimo, col, f"maggiore di {massimo}")

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
    if {"minutes_played", "matches_played"} <= tipo_ok:
        _segnala(violazioni, df,
                 df["minutes_played"] > df["matches_played"] * MINUTI_MASSIMI_PER_PARTITA,
                 "minutes_played",
                 f"più di {MINUTI_MASSIMI_PER_PARTITA} minuti per partita")
    if "observation_date" in tipo_ok:
        for stagione in DOMINI["season"]:
            inizio, fine = _finestra_stagione(stagione)
            fuori = (df["season"] == stagione) & (
                (df["observation_date"] < inizio) | (df["observation_date"] > fine))
            _segnala(violazioni, df, fuori, "observation_date",
                     f"fuori dalla stagione {stagione} ({inizio.date()} .. {fine.date()})")
    if {"contract_expiry", "observation_date"} <= tipo_ok:
        _segnala(violazioni, df, df["contract_expiry"] < df["observation_date"],
                 "contract_expiry", "precedente alla data di osservazione")
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
