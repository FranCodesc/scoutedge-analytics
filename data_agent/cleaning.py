import pandas as pd


MAPPA_CORREZIONE_NOMI = {
    '伊藤 裕太': 'Ito Yuta',
    '池田 英樹': 'Ikeda Hideki',
    '吉田 智也': 'Yoshida Tomoya',
    '吉田 直人': 'Yoshida Naoto',
    '松本 学': 'Matsumoto Manabu',
    '佐藤 淳': 'Sato Jun',
    '林 拓真': 'Hayashi Takuma',
    '前田 健一': 'Maeda Kenichi',
    '佐藤 裕太': 'Sato Yuta',
}

CLUB_CANONICI = [
    "Altopiano Sporting", "Arena Meridiana FC", "Atletico Serrano", "Baia Dorata FC",
    "Borgo Union", "Cima Bianca FC", "Costa Azzurra FC", "Delta Sporting Club",
    "Fiume Rosso AC", "Foresta Nera AC", "Isola Verde United", "Lago Blu United",
    "Monte Grigio SC", "Nord Stella FC", "Pineta Calcio", "Ponte Vecchio FC",
    "Portofino AC", "Radura United", "Real Cascata FC", "Rocca Sportiva",
    "Scogliera AC", "Stelluccia Sporting", "Torretta United", "Vallata Calcio",
    "Vigneto Calcio",
]

# chiave normalizzata (senza spazi di troppo, tutto minuscolo) -> grafia canonica
_CLUB_LOOKUP = {" ".join(nome.split()).casefold(): nome for nome in CLUB_CANONICI}


def _normalize_club(value):
    chiave = " ".join(str(value).split()).casefold()
    try:
        return _CLUB_LOOKUP[chiave]
    except KeyError:
        raise ValueError(f"Club sconosciuto nel dataset: {value!r}") from None


def _parse_market_value(value):
    value = str(value).strip()
    if ',' in value and '.' in value:
        # formato italiano: punti = migliaia, virgola = decimali
        value = value.replace('.', '').replace(',', '.')
    return float(value)


def _parse_mixed_date(value):
    value = str(value).strip()
    # prova prima il formato ISO, poi quello GG/MM/AAAA
    try:
        return pd.to_datetime(value, format='%Y-%m-%d')
    except ValueError:
        return pd.to_datetime(value, format='%d/%m/%Y')


def clean_scouting_data(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Applica la procedura di cleaning descritta nella sezione 6 di platform_handbook.md."""
    df = df_raw.copy()

    # normalizzazione nationality
    df['nationality'] = df['nationality'].str.strip().str.title()

    # normalizzazione club: mappatura canonica case-insensitive (non .title(), che rovinerebbe le sigle)
    df['club'] = df['club'].apply(_normalize_club)

    # market_value_eur: stringa mista -> float
    df['market_value_eur'] = df['market_value_eur'].apply(_parse_market_value)

    # date miste -> datetime
    df['observation_date'] = df['observation_date'].apply(_parse_mixed_date)
    df['contract_expiry'] = df['contract_expiry'].apply(_parse_mixed_date)

    # correzione anomalie di range (pattern sistematici, non semplici outlier)
    df.loc[df['pass_accuracy_pct'] > 100, 'pass_accuracy_pct'] /= 2
    df['sprint_speed_kmh'] = df['sprint_speed_kmh'].abs()
    df.loc[df['height_cm'] > 210, 'height_cm'] /= 10

    # traslitterazione nomi giapponesi (mappatura Hepburn manuale, non unidecode)
    df['player_name'] = df['player_name'].replace(MAPPA_CORREZIONE_NOMI)

    # deduplica: DOPO tutte le normalizzazioni (righe uguali nella sostanza ma scritte
    # in modo diverso diventano identiche) e PRIMA dell'imputazione (le mediane non
    # devono essere calcolate su righe doppie)
    df = df.drop_duplicates()

    # imputazione valori mancanti (mediana per ruolo/stagione)
    cols_da_imputare = ['weight_kg', 'xg', 'xa', 'pass_accuracy_pct', 'sprint_speed_kmh', 'injury_days_last_season']
    for col in cols_da_imputare:
        df[col] = df.groupby(['position', 'season'])[col].transform(lambda x: x.fillna(x.median()))


    #controlli di sicurezza
    assert df['club'].nunique() == len(CLUB_CANONICI), "Il cleaning dei club non ha prodotto i club attesi"
    assert df.duplicated().sum() == 0, "Restano righe duplicate dopo il cleaning"
    
    return df