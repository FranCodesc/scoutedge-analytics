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
    df = df_raw.drop_duplicates().copy()

    # normalizzazione nationality
    df['nationality'] = df['nationality'].str.strip().str.title()

    # market_value_eur: stringa mista -> float
    df['market_value_eur'] = df['market_value_eur'].apply(_parse_market_value)

    # date miste -> datetime
    df['observation_date'] = df['observation_date'].apply(_parse_mixed_date)
    df['contract_expiry'] = df['contract_expiry'].apply(_parse_mixed_date)

    # correzione anomalie di range (pattern sistematici, non semplici outlier)
    df.loc[df['pass_accuracy_pct'] > 100, 'pass_accuracy_pct'] /= 2
    df['sprint_speed_kmh'] = df['sprint_speed_kmh'].abs()
    df.loc[df['height_cm'] > 210, 'height_cm'] /= 10

    # imputazione valori mancanti (mediana per ruolo/stagione)
    cols_da_imputare = ['weight_kg', 'xg', 'xa', 'pass_accuracy_pct', 'sprint_speed_kmh', 'injury_days_last_season']
    for col in cols_da_imputare:
        df[col] = df.groupby(['position', 'season'])[col].transform(lambda x: x.fillna(x.median()))

    # traslitterazione nomi giapponesi (mappatura Hepburn manuale, non unidecode)
    df['player_name'] = df['player_name'].replace(MAPPA_CORREZIONE_NOMI)

    return df