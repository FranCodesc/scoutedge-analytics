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
nel processo del servizio, senza sandbox, e quel processo conosce la chiave OpenAI.
Nella demo online il rischio è ridotto, non eliminato, da difese a strati: servizio in
ascolto solo su 127.0.0.1, limite di frequenza, chiave dedicata con tetto di spesa,
utente non root (vedi la sezione sulla sicurezza nella documentazione del progetto).
"""

import io
import contextlib
import ast
import uuid
import threading
import re
import time
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

# Limite (in caratteri) del testo restituito al modello: i DataFrame si stampano con tutte le
# colonne e un risultato grande farebbe crescere i token. Oltre il limite il testo si tronca con
# una nota fissa, perché il modello non riempia i vuoti inventando i dati.
MAX_TOOL_OUTPUT = 6000

# Tempo massimo di attesa per entrare nell'esecuzione del codice del modello. Il codice dura
# di norma meno di un secondo: se un'altra richiesta tiene il lock più a lungo, è meglio
# rispondere con un errore che far aspettare (il back end ha un timeout di 90 s).
ATTESA_MASSIMA_LOCK_S = 30

# Mentre esegue il codice del modello, il tool sostituisce per tutto il processo
# savefig/close/show di matplotlib e sys.stdout, e usa le figure globali di pyplot e le
# opzioni globali di pandas: due richieste insieme si sovrascriverebbero a vicenda.
# Per questo l'esecuzione è serializzata da questo lock; la chiamata al modello
# resta fuori e continua a funzionare in parallelo.
_lock_esecuzione = threading.Lock()

# Conservazione dei grafici: i PNG più vecchi di 2 ore o oltre i 200 più recenti si cancellano,
# per non riempire il disco. Solo i file con il nome esatto dei grafici del tool.
CONSERVAZIONE_GRAFICI_S = 2 * 60 * 60
MAX_GRAFICI = 200
NOME_GRAFICO = re.compile(r"chart_[0-9a-f]{8}\.png")

# Valore assoluto, sull'intervallo visibile di un asse, da cui in poi i numeri si scrivono
# per esteso con il punto delle migliaia invece della notazione scientifica (es. 1e7).
SOGLIA_ASSE_GRANDE = 1_000_000


def _cancella(percorso):
    """Cancella un file; se è già sparito o non si può cancellare, l'analisi non si ferma."""
    try:
        percorso.unlink()
    except OSError:
        pass


def pulisci_grafici(spazio_per_nuovo=0, adesso=None):
    """Cancella i grafici troppo vecchi o in eccesso in CHARTS_DIR.

    Si toccano solo i file chart_xxxxxxxx.png. `spazio_per_nuovo` lascia libero il posto
    per i file che stanno per essere salvati; `adesso` serve ai test per fissare l'ora.
    Va chiamata con il lock già preso (o all'avvio, quando non ci sono richieste)."""
    if adesso is None:
        adesso = time.time()

    grafici = []
    for percorso in CHARTS_DIR.iterdir():
        if NOME_GRAFICO.fullmatch(percorso.name):
            try:
                grafici.append((percorso.stat().st_mtime, percorso))
            except OSError:
                pass  # sparito nel frattempo

    # 1) troppo vecchi
    recenti = []
    for data, percorso in grafici:
        if data < adesso - CONSERVAZIONE_GRAFICI_S:
            _cancella(percorso)
        else:
            recenti.append((data, percorso))

    # 2) in eccesso: si tolgono i più vecchi
    recenti.sort(key=lambda voce: (voce[0], voce[1].name))
    in_eccesso = len(recenti) - (MAX_GRAFICI - spazio_per_nuovo)
    for data, percorso in recenti[:max(in_eccesso, 0)]:
        _cancella(percorso)


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

    def _esegui(code: str) -> str:
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
            # Il contesto pandas mostra tutte le colonne: con la forma abbreviata il modello
            # inventava i valori delle colonne nascoste. 250 caratteri evitano righe spezzate male.
            #
            # Il salvataggio dei grafici è riservato al tool: durante l'esecuzione savefig, close
            # e show non fanno nulla, così ogni figura finisce in charts/ con il nome del tool.
            # Non è una sandbox (docs/decisions/06-esecuzione-del-codice-generato.md).
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
                pulisci_grafici(spazio_per_nuovo=1)
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
        if not _lock_esecuzione.acquire(timeout=ATTESA_MASSIMA_LOCK_S):
            return ("Errore: il servizio di analisi è occupato con un'altra richiesta. "
                    "Riprova tra qualche istante.")
        try:
            return _esegui(code)
        finally:
            _lock_esecuzione.release()
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

    # System prompt: ogni sezione corregge un comportamento sbagliato osservato, quindi ordine e
    # formulazione contano. Le regole sono procedure con codice esatto e un ordine fisso della
    # risposta, con segnaposto (<...>) negli esempi: docs/decisions/03-regole-del-prompt-del-data-agent.md.
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

Quando la domanda riguarda lo stato attuale di uno o più giocatori specifici (indicati per 'player_id' in qualunque forma:
«giocatore <id>», «giocatore con ID <id>», «player_id <id>», «id <id>», o più id insieme), dopo aver
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
