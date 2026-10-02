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


def clean_scouting_data(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Applica la procedura di cleaning descritta nella sezione 6 di platform_handbook.md.
    Restituisce (dataframe pulito, report delle correzioni).
    I conteggi delle correzioni sono riferiti alle righe del file grezzo; quelli delle
    imputazioni alle righe rimaste dopo la deduplica."""
    df = df_raw.copy()
    report = {"righe_originali": len(df_raw)}

    # normalizzazione nationality
    nat_prima = df['nationality']
    df['nationality'] = df['nationality'].str.strip().str.title()
    report['nationality'] = {
        'grafie_originali': int(nat_prima.nunique()),
        'grafie_finali': int(df['nationality'].nunique()),
        'righe_modificate': int((nat_prima != df['nationality']).sum()),
    }

    # normalizzazione club: mappatura canonica case-insensitive (non .title(), che rovinerebbe le sigle)
    club_prima = df['club']
    df['club'] = df['club'].apply(_normalize_club)
    report['club'] = {
        'grafie_originali': int(club_prima.nunique()),
        'grafie_finali': int(df['club'].nunique()),
        'righe_modificate': int((club_prima != df['club']).sum()),
    }

    # market_value_eur: stringa mista -> float
    mv = df['market_value_eur'].astype(str).str.strip()
    report['market_value_eur'] = {
        'righe_in_formato_italiano_convertite': int((mv.str.contains(',') & mv.str.contains('.', regex=False)).sum()),
    }
    df['market_value_eur'] = df['market_value_eur'].apply(_parse_market_value)

    # date miste -> datetime
    report['date_formato_gg_mm_aaaa_convertite'] = {}
    for col in ['observation_date', 'contract_expiry']:
        non_iso = pd.to_datetime(df[col].astype(str).str.strip(), format='%Y-%m-%d', errors='coerce').isna()
        report['date_formato_gg_mm_aaaa_convertite'][col] = int(non_iso.sum())
        df[col] = df[col].apply(_parse_mixed_date)

    # correzione anomalie di range (pattern sistematici, non semplici outlier)
    mask_pass = df['pass_accuracy_pct'] > 100
    mask_sprint = df['sprint_speed_kmh'] < 0
    mask_height = df['height_cm'] > 210
    report['correzioni_range'] = {
        'pass_accuracy_pct_dimezzati': int(mask_pass.sum()),
        'sprint_speed_kmh_resi_positivi': int(mask_sprint.sum()),
        'height_cm_divisi_per_10': int(mask_height.sum()),
    }
    df.loc[mask_pass, 'pass_accuracy_pct'] /= 2
    df['sprint_speed_kmh'] = df['sprint_speed_kmh'].abs()
    df.loc[mask_height, 'height_cm'] /= 10

    # traslitterazione nomi giapponesi (mappatura Hepburn manuale, non unidecode)
    mask_nomi = df['player_name'].isin(list(MAPPA_CORREZIONE_NOMI))
    report['nomi_traslitterati'] = {
        'righe': int(mask_nomi.sum()),
        'nomi_distinti': int(df.loc[mask_nomi, 'player_name'].nunique()),
    }
    df['player_name'] = df['player_name'].replace(MAPPA_CORREZIONE_NOMI)

    # deduplica: DOPO tutte le normalizzazioni (righe uguali nella sostanza ma scritte
    # in modo diverso diventano identiche) e PRIMA dell'imputazione (le mediane non
    # devono essere calcolate su righe doppie)
    righe_prima = len(df)
    df = df.drop_duplicates()
    rimossi = righe_prima - len(df)
    identici_nel_grezzo = int(df_raw.duplicated().sum())
    report['duplicati'] = {
        'rimossi_totale': rimossi,
        'identici_nel_file_grezzo': identici_nel_grezzo,
        'emersi_dopo_le_normalizzazioni': rimossi - identici_nel_grezzo,
    }

    # imputazione valori mancanti (mediana per ruolo/stagione)
    cols_da_imputare = ['weight_kg', 'xg', 'xa', 'pass_accuracy_pct', 'sprint_speed_kmh', 'injury_days_last_season']
    report['valori_imputati_con_mediana_ruolo_stagione'] = {}
    for col in cols_da_imputare:
        mancanti_prima = int(df[col].isna().sum())
        df[col] = df.groupby(['position', 'season'])[col].transform(lambda x: x.fillna(x.median()))
        report['valori_imputati_con_mediana_ruolo_stagione'][col] = mancanti_prima - int(df[col].isna().sum())

    # saves / save_pct / clean_sheets: mancanti per costruzione per i non portieri, NON imputati
    report['mancanti_non_imputati_non_portieri'] = {
        col: int(df[col].isna().sum()) for col in ['saves', 'save_pct', 'clean_sheets']
    }

    # osservazioni dello stesso giocatore nello stesso giorno (mantenute, ma documentate)
    per_giorno = df.groupby(['player_id', 'observation_date']).size()
    doppie = per_giorno[per_giorno > 1]
    report['osservazioni_stesso_giorno'] = {
        'coppie': int(len(doppie)),
        'righe_coinvolte': int(doppie.sum()),
        'player_id': sorted(doppie.index.get_level_values('player_id').unique().tolist()),
    }

    report['righe_finali'] = len(df)
    report['giocatori_unici'] = int(df['player_id'].nunique())

    # controlli di sicurezza
    if df['club'].nunique() != len(CLUB_CANONICI):
        raise ValueError("Il cleaning dei club non ha prodotto i club attesi")
    if df.duplicated().any():
        raise ValueError("Restano righe duplicate dopo il cleaning")
    return df, report

# trasformazione del dizionario in testo, da passare al system prompt dell'agente
def format_cleaning_report(report: dict) -> str:
    """Trasforma il cleaning_report in un testo in italiano da dare all'agente."""
    nat = report['nationality']
    club = report['club']
    dup = report['duplicati']
    rng = report['correzioni_range']
    nomi = report['nomi_traslitterati']
    date = report['date_formato_gg_mm_aaaa_convertite']
    imp = report['valori_imputati_con_mediana_ruolo_stagione']
    stesso_giorno = report['osservazioni_stesso_giorno']

    righe_imputazioni = "\n".join(f"    - {col}: {n} valori" for col, n in imp.items())
    ids = ", ".join(str(p) for p in stesso_giorno['player_id'])

    return f"""Correzioni applicate ai dati grezzi (file originale: {report['righe_originali']} righe; dataset pulito: {report['righe_finali']} righe, {report['giocatori_unici']} giocatori).
I conteggi delle correzioni sono riferiti alle righe del file grezzo; quelli delle imputazioni alle righe rimaste dopo la rimozione dei duplicati.
- Duplicati rimossi: {dup['rimossi_totale']} righe ({dup['identici_nel_file_grezzo']} identiche già nel file grezzo, {dup['emersi_dopo_le_normalizzazioni']} diventate identiche solo dopo le normalizzazioni).
- Nazionalità: {nat['grafie_originali']} grafie normalizzate in {nat['grafie_finali']} ({nat['righe_modificate']} righe modificate).
- Club: {club['grafie_originali']} grafie normalizzate in {club['grafie_finali']} club ({club['righe_modificate']} righe modificate).
- Valore di mercato: {report['market_value_eur']['righe_in_formato_italiano_convertite']} righe in formato italiano (es. 11.415.000,00) convertite in numero.
- Date: {date['observation_date']} date di osservazione e {date['contract_expiry']} scadenze di contratto in formato GG/MM/AAAA convertite.
- Correzioni di range: {rng['pass_accuracy_pct_dimezzati']} valori di pass_accuracy_pct superiori a 100 dimezzati; {rng['sprint_speed_kmh_resi_positivi']} valori negativi di sprint_speed_kmh resi positivi; {rng['height_cm_divisi_per_10']} valori di height_cm superiori a 210 divisi per 10.
- Nomi traslitterati dal giapponese: {nomi['righe']} righe ({nomi['nomi_distinti']} nomi distinti).
- Valori mancanti imputati con la mediana per ruolo e stagione:
{righe_imputazioni}
- saves, save_pct e clean_sheets restano vuoti per i non portieri (mancanti per costruzione, non imputati).
- Osservazioni con stesso giocatore e stessa data: {stesso_giorno['coppie']} casi ({stesso_giorno['righe_coinvolte']} righe) per i giocatori con player_id {ids}. Sono state mantenute come valutazioni distinte; non sono un errore corretto ma un'anomalia da segnalare."""
