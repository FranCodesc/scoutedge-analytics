# ScoutEdge Analytics - Manuale Interno del Reparto Data Science & Client Success

**Versione:** 1.7
**Ultimo aggiornamento:** Ottobre 2026
**Ad uso di:** Team Data Science, Team Client Success, Onboarding nuovi analisti

---

## 1. Chi siamo e come lavoriamo

ScoutEdge Analytics è una piattaforma SaaS B2B che fornisce software di scouting e performance analytics ai club di calcio professionistici e semi-professionistici. I nostri clienti sono principalmente direttori sportivi, capi scout e analisti dell'area tecnica, che usano la piattaforma per prendere decisioni di recruiting basate sui dati invece che solo sull'osservazione soggettiva.

Il reparto Data Science & Client Success è il punto di contatto tra la tecnologia che costruiamo e i club che la usano ogni giorno. Il nostro compito è duplice:

- rispondere rapidamente alle domande dei clienti su come funziona la piattaforma, la metodologia di scouting e le policy commerciali;
- aiutare i club a interpretare i dati di scouting dei propri giocatori osservati, individuando trend, anomalie e insight utili alle decisioni di mercato.

ScoutEdge copre attualmente le principali leghe professionistiche e semi-professionistiche europee e sudamericane, con un focus particolare su campionati di seconda/terza divisione e settori giovanili: è lì che un'analisi dati strutturata offre il vantaggio competitivo maggiore, rispetto ai grandi campionati di prima fascia già ampiamente coperti dallo scouting tradizionale.

---

## 2. Piani di abbonamento

ScoutEdge Analytics è offerta in tre piani, differenziati per numero di giocatori monitorabili e livello di supporto analitico:

| Piano | Giocatori monitorati | Report custom | Osservatori dedicati | Supporto |
|---|---|---|---|---|
| **Scout** | Fino a 150 | 2 al mese | Condivisi (pool comune) | Email, SLA standard |
| **Recruitment Pro** | Fino a 600 | Illimitati | 1 osservatore dedicato al club | Email + chat prioritaria |
| **Enterprise** | Illimitati | Illimitati | Team di osservatori dedicato | Account manager dedicato + SLA rinforzato |

- Il passaggio da un piano inferiore a uno superiore (upgrade) è effettivo entro 2 giorni lavorativi dalla conferma del cliente e non richiede interruzioni del servizio.
- Il downgrade è possibile solo al rinnovo del contratto annuale, per evitare la perdita di dati storici già raccolti sopra la nuova soglia di giocatori monitorati.
- Il piano Enterprise include l'accesso in anteprima (beta) alle nuove metriche in fase di sviluppo da parte del team Data Science, prima del rilascio generale.

### Termini contrattuali di base

- **Durata minima:** 12 mesi, con rinnovo automatico alla scadenza salvo disdetta.
- **Recesso:** il cliente può recedere con preavviso scritto di almeno 60 giorni prima della data di rinnovo annuale; il recesso in corso di contratto non è previsto salvo inadempimento grave da parte di ScoutEdge.
- **Fatturazione:** mensile o annuale, con sconto sul canone in caso di pagamento annuale anticipato.

---

## 3. Metodologia di scouting ScoutEdge

### 3.1 Il sistema di scout_rating

Ogni osservazione di scouting produce uno `scout_rating` su una scala da 1 a 99, calcolato combinando:

- **Performance statistica nella stagione** (matches_played, minutes_played, goals, assists, xG, xA, pass_accuracy_pct, duels_won_pct, aerial_duels_won_pct, tackles_won, key_passes, dribbles_completed, sprint_speed_kmh, e per i portieri saves/save_pct/clean_sheets), pesata in base al ruolo del giocatore secondo i criteri della sezione 3.3;
- **Valutazione qualitativa dell'osservatore** sul campo (visione di gioco, presa di decisione, intensità), che rappresenta circa il 40% del punteggio finale;
- **Fattore età e potenziale**, che penalizza leggermente i rating per giocatori sopra i 30 anni e valorizza il potenziale di crescita sotto i 21.

Un rating sopra 80 indica un profilo da monitorare con priorità alta. Un rating sotto 40 indica un profilo generalmente non in linea con gli standard richiesti dai nostri club clienti, salvo contesti specifici (es. giovani in fase di sviluppo).

### 3.2 Metriche avanzate: xG e xA

`xG` (expected goals) e `xA` (expected assists) misurano la qualità delle occasioni da gol create o concluse da un giocatore, indipendentemente dal fatto che il gol sia stato effettivamente segnato. Sono metriche predittive più stabili del semplice conteggio di gol/assist su piccoli campioni di partite, e vengono usate dal nostro team per identificare giocatori "sottovalutati" (xG alto ma pochi gol realizzati, indice di sfortuna o problemi di finalizzazione) o "sopravvalutati" (pochi gol attesi ma tanti realizzati, possibile trend non sostenibile).

### 3.3 Criteri di valutazione per ruolo

- **Portieri (GK):** priorità a reattività, gioco con i piedi, gestione dell'area. Le metriche offensive (goals, assists, xG, xA) non sono rilevanti e vengono normalmente a zero; si valutano invece le metriche specifiche `saves`, `save_pct` e `clean_sheets` (vedi sezione 4).
- **Difensori centrali (CB):** priorità a `duels_won_pct` e `aerial_duels_won_pct` (specialisti del gioco aereo), oltre a `tackles_won` e capacità di impostazione (`pass_accuracy_pct`).
- **Terzini (LB, RB):** priorità a `duels_won_pct`, `sprint_speed_kmh` per il recupero in campo aperto e `distance_covered_km`.
- **Centrocampista di rottura (CDM):** attenzione, questo ruolo va valutato più come un difensore aggiunto che come un centrocampista puro: `duels_won_pct` e `tackles_won` sono altrettanto rilevanti quanto lo sono per CB/LB/RB, insieme a `pass_accuracy_pct` per l'impostazione del gioco.
- **Centrocampisti offensivi (CM, CAM, LM, RM):** equilibrio tra `pass_accuracy_pct`, `key_passes`, assist, xA e capacità di copertura del campo (`distance_covered_km`).
- **Attaccanti (FW - LW, RW, ST):** priorità a `goals`, `xG`, `sprint_speed_kmh` e capacità di finalizzazione; per esterni offensivi e trequartisti conta anche `dribbles_completed`, per le punte centrali (ST) conta anche `aerial_duels_won_pct`.
- **Disciplina (tutti i ruoli):** `yellow_cards` e `red_cards` vanno lette insieme a `duels_won_pct`/`tackles_won` - un volume alto di contrasti con cartellini contenuti indica un buon controllo del rischio, non solo aggressività.

### 3.4 Frequenza delle osservazioni

Ogni giocatore monitorato riceve in media 2-4 osservazioni di scouting per stagione, effettuate da osservatori diversi in match differenti, per ridurre il bias di un singolo osservatore. Le osservazioni sono registrate con data (`observation_date`) e nome dell'osservatore (`scout_name`), e vanno sempre lette in sequenza temporale per valutare il trend, non isolatamente.

---

## 4. Glossario delle metriche

| Metrica | Significato |
|---|---|
| `scout_rating` | Punteggio sintetico di valutazione (1-99), vedi sezione 3.1 |
| `xG` (expected goals) | Probabilità attesa di segnare, sommata su tutte le occasioni avute |
| `xA` (expected assists) | Probabilità attesa che un passaggio chiave si trasformi in gol |
| `pass_accuracy_pct` | Percentuale di passaggi riusciti sul totale tentati |
| `duels_won_pct` | Percentuale di duelli individuali (contrasti, corpo a corpo) vinti - rilevante non solo per i difensori ma anche per i CDM |
| `aerial_duels_won_pct` | Percentuale di duelli aerei vinti, particolarmente rilevante per CB e punte centrali (ST) |
| `tackles_won` | Numero di contrasti vinti nella stagione |
| `key_passes` | Passaggi chiave che generano un'occasione da gol, complementare a xA |
| `dribbles_completed` | Dribbling riusciti nella stagione, soprattutto per esterni offensivi e trequartisti |
| `yellow_cards` / `red_cards` | Cartellini gialli e rossi ricevuti nella stagione, indicatore di disciplina/rischio |
| `distance_covered_km` | Distanza media percorsa a partita, indicatore di intensità fisica |
| `sprint_speed_kmh` | Velocità massima di sprint registrata, in km/h |
| `saves` | Numero di parate effettuate nella stagione (solo portieri) |
| `save_pct` | Percentuale di parate sui tiri in porta subiti (solo portieri) |
| `clean_sheets` | Partite concluse senza subire gol (solo portieri) |
| `matches_played` / `minutes_played` | Partite disputate e minuti totali giocati nella stagione |
| `market_value_eur` | Stima interna del valore di mercato del giocatore (vedi FAQ, sezione 8) |
| `injury_days_last_season` | Giorni di indisponibilità per infortunio nell'ultima stagione osservata |
| `observation_date` | Data della singola osservazione di scouting (non coincide con la stagione) |

Le metriche `saves`, `save_pct` e `clean_sheets` sono valorizzate solo per i portieri: per tutti gli altri ruoli il campo è vuoto per costruzione, non per un errore di raccolta dati.

---

## 5. Policy dati e privacy

- I dati di scouting raccolti (statistiche di performance, valutazioni, dati anagrafici dei giocatori osservati) sono trattati come informazioni riservate del club cliente che li ha commissionati e non vengono mai condivisi con altri club clienti della piattaforma.
- I dati anagrafici dei calciatori osservati (nome, nazionalità, data di nascita) sono trattati nel rispetto della normativa applicabile sulla protezione dei dati personali. L'accesso ai dati grezzi è limitato al personale del club cliente e al team Data Science interno per finalità di manutenzione del servizio.
- Le credenziali di accesso alla piattaforma (incluse le chiavi API per le integrazioni) non devono mai essere condivise via email o chat non cifrata. Ogni richiesta di reset credenziali va gestita tramite il canale di supporto ufficiale, con verifica dell'identità del richiedente.
- I dataset esportati dai club (CSV, report PDF) restano di proprietà del club cliente. ScoutEdge non riutilizza i dati di un club per finalità commerciali verso altri club.

---

## 6. Procedura di data cleaning del team Data Science

Prima di qualunque analisi aggregata o calcolo di trend su un dataset di scouting, il team Data Science applica una procedura standard di pulizia dei dati, necessaria perché le osservazioni raccolte sul campo da osservatori diversi, con strumenti non sempre uniformi, contengono fisiologicamente delle imperfezioni:

1. **Rimozione duplicati:** eliminazione delle righe identiche generate da doppia registrazione della stessa osservazione su canali diversi.
2. **Gestione valori mancanti:** i valori mancanti su metriche numeriche (es. xG, xA, sprint_speed_kmh) non vengono eliminati automaticamente riga per riga, ma segnalati e, dove statisticamente sensato, imputati con la mediana del ruolo/stagione di riferimento, per non distorcere le medie con rimozioni indiscriminate.
3. **Normalizzazione dei formati:** uniformazione dei formati data (alcune osservazioni arrivano in formato `GG/MM/AAAA`, altre in `AAAA-MM-GG`) e dei testi (maiuscole/minuscole e spazi incoerenti nei nomi di club e nazionalità).
4. **Normalizzazione degli alfabeti non latini:** i nomi dei giocatori osservati in alcuni campionati (es. Giappone) arrivano talvolta registrati nell'alfabeto originale (es. caratteri kanji) invece che traslitterati. Il team Data Science applica una traslitterazione in caratteri latini prima di qualunque incrocio o confronto tra dataset, per garantire coerenza con i club clienti che operano su sistemi che non supportano alfabeti non latini.
5. **Rimozione di titoli e qualifiche dai nomi dei giocatori:** alcuni nomi arrivano dalle fonti con un titolo davanti (es. `Dr.`, `Mr`, `Herr`, `Sr.`) o una qualifica in coda (es. `MBA`, `PhD`). Il team Data Science li toglie, in modo che nei report e nei grafici compaia solo il nome del giocatore (es. `Dr. Rene Mühle MBA.` diventa `Rene Mühle`). La rimozione segue un elenco chiuso di titoli e qualifiche e riguarda solo la prima e l'ultima parola del nome: nessun'altra parte del nome viene toccata. Questo passaggio non modifica il `player_id`, che resta la chiave di riferimento per ogni confronto.
6. **Controllo dei range:** verifica che le metriche percentuali (es. `pass_accuracy_pct`) siano comprese tra 0 e 100, e che valori come `sprint_speed_kmh` o `height_cm` siano fisicamente plausibili; i valori fuori range vengono segnalati come possibili errori di trascrizione e corretti o esclusi dal calcolo, mai lasciati silenziosamente nell'analisi.
7. **Documentazione delle modifiche:** ogni pulizia applicata a un dataset cliente viene sintetizzata insieme al report finale, così il club sa sempre quali correzioni sono state fatte sui propri dati grezzi.

Questa procedura è la stessa che l'agente di analisi dati della piattaforma applica in automatico quando elabora una richiesta di analisi.

---

## 7. SLA e procedura di supporto

### 7.1 Tempi di risposta garantiti

| Priorità | Descrizione | Tempo di prima risposta | Tempo di risoluzione target |
|---|---|---|---|
| Alta | Piattaforma non accessibile, dati non disponibili | 2 ore lavorative | 8 ore lavorative |
| Media | Funzionalità non disponibile ma esiste workaround | 8 ore lavorative | 2 giorni lavorativi |
| Bassa | Richiesta informativa, domanda su metodologia | 1 giorno lavorativo | 3 giorni lavorativi |

### 7.2 Come richiedere un report di scouting custom

I club clienti possono richiedere report di analisi personalizzati (es. confronto tra più giocatori su metriche specifiche, analisi di trend su una singola stagione, elenco filtrato per ruolo e fascia di età) tramite il canale di supporto ufficiale. Il team Data Science processa la richiesta entro lo SLA indicato in base alla priorità assegnata dal cliente.

### 7.3 Escalation

Se una richiesta non riceve risposta entro lo SLA previsto, il cliente può richiedere l'escalation al Team Lead di Client Success, che prende in carico la pratica entro 4 ore lavorative.

---

## 8. FAQ per il team Client Success

**D: Un club chiede perché lo scout_rating di un giocatore è cambiato molto da un'osservazione all'altra. Come rispondo?**
R: È normale entro un certo margine (5-10 punti), perché ogni osservazione riflette una singola partita e un singolo osservatore. Variazioni più ampie vanno controllate: potrebbe trattarsi di un infortunio recente (vedi `injury_days_last_season`), un cambio di ruolo tattico, oppure - se il dato sembra un errore - un problema di data quality da segnalare al team Data Science.

**D: Un cliente vuole sapere se può confrontare giocatori di ruoli diversi con lo stesso rating.**
R: Sconsigliato. Lo scout_rating è calibrato per ruolo (vedi sezione 3.3): un rating di 75 per un portiere e uno di 75 per un attaccante non sono comparabili sullo stesso piano, perché derivano da pesi diversi assegnati alle metriche. Il confronto corretto è sempre all'interno dello stesso ruolo o macro-categoria.

**D: Come gestisco una richiesta di upgrade del piano di abbonamento?**
R: Le richieste di upgrade (vedi sezione 2 per il dettaglio dei piani) vanno indirizzate al team Account Management, non gestite direttamente dal team Data Science o Client Success tecnico.

**D: Qual è la procedura di onboarding per un nuovo club cliente?**
R: 1) Kick-off call con il capo scout/direttore sportivo per definire i ruoli e le competizioni di interesse. 2) Configurazione dei filtri di ruolo/età/nazionalità richiesti per il club. 3) Caricamento del primo elenco di giocatori monitorati. 4) Sessione di formazione sull'interpretazione delle metriche (xG, xA, scout_rating) per lo staff tecnico del club. 5) Check-in dopo 30 giorni per raccogliere feedback e affinare la configurazione.

**D: Un dataset esportato dal cliente contiene valori mancanti o incoerenti (es. date in formati diversi, valori percentuale sopra 100%). È un bug della piattaforma?**
R: Non necessariamente. Come descritto nella procedura di data cleaning (sezione 6), i dati di scouting raccolti sul campo da osservatori diversi possono presentare incoerenze naturali. È corretto informare il cliente che l'analisi dati include sempre una fase di pulizia prima di qualunque calcolo di trend o statistica aggregata.

**D: Un club chiede se il valore di mercato (`market_value_eur`) stimato dalla piattaforma è una valutazione ufficiale.**
R: No. Il valore di mercato calcolato da ScoutEdge è una stima interna basata su età, ruolo, rating e benchmark di mercato per fascia, pensata per supportare le decisioni interne del club, non è una valutazione ufficiale o vincolante ai fini di una trattativa di trasferimento.

**D: In alcune osservazioni recenti il campo `contract_expiry` riporta una data già passata. È un errore da segnalare?**
R: Non necessariamente. Un contratto già scaduto su un'osservazione recente indica spesso un giocatore svincolato o in scadenza imminente - uno scenario di scouting particolarmente rilevante, perché un giocatore a parametro zero rappresenta un'opportunità di mercato senza costo di cartellino. Va quindi letto come un segnale utile, non filtrato via come dato sporco, salvo il caso in cui il cliente segnali esplicitamente un errore di trascrizione su un giocatore specifico.

**D: Come distinguo in modo affidabile due giocatori diversi nel dataset?**
R: Sempre tramite `player_id`, mai tramite `player_name`. In dataset più ampi di quelli attuali possono comparire omonimie (nomi comuni in alcuni paesi), quindi qualunque analisi, confronto o join tra tabelle va fatto incrociando gli ID, non i nomi testuali, per evitare di unire per errore le statistiche di due persone diverse.
