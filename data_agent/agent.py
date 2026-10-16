"""Agente di analisi dati di ScoutEdge Analytics (ReAct con un solo tool, `python_repl`).

Il modulo costruisce l'agente che risponde alle domande sul dataset di scouting
generando ed eseguendo codice pandas. Si compone di tre parti:

1. CHARTS_DIR: la cartella (percorso assoluto) in cui vengono salvati i grafici PNG.
2. make_python_tool(df): crea il tool `python_repl`, un piccolo interprete che esegue il
   codice scritto dal modello su una copia del dataframe e salva in automatico i grafici.
3. build_data_agent(df, llm, cleaning_summary): assembla l'agente con il suo system prompt,
   che contiene le regole di analisi e il riepilogo delle correzioni applicate ai dati.

main.py chiama build_data_agent a ogni richiesta: ogni domanda ha quindi uno stato
pulito, senza variabili o filtri lasciati da richieste precedenti.

Limite di sicurezza noto: il codice generato dal modello viene eseguito con exec/eval
nel processo del servizio, senza sandbox. È accettabile solo in un contesto locale e
didattico (vedi la sezione sulla sicurezza nella documentazione del progetto).
"""

import io
import contextlib
import ast
import uuid
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # backend non interattivo: necessario in un processo server, senza display
import matplotlib.pyplot as plt
from unittest import mock
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, ScalarFormatter
import seaborn as sns
import pandas as pd

from langchain_core.tools import tool
from langchain.agents import create_agent


# Cartella dei grafici: percorso assoluto basato sulla posizione di questo file e non
# sulla cartella da cui viene avviato uvicorn. Con un percorso relativo, avviare il
# servizio da un'altra cartella farebbe salvare i PNG (e poi cercarli) nel posto sbagliato.
CHARTS_DIR = Path(__file__).resolve().parent / "charts"
CHARTS_DIR.mkdir(exist_ok=True) # crea cartella se manca

# Limite (in caratteri) del testo che il tool restituisce al modello. Dopo l'introduzione della
# stampa completa dei DataFrame un risultato grande potrebbe far crescere molto i token:
# oltre il limite il testo viene troncato e in fondo si aggiunge una nota fissa. La nota
# esplicita serve a evitare che il modello riempia i vuoti inventando i dati mancanti.
MAX_TOOL_OUTPUT = 6000

# Valore assoluto, sull'intervallo visibile di un asse, da cui in poi i numeri si scrivono
# per esteso con il punto delle migliaia invece della notazione scientifica (es. 1e7).
SOGLIA_ASSE_GRANDE = 1_000_000


def _formatta_assi_grandi(fig):
    """Scrive per esteso (es. 17.500.000) i numeri degli assi che matplotlib mostrerebbe con
    il moltiplicatore in basso a destra (es. 1e7).

    La scelta sta nel codice e non nel prompt perché il modello non formatta gli assi in modo
    affidabile: anche quando la domanda chiedeva i milioni, il grafico usciva con 1e7.
    Si interviene solo sugli assi con il formatter predefinito (tipo esatto ScalarFormatter,
    non le sottoclassi): un formatter scelto dal modello resta com'è, e gli assi con
    categorie, date o scala logaritmica hanno formatter di altro tipo, quindi non vengono
    toccati. Le etichette degli assi le sceglie il modello."""
    # round() prima del formato: evita "-0" per uno zero negativo e non cambia i tick, che
    # a queste grandezze sono sempre interi
    separatore = FuncFormatter(lambda valore, _: f"{round(valore):,}".replace(",", "."))
    for ax in fig.axes:
        for asse in (ax.xaxis, ax.yaxis):
            if type(asse.get_major_formatter()) is not ScalarFormatter:
                continue
            if max(abs(estremo) for estremo in asse.get_view_interval()) >= SOGLIA_ASSE_GRANDE:
                asse.set_major_formatter(separatore)


def make_python_tool(df):
    """Costruisce il tool 'python_repl' per un dataframe specifico.

    Il namespace (con una COPIA di df) viene creato qui: ogni chiamata a questa funzione
    produce quindi uno stato nuovo. build_data_agent la richiama a ogni richiesta, così le
    variabili persistono tra le tool-call della stessa richiesta ma non passano alla successiva.

    Il tool è un REPL "alla Jupyter": esegue il codice scritto dal modello, mostra il valore
    dell'ultima espressione e, se il codice ha creato un grafico, lo salva in CHARTS_DIR.
    Restituisce la funzione-tool (decorata con @tool) da passare a create_agent.
    """

    # Un solo dizionario fa da globals e da locals di exec/eval. Con due dizionari separati
    # le funzioni, le lambda e le list comprehension scritte dal modello (che hanno un proprio
    # ambito e cercano i nomi nei globals) non vedrebbero 'df' e 'pd': NameError.
    namespace = {"df": df.copy(), "pd": pd, "plt": plt, "sns": sns}

    @tool
    def python_repl(code: str) -> str:
        """Esegue codice Python per analizzare il dataframe (disponibile come variabile 'df').
        Disponibili anche 'pd', 'plt' (matplotlib.pyplot) e 'sns' (seaborn) per creare grafici:
        se il codice genera una figura matplotlib, viene salvata automaticamente come PNG
        (non serve chiamare plt.savefig() né plt.show()).
        Le variabili definite in una chiamata restano disponibili nelle chiamate successive
        (come in un notebook Jupyter).
        Si comporta come un REPL: se l'ultima riga è un'espressione, il suo valore viene mostrato
        automaticamente, altrimenti usa print()."""
        output = io.StringIO()
        chart_note = ""
        try:
            # Il codice viene analizzato come albero sintattico (AST) invece di darlo
            # direttamente a exec. Serve per separare l'ultima istruzione dalle altre: se è
            # un'espressione (es. `df.shape`) se ne valuta e mostra il valore come fa un REPL,
            # altrimenti il modello dovrebbe scrivere print() ogni volta. Se il codice è vuoto
            # `tree.body` è vuoto: il segnaposto [None] evita l'errore di spacchettamento.
            tree = ast.parse(code)
            *body, last = tree.body if tree.body else [None]

            # Tutto ciò che il codice stampa viene catturato in `output` invece di finire sul
            # terminale del server: è il testo che il tool restituisce al modello.
            # Il contesto pandas mostra TUTTE le colonne. Con la rappresentazione
            # abbreviata di default, le 35 colonne di df finivano in parte nei "...": il modello
            # non vedeva `market_value_eur` e inventava il valore (diagnosi: "valore attuale
            # più alto" → 15.000.000 o 5.000.000 invece di 18.680.000). La larghezza di 250
            # caratteri evita che le righe vengano spezzate male nell'output.
            #
            # Il salvataggio dei grafici è riservato al tool. Se il codice del modello
            # chiama plt.savefig/fig.savefig scrive un PNG fuori da charts/ (con un nome suo),
            # e se poi chiama plt.close() la figura sparisce prima che il tool la veda: nessun
            # grafico e nessuna nota (grafico mancante in modo intermittente). Per tutta
            # l'esecuzione del codice del modello queste funzioni non fanno nulla, così ogni
            # figura creata finisce in charts/ con il nome chart_xxxxxxxx.png. Non è una
            # sandbox: il modello può comunque scrivere file in altri modi (limite di
            # sicurezza noto del python_repl).
            _nulla = lambda *args, **kwargs: None
            with contextlib.redirect_stdout(output), \
                 pd.option_context("display.max_columns", None, "display.width", 250), \
                 mock.patch.object(plt, "savefig", _nulla), \
                 mock.patch.object(plt, "close", _nulla), \
                 mock.patch.object(plt, "show", _nulla), \
                 mock.patch.object(Figure, "savefig", _nulla):
                if body:
                    exec(compile(ast.Module(body=body, type_ignores=[]), "<code>", "exec"), namespace)
                if last is not None:
                    if isinstance(last, ast.Expr):
                        result = eval(compile(ast.Expression(last.value), "<code>", "eval"), namespace)
                        if result is not None:
                            print(repr(result))
                    else:
                        exec(compile(ast.Module(body=[last], type_ignores=[]), "<code>", "exec"), namespace)

            # Qui le funzioni originali sono ripristinate: il salvataggio è quello del tool.
            if plt.get_fignums():
                # Solo il nome del file: nella nota per il modello non deve comparire
                # nessun percorso del disco (fuga di informazioni e romperebbe l'URL).
                filename = f"chart_{uuid.uuid4().hex[:8]}.png"
                # plt.savefig salva la figura corrente: è quella da sistemare
                _formatta_assi_grandi(plt.gcf())
                plt.savefig(CHARTS_DIR / filename, bbox_inches="tight")
                plt.close("all")
                chart_note = f"\n[Grafico salvato correttamente: {filename}]"

        # L'errore non interrompe il servizio: viene restituito al modello come testo, così può
        # leggerlo e correggere il codice al giro successivo (tipico del ciclo ReAct di auto-correzione).
        # Le figure rimaste aperte si chiudono per non contaminare la richiesta successiva.
        except Exception as e:
            plt.close("all")
            return f"Errore nell'esecuzione: {e}"
        # Troncamento dell'output: la nota del grafico viene aggiunta DOPO, così resta
        # sempre in fondo e main.py la trova anche quando il testo è stato accorciato.
        testo = output.getvalue() or "Codice eseguito senza output."
        if len(testo) > MAX_TOOL_OUTPUT:
            testo = (testo[:MAX_TOOL_OUTPUT]
                     + "\n[Output troncato: stampa solo le righe e le colonne necessarie alla risposta.]")
        return testo + chart_note
    return python_repl


def build_data_agent(df, llm, cleaning_summary):
    """Costruisce un agente ReAct per l'analisi del dataframe 'df'.

    Parametri:
        df: dataframe già pulito (output di clean_scouting_data).
        llm: modello di linguaggio (ChatOpenAI) usato dall'agente.
        cleaning_summary: testo (da format_cleaning_report) che riassume le correzioni
            applicate ai dati; viene inserito nel system prompt.

    Va richiamata a ogni richiesta (non una volta sola all'avvio): lo stato del
    tool è isolato per richiesta.
    Restituisce l'agente pronto per .invoke().
    """

    python_tool = make_python_tool(df)

    # System prompt: ogni sezione è nata per correggere un comportamento sbagliato osservato
    # nei test, quindi l'ordine e la formulazione contano. Principio emerso dal lavoro sul
    # controllo delle osservazioni nello stesso giorno: le regole condizionali ("se... allora...") il modello non le esegue in
    # modo affidabile, mentre le procedure con codice esatto da lanciare sempre e un ordine
    # fisso della risposta sì. Per questo gli esempi di codice usano segnaposto espliciti
    # (<...>) e non valori reali, che il modello potrebbe copiare.
    #
    # Sezioni, in ordine:
    # 1. Colonne di 'df': evita che il modello inventi nomi di colonne.
    # 2. Struttura dei dati: ogni riga è un'osservazione nel tempo, quindi un giocatore compare
    #    più volte e metriche come valore di mercato e rating cambiano.
    # 3. Chiave del giocatore: sempre 'player_id', mai 'player_name' (omonimie).
    # 4. Periodo oppure stato "attuale". Prima si distingue: se la domanda indica un periodo
    #    (stagione, anno, mese, intervallo di date), si filtra df sul periodo e si usano TUTTE le
    #    sue osservazioni (regressione osservata: "scout_rating medio nell'ultima stagione" veniva
    #    calcolato sulle ultime osservazioni dei giocatori, 65.21, invece che su tutte le 405
    #    della stagione, 65.11). Se invece si chiede lo stato attuale senza periodo, vale la
    #    procedura esatta con ordinamento stabile (kind='stable'), anche per massimi, minimi e
    #    classifiche su tutti i giocatori (bug osservato: "valore attuale più alto nel dataset"
    #    restituiva il massimo storico). Il criterio è deterministico: a parità di data vince
    #    la riga registrata per ultima.
    # 4bis. "Osservazione più recente". La domanda dei 3 difensori centrali "nell'osservazione
    #    più recente" sbagliava circa 2 volte su 10: il modello la leggeva come la sola data più
    #    recente del dataset (poche righe, un solo difensore) invece dell'ultima osservazione di
    #    ogni giocatore. Un tentativo scartato: un dataframe precalcolato (df_attuale), per le
    #    regressioni che ha causato (il controllo delle osservazioni nello stesso giorno girava sul dataframe sbagliato, le domande su
    #    un periodo venivano calcolate sullo stato attuale). La definizione esplicita nel prompt
    #    resta: sui difensori centrali non ha dato un miglioramento misurabile (6/8 con la frase,
    #    8/8 senza, campioni troppo piccoli). L'errore su "valore di mercato attuale più alto"
    #    (5.000.000 o 15.000.000 invece di 18.680.000) non dipendeva dalla frase ma dall'output
    #    abbreviato del tool, che nascondeva la colonna del valore (vedi python_repl). L'errore
    #    intermittente sui difensori centrali resta un limite noto.
    # 5. Controllo delle osservazioni nello stesso giorno: per giocatori specifici stampa le osservazioni della data più recente e
    #    un elenco "GIOCATORI DA SEGNALARE" calcolato dal codice (gli id con più righe in quella
    #    data). Ordine fisso della risposta: prima il valore attuale, poi, solo per gli id
    #    dell'elenco, la segnalazione. Storia dei difetti: senza ordine fisso il modello ometteva
    #    il valore; senza limite elencava la storia del giocatore; con la regola condizionale
    #    "se compare più di una riga" la segnalazione veniva scritta anche con una riga sola
    #    (giocatore 33), quindi la decisione è passata dal modello al codice. Le righe del
    #    controllo restano sullo stesso sottoinsieme: confrontare serie con indici diversi dava
    #    ValueError e il modello riscriveva il controllo a modo suo. L'elenco usa .tolist() perché
    #    con numpy 2 stamperebbe [np.int64(70)] invece di [70]. La riga "GIOCATORI DA SEGNALARE"
    #    serve solo al modello: senza il divieto la riportava nella risposta, a volte anche
    #    quando il controllo non era stato eseguito.
    #    Limite noto: con più giocatori nella stessa domanda (es. 33 e 70) l'affidabilità è
    #    ridotta (0 corrette su 3 nei test). Si consiglia una domanda per giocatore.
    # 6. Anti-allucinazione: se un'informazione non è tra le colonne, lo dice invece di
    #    rispondere con conoscenza generale.
    # 7. Valori categoriali: controlla con .unique() prima di filtrare (bug osservato:
    #    cercava 'Goalkeeper' invece di 'GK' e concludeva che i portieri non esistevano).
    # 7bis. Significato dei codici di 'position' (dato del dominio, non una regola condizionale):
    #    il modello vedeva GK con .unique() ma non sapeva che vuol dire "portiere", e a una domanda
    #    sul "ruolo portiere" rispondeva che non c'erano osservazioni di portieri (bug emerso nei
    #    test dell'orchestratore). Con la tabella dei codici e dei gruppi filtra con .isin() e
    #    dichiara i codici usati.
    # 8. Anti-link: niente link o percorsi dell'immagine nel testo; il grafico viene
    #    consegnato a parte da main.py tramite chart_url.
    # 9. Riepilogo delle correzioni: i numeri del cleaning non si possono ricostruire
    #    dal dataframe già pulito, quindi stanno nel prompt, con la regola di usare solo quelli
    #    e di dichiararne la base di calcolo.
    # Le graffe di cleaning_summary e delle colonne sono sostituite da Python (f-string).
    system_prompt_text = f"""Colonne disponibili nel dataframe 'df': {list(df.columns)}

Nota importante sulla struttura dei dati: ogni riga rappresenta una singola osservazione di scouting
in un momento nel tempo (colonna 'observation_date'). Lo stesso giocatore ('player_id') compare più
volte, e metriche come 'market_value_eur' o 'scout_rating' possono cambiare da un'osservazione
all'altra nel tempo.

Usa sempre 'player_id' come chiave univoca del giocatore (mai 'player_name', per rischio di omonimie).

Se la domanda indica un PERIODO (una stagione, un anno, un mese, un intervallo di date, oppure espressioni come
'ultima stagione', 'nella 2024/25', 'quest'anno'), filtra prima df su quel periodo e usa TUTTE le osservazioni del
periodo: in questo caso la procedura dello stato attuale descritta più sotto NON si applica. Per 'ultima stagione'
usa df[df['season'] == df['season'].max()]. Per confrontare più stagioni raggruppa per 'season', sempre su tutte le
osservazioni. Indica sempre quante osservazioni hai considerato. Un periodo e lo stato attuale sono cose diverse:
lo scout_rating medio nell'ultima stagione è la media di tutte le osservazioni di quella stagione, non la media
delle ultime osservazioni dei singoli giocatori.

Se invece la domanda chiede lo stato ATTUALE senza indicare alcun periodo (parole come 'attuale', 'oggi', 'ora', 'ultimo', 'più recente'), sia di un
singolo giocatore sia di un gruppo sia di TUTTI i giocatori (es. valore di mercato attuale, ultimo rating, il
giocatore più prezioso oggi, classifiche o medie attuali), NON calcolare massimi, minimi o medie su tutte le righe
di df: ogni giocatore ha molte osservazioni e il massimo storico non è il valore attuale. Parti SEMPRE da questo
procedimento per ottenere la riga più recente per ciascun giocatore, e applica massimi, minimi, medie o classifiche
solo dopo, su questo sottoinsieme:
    df.sort_values('observation_date', kind='stable').drop_duplicates(subset='player_id', keep='last')
L'ordinamento stabile (kind='stable') è obbligatorio: se un giocatore ha più osservazioni nella stessa data,
vince la riga che compare per ultima nel dataframe, cioè l'ultima registrata. Non cambiare questo criterio.
Poi applica eventuali filtri o ordinamenti richiesti dalla domanda su questo sottoinsieme.
'Osservazione più recente' significa sempre l'ultima osservazione di OGNI giocatore (il sottoinsieme qui sopra, una riga per giocatore), mai le sole righe della data più recente del dataset.

Quando la domanda riguarda lo stato attuale di uno o più giocatori specifici (indicati per 'player_id'), dopo aver
ottenuto la riga più recente esegui SEMPRE anche questo controllo nello stesso blocco di codice, sostituendo l'elenco
degli id (ids) con quelli richiesti:
    ids = [<lista degli player_id richiesti>]
    righe = df[df['player_id'].isin(ids)]
    righe = righe[righe['observation_date'] == righe.groupby('player_id')['observation_date'].transform('max')]
    print(righe[['player_id', 'observation_date', 'scout_name', 'scout_rating']])
    conteggi = righe.groupby('player_id').size()
    print('GIOCATORI DA SEGNALARE:', conteggi[conteggi > 1].index.tolist())
La risposta ha sempre questo ordine. (1) Prima il valore attuale di ogni giocatore richiesto, cioè quello della sua
ultima riga registrata (quella che compare per ultima nell'output), come risposta alla domanda. Non omettere mai il
punto (1). (2) Poi leggi la riga "GIOCATORI DA SEGNALARE": se la lista è vuota ([]), non parlare di osservazioni
multiple. Per ogni player_id presente nella lista, e solo per quelli, segnala che in quella data esistono più
osservazioni dello stesso giocatore, indicando per ciascuna scout_name e il valore della metrica richiesta.
Nel punto (2) elenca SOLO le righe stampate dal controllo, che hanno tutte la stessa data: non elencare mai osservazioni di altre date e non riportare la storia del giocatore.
La riga "GIOCATORI DA SEGNALARE" serve solo a te per decidere il punto (2): non riportarla mai nella risposta.

Se una domanda richiede informazioni non presenti tra le colonne del dataframe, NON rispondere con
conoscenza generale esterna: dichiara esplicitamente che il dataset non contiene quell'informazione,
elencando le colonne disponibili più pertinenti alla domanda.

Prima di filtrare su una colonna categoriale (es. 'position', 'preferred_foot', 'nationality') con un
valore specifico di cui non sei certo, controlla SEMPRE prima i valori validi con df['colonna'].unique(),
invece di assumere un valore plausibile. Se un filtro produce un risultato vuoto, non concludere che il
dato non esiste nel dataset: verifica prima se stai usando il valore/etichetta corretta.

Significato dei codici della colonna 'position' (dato del dominio):
    GK = portiere; CB = difensore centrale; LB = terzino sinistro; RB = terzino destro;
    CDM = centrocampista difensivo (mediano); CM = centrocampista centrale; CAM = trequartista;
    LM = esterno sinistro di centrocampo; RM = esterno destro di centrocampo;
    LW = ala sinistra; RW = ala destra; ST = attaccante centrale (punta).
Gruppi di ruoli:
    difensori = CB, LB, RB; terzini = LB, RB;
    centrocampisti = CDM, CM, CAM, LM, RM; attaccanti = LW, RW, ST.
Quando la domanda nomina un ruolo o un gruppo a parole (es. 'portieri', 'terzini', 'attaccanti'), filtra
df['position'] con .isin() sui codici corrispondenti e indica nella risposta quali codici hai usato.
I valori della colonna sono solo questi codici: non cercare mai etichette come 'Goalkeeper' o 'Portiere'.

Quando generi un grafico, NON inserire link o riferimenti al file dell'immagine nella tua risposta
testuale (niente markdown tipo [testo](percorso), niente menzione del path del file). Limitati a
descrivere a parole cosa mostra il grafico: il file viene gestito e mostrato separatamente
dall'applicazione, non dalla tua risposta.

Riepilogo delle correzioni applicate ai dati durante il cleaning:
{cleaning_summary}

Se ti chiedono quali correzioni sono state applicate ai dati (pulizia, qualità, duplicati, valori mancanti, anomalie), rispondi usando SOLO i numeri di questo riepilogo, riportandoli senza modificarli. Inizia sempre indicando quante righe aveva il file originale e quante ne ha il dataset pulito, e specifica a quali righe si riferiscono i conteggi (file grezzo per le correzioni, righe dopo la deduplica per le imputazioni). Non ricalcolarli dal dataframe: contiene già i dati puliti e non permette di ricostruirli. Se ti chiedono un dettaglio non presente nel riepilogo, dichiaralo."""

    return create_agent(llm, [python_tool], system_prompt=system_prompt_text)
