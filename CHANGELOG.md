# Changelog - platform_handbook.md

Storico delle versioni del documento `platform_handbook.md` (knowledge base RAG di ScoutEdge Analytics). Non fa parte del contenuto indicizzato in ChromaDB: è documentazione di progetto ad uso interno/consegna.

## 1.6 - Settembre 2026
- Rimossa la sezione "Guida rapida alla dashboard" per evitare che la RAG citi funzionalita' di prodotto (Shortlist, Confronto Giocatori, Report Custom, Alert) non rappresentate nel frontend consegnato con il progetto. Rinumerate le sezioni successive (Policy dati 5, Data cleaning 6, SLA 7, FAQ 8) e aggiornati i rimandi incrociati.

## 1.5 - Settembre 2026
- Aggiunto un breve paragrafo sulle competizioni/campionati coperti dal servizio (sezione 1).
- Aggiunta sottosezione "Termini contrattuali di base" (durata minima, recesso, fatturazione) alla sezione 2, Piani di abbonamento.

## 1.4 - Settembre 2026
- Aggiornato l'elenco delle metriche che alimentano lo scout_rating (sezione 3.1) per includere anche aerial_duels_won_pct, tackles_won, key_passes, dribbles_completed e le metriche portiere - era rimasto disallineato dopo l'estensione dei criteri per ruolo in 3.3.
- Aggiunta FAQ su `contract_expiry` già scaduto in osservazioni recenti (interpretato come segnale di giocatore svincolato/in scadenza, non come errore).
- Aggiunta FAQ sull'omonimia tra giocatori diversi, con raccomandazione di usare sempre `player_id` come chiave di confronto.

## 1.3 - Settembre 2026
- Aggiunto lo step "Normalizzazione degli alfabeti non latini" alla Procedura di data cleaning (sezione 7), per gestire nomi giocatori registrati in alfabeti originali (es. kanji) invece che traslitterati.
- Corretta la data del documento per coerenza con la data reale del progetto.
- Allineato lo storico stagioni del dataset di riferimento a 2023/24, 2024/25, 2025/26.

## 1.2 - Settembre 2026
- Riscritti i Criteri di valutazione per ruolo (sezione 3.3) con maggiore granularità (CB, terzini, CDM trattato come difensore aggiunto, centrocampisti offensivi, disciplina).
- Esteso il Glossario delle metriche (sezione 4) con le nuove metriche del dataset: `aerial_duels_won_pct`, `tackles_won`, `key_passes`, `dribbles_completed`, `yellow_cards`/`red_cards`, `distance_covered_km`, `saves`, `save_pct`, `clean_sheets`.

## 1.1 - Settembre 2026
- Aggiunta sezione 2, Piani di abbonamento (Scout, Recruitment Pro, Enterprise).
- Aggiunta sezione 4, Glossario delle metriche.
- Aggiunta sezione 5, Guida rapida alla dashboard.
- Aggiunta sezione 7, Procedura di data cleaning del team Data Science.
- Aggiornati i rimandi incrociati nella FAQ (sezione 9) alle nuove sezioni.

## 1.0 - Settembre 2026
- Prima stesura: Chi siamo, Metodologia di scouting, Policy dati e privacy, SLA e procedura di supporto, FAQ per il team Client Success.
