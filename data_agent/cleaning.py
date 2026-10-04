"""Pulizia del dataset di scouting (data/scouting_data.csv).

Implementa la procedura descritta nella sezione 6 di data/platform_handbook.md.
Viene eseguita una sola volta all'avvio del microservizio (lifespan in main.py):
l'agente lavora sempre sui dati già puliti e riceve il riepilogo delle correzioni
(cleaning_report) nel proprio system prompt.
"""

import pandas as pd


# Nomi di giocatori giapponesi registrati in kanji nel file grezzo -> traslitterazione
# Hepburn (cognome nome). Mappatura manuale perché librerie come unidecode usano le
# letture cinesi dei caratteri e producono nomi sbagliati.
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

# Grafie ufficiali dei 25 club presenti nel dataset. Nel file grezzo compaiono 74
# varianti (maiuscole, spazi in più): ognuna viene ricondotta a uno di questi nomi.
# Lista esplicita invece della "grafia più frequente" per avere un risultato
# riproducibile e per accorgersi subito di un club inatteso.
CLUB_CANONICI = [
    "Altopiano Sporting", "Arena Meridiana FC", "Atletico Serrano", "Baia Dorata FC",
    "Borgo Union", "Cima Bianca FC", "Costa Azzurra FC", "Delta Sporting Club",
    "Fiume Rosso AC", "Foresta Nera AC", "Isola Verde United", "Lago Blu United",
    "Monte Grigio SC", "Nord Stella FC", "Pineta Calcio", "Ponte Vecchio FC",
    "Portofino AC", "Radura United", "Real Cascata FC", "Rocca Sportiva",
    "Scogliera AC", "Stelluccia Sporting", "Torretta United", "Vallata Calcio",
    "Vigneto Calcio",
]

# Dizionario di ricerca: chiave normalizzata -> grafia canonica.
# " ".join(nome.split()) toglie gli spazi iniziali/finali e riduce quelli doppi a uno;
# casefold() porta tutto in minuscolo (versione più robusta di lower()).
_CLUB_LOOKUP = {" ".join(nome.split()).casefold(): nome for nome in CLUB_CANONICI}


def _normalize_club(value):
    """Restituisce la grafia canonica di un club, a prescindere da maiuscole e spazi."""
    # stessa normalizzazione usata per costruire _CLUB_LOOKUP
    chiave = " ".join(str(value).split()).casefold()
    try:
        return _CLUB_LOOKUP[chiave]
    except KeyError:
        # Un club fuori lista blocca l'avvio con un errore leggibile, invece di far
        # passare dati non normalizzati. "from None" nasconde il KeyError interno.
        raise ValueError(f"Club sconosciuto nel dataset: {value!r}") from None


def _parse_market_value(value):
    """Converte market_value_eur in float. Nel file grezzo convivono numeri semplici
    (es. 6439000) e il formato italiano (es. 11.415.000,00)."""
    value = str(value).strip()
    if ',' in value and '.' in value:
        # formato italiano: punti = migliaia, virgola = decimali
        value = value.replace('.', '').replace(',', '.')
    return float(value)


def _parse_mixed_date(value):
    """Converte una data in Timestamp. Nel file grezzo convivono AAAA-MM-GG e GG/MM/AAAA.
    Limite noto: un valore mancante (NaN) solleverebbe un errore (D6; oggi non succede)."""
    value = str(value).strip()
    # prova prima il formato ISO, poi quello GG/MM/AAAA
    try:
        return pd.to_datetime(value, format='%Y-%m-%d')
    except ValueError:
        return pd.to_datetime(value, format='%d/%m/%Y')


def clean_scouting_data(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Applica la procedura di cleaning descritta nella sezione 6 di platform_handbook.md.
    Restituisce (dataframe pulito, report delle correzioni(coppia chiave valore)).
    I conteggi delle correzioni sono riferiti alle righe del file grezzo; quelli delle
    imputazioni alle righe rimaste dopo la deduplica."""
    # Si lavora su una copia: df_raw deve restare intatto, perché serve più avanti
    # per contare i duplicati già presenti nel file grezzo.
    df = df_raw.copy()

    # Il report si riempie passo per passo, nel momento in cui ogni correzione viene
    # applicata: è l'unico punto in cui si conoscono sia il valore prima sia quello dopo.
    report = {"righe_originali": len(df_raw)}

    # normalizzazione nationality (spazi in più e maiuscole incoerenti, es. "  italy")
    # nat_prima resta collegata alla colonna originale: l'assegnazione successiva
    # crea una nuova colonna invece di modificare quella vecchia.
    nat_prima = df['nationality']
    df['nationality'] = df['nationality'].str.strip().str.title()
    report['nationality'] = {
        'grafie_originali': int(nat_prima.nunique()),
        'grafie_finali': int(df['nationality'].nunique()),
        # confronto riga per riga: True dove il valore è cambiato, .sum() conta i True
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
    # Prima si conta, poi si converte: dopo la conversione in float non si può più
    # sapere quali valori erano in formato italiano.
    # mv è una copia testuale usata solo per il conteggio (non viene assegnata a df).
    mv = df['market_value_eur'].astype(str).str.strip()
    report['market_value_eur'] = {
        # stessa condizione usata da _parse_market_value: virgola E punto presenti.
        # regex=False: in una regex "." significa "qualsiasi carattere".
        'righe_in_formato_italiano_convertite': int((mv.str.contains(',') & mv.str.contains('.', regex=False)).sum()),
    }
    df['market_value_eur'] = df['market_value_eur'].apply(_parse_market_value)

    # date miste -> datetime
    # Formati espliciti (ISO e GG/MM/AAAA) invece del riconoscimento automatico,
    # che potrebbe scambiare giorno e mese (es. 03/04/2025).
    report['date_formato_gg_mm_aaaa_convertite'] = {}
    for col in ['observation_date', 'contract_expiry']:
        # tentativo di lettura solo ISO: i valori non ISO diventano NaT (errors='coerce'),
        # quindi .isna() individua proprio le date in formato GG/MM/AAAA da convertire
        non_iso = pd.to_datetime(df[col].astype(str).str.strip(), format='%Y-%m-%d', errors='coerce').isna()
        report['date_formato_gg_mm_aaaa_convertite'][col] = int(non_iso.sum())
        df[col] = df[col].apply(_parse_mixed_date)

    # correzione anomalie di range (pattern sistematici, non semplici outlier)
    # Valori fisicamente impossibili con uno schema riconoscibile: vengono corretti,
    # non eliminati (handbook §6 punto 5). Le maschere si calcolano PRIMA di correggere
    # e servono sia per contare sia per modificare esattamente quelle righe.
    mask_pass = df['pass_accuracy_pct'] > 100    # percentuale oltre 100: valore registrato doppio
    mask_sprint = df['sprint_speed_kmh'] < 0     # velocità negativa: errore di segno
    mask_height = df['height_cm'] > 210          # altezza con uno zero in più (es. 1820 -> 182)
    report['correzioni_range'] = {
        'pass_accuracy_pct_dimezzati': int(mask_pass.sum()),
        'sprint_speed_kmh_resi_positivi': int(mask_sprint.sum()),
        'height_cm_divisi_per_10': int(mask_height.sum()),
    }
    # .loc[maschera, colonna]: la modifica si applica solo alle righe dove la maschera è True
    df.loc[mask_pass, 'pass_accuracy_pct'] /= 2
    # abs() su tutta la colonna: sui valori già positivi non cambia nulla
    df['sprint_speed_kmh'] = df['sprint_speed_kmh'].abs()
    df.loc[mask_height, 'height_cm'] /= 10

    # traslitterazione nomi giapponesi (mappatura Hepburn manuale, non unidecode)
    # isin(...) individua le righe con un nome in kanji presente nella mappa;
    # .replace(dizionario) sostituisce i valori che coincidono esattamente con una chiave.
    mask_nomi = df['player_name'].isin(list(MAPPA_CORREZIONE_NOMI))
    report['nomi_traslitterati'] = {
        'righe': int(mask_nomi.sum()),
        'nomi_distinti': int(df.loc[mask_nomi, 'player_name'].nunique()),
    }
    df['player_name'] = df['player_name'].replace(MAPPA_CORREZIONE_NOMI)

    # deduplica: DOPO tutte le normalizzazioni (righe uguali nella sostanza ma scritte
    # in modo diverso diventano identiche) e PRIMA dell'imputazione (le mediane non
    # devono essere calcolate su righe doppie).
    # drop_duplicates() confronta tutte le colonne e tiene la prima occorrenza.
    righe_prima = len(df)
    df = df.drop_duplicates()
    rimossi = righe_prima - len(df)
    # Le righe identiche nel file grezzo restano identiche anche dopo le normalizzazioni,
    # quindi sono sicuramente tra quelle rimosse: la differenza sono i duplicati "nascosti".
    identici_nel_grezzo = int(df_raw.duplicated().sum())
    report['duplicati'] = {
        'rimossi_totale': rimossi,
        'identici_nel_file_grezzo': identici_nel_grezzo,
        'emersi_dopo_le_normalizzazioni': rimossi - identici_nel_grezzo,
    }

    # imputazione valori mancanti (mediana per ruolo/stagione)
    # Mediana(importante) e non media: non si lascia trascinare dai valori estremi.
    # Per ruolo e stagione: un portiere e un'ala hanno valori tipici molto diversi.
    # transform restituisce una Series allineata a df (stessa lunghezza e indice),
    # quindi si può riassegnare direttamente alla colonna.
    cols_da_imputare = ['weight_kg', 'xg', 'xa', 'pass_accuracy_pct', 'sprint_speed_kmh', 'injury_days_last_season']
    report['valori_imputati_con_mediana_ruolo_stagione'] = {}
    for col in cols_da_imputare:
        mancanti_prima = int(df[col].isna().sum())
        df[col] = df.groupby(['position', 'season'])[col].transform(lambda x: x.fillna(x.median()))
        # se un gruppo fosse tutto vuoto la mediana sarebbe NaN e il valore resterebbe
        # mancante: contare "prima - dopo" non gonfia il numero
        report['valori_imputati_con_mediana_ruolo_stagione'][col] = mancanti_prima - int(df[col].isna().sum())

    # saves / save_pct / clean_sheets: mancanti per costruzione per i non portieri, NON imputati.
    # Per chi non è portiere la metrica non esiste: imputarla significherebbe inventare dati.
    # Vengono solo contati, per trasparenza.
    report['mancanti_non_imputati_non_portieri'] = {
        col: int(df[col].isna().sum()) for col in ['saves', 'save_pct', 'clean_sheets']
    }

    # osservazioni dello stesso giocatore nello stesso giorno (mantenute, ma documentate)
    # Decisione D8 (opzione A): non sono duplicati da eliminare ma valutazioni distinte,
    # in contrasto con l'handbook §3.4 ("osservatori diversi in match differenti"):
    # vengono solo contate e segnalate.
    # .size() conta le righe per ogni coppia (player_id, observation_date): il risultato
    # ha un indice doppio, da cui get_level_values estrae solo i player_id.
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
    # raise e non assert: gli assert si disattivano con "python -O".
    # Il cleaning gira all'avvio di FastAPI: se un controllo fallisce il servizio non
    # parte, invece di lavorare su dati sbagliati(importante).
    if df['club'].nunique() != len(CLUB_CANONICI):
        raise ValueError("Il cleaning dei club non ha prodotto i club attesi")
    if df.duplicated().any():
        raise ValueError("Restano righe duplicate dopo il cleaning")
    return df, report


def format_cleaning_report(report: dict) -> str:
    """Trasforma il cleaning_report in un testo in italiano da dare all'agente.

    Il testo finisce nel system prompt del data agent (vedi build_data_agent in agent.py):
    i numeri non sono ricalcolabili dal dataframe già pulito, quindi l'agente li legge da qui.
    Testo e non JSON: l'LLM lo riporta con più fedeltà e la base dei conteggi è esplicita.
    """
    # alias brevi per rendere leggibile la f-string finale
    nat = report['nationality']
    club = report['club']
    dup = report['duplicati']
    rng = report['correzioni_range']
    nomi = report['nomi_traslitterati']
    date = report['date_formato_gg_mm_aaaa_convertite']
    imp = report['valori_imputati_con_mediana_ruolo_stagione']
    stesso_giorno = report['osservazioni_stesso_giorno']

    # una riga per colonna imputata (generator expression dentro join)
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
