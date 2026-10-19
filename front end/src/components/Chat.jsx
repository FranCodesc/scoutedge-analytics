import { useCallback, useEffect, useRef, useState } from "react";
import { useChartDownload } from "../hooks/useChartDownload";
import { useChat } from "../hooks/useChat";
import { useOnlineStatus } from "../hooks/useOnlineStatus";
import ChartDialog from "./ChartDialog";
import ChartsPanel from "./ChartsPanel";
import ChatInput from "./ChatInput";
import ErrorCard from "./ErrorCard";
import MessageBubble from "./MessageBubble";
import NotesDialog from "./NotesDialog";
import PitchBackground from "./PitchBackground";
import Thinking from "./Thinking";
import Welcome from "./Welcome";

// Sotto questa distanza dal fondo la chat si considera "in fondo" e segue le nuove risposte.
const STICK_THRESHOLD_PX = 120;
// Durante lo scroll animato partono molti eventi "scroll" con una distanza ancora
// grande: per questo tempo li ignoro, altrimenti il pulsante ⬇ lampeggerebbe.
const PROGRAMMATIC_SCROLL_MS = 700;
// Una risposta è "più alta della zona visibile" se supera l'altezza della lista meno
// questo margine (il padding alto e basso della lista, circa 16 px per lato).
const FIT_SLACK_PX = 32;
// Distanza tra il bordo alto della lista e l'inizio di una risposta lunga portata in alto.
const LONG_ANSWER_TOP_MARGIN_PX = 12;

// Stile comune dei pulsanti dell'intestazione ("Note" e "Nuova chat").
const HEADER_BUTTON_CLASS =
  "rounded-lg border border-white/20 px-3 py-1.5 text-sm font-semibold transition hover:border-edge hover:text-edge";

/** Comportamento dello scroll: con "riduci movimento" è sempre istantaneo. */
function scrollBehavior(smooth) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  return smooth && !reduce ? "smooth" : "auto";
}

// Guscio alto quanto la finestra; sul campo da calcio, chat a sinistra e pannello
// grafici a destra (da 1024px) con la stessa altezza. Scorre solo la lista dei messaggi.
export default function Chat() {
  const { messages, busy, lastChartSrc, send, retry, newChat } = useChat();
  const online = useOnlineStatus();
  const { download, downloading, downloadError } =
    useChartDownload(lastChartSrc);

  // Contenitore scorrevole dei messaggi: lo scroll non è più della pagina.
  const scrollerRef = useRef(null);
  // true = l'utente è in fondo e le nuove risposte lo portano in fondo.
  // È un ref (non uno stato) perché cambia a ogni scroll e non deve far ridisegnare.
  const stickRef = useRef(true);
  // Fino a questo istante gli eventi di scroll sono dovuti al nostro scroll automatico.
  const ignoreScrollUntilRef = useRef(0);
  // Id dell'ultima risposta dell'assistente (benvenuto escluso): serve a ritrovarne il
  // fumetto per misurarlo.
  const lastAnswerIdRef = useRef(null);
  // Mostra il pulsante ⬇ quando ci sono contenuti sotto la zona visibile.
  const [showJump, setShowJump] = useState(false);
  // Finestra con il grafico ingrandito (aperta dal pulsante "Ingrandisci").
  const [zoomOpen, setZoomOpen] = useState(false);
  // Finestra con le note sul progetto (aperta dal pulsante "Note").
  const [notesOpen, setNotesOpen] = useState(false);

  /** Porta il contenitore in fondo; con "riduci movimento" lo scroll è istantaneo. */
  const scrollToBottom = useCallback((smooth) => {
    const el = scrollerRef.current;
    if (!el) return;
    ignoreScrollUntilRef.current = performance.now() + PROGRAMMATIC_SCROLL_MS;
    el.scrollTo({ top: el.scrollHeight, behavior: scrollBehavior(smooth) });
  }, []);

  /**
   * Se l'ultima risposta è più alta della zona visibile, ne porta l'INIZIO in alto
   * (invece della fine, che farebbe perdere il principio del testo), smette di seguire
   * il fondo e mostra il pulsante ⬇. Se la risposta sta dentro non fa nulla.
   * @returns {boolean} true se ha scorso; false se la risposta sta dentro e il
   *   chiamante deve scendere in fondo come al solito.
   */
  const alignLongAnswer = useCallback((smooth) => {
    const el = scrollerRef.current;
    const id = lastAnswerIdRef.current;
    if (!el || id === null) return false;
    const bubble = el.querySelector(`[data-message-id="${id}"]`);
    if (!bubble || bubble.offsetHeight <= el.clientHeight - FIT_SLACK_PX) {
      return false;
    }
    ignoreScrollUntilRef.current = performance.now() + PROGRAMMATIC_SCROLL_MS;
    el.scrollTo({
      top: Math.max(0, bubble.offsetTop - LONG_ANSWER_TOP_MARGIN_PX),
      behavior: scrollBehavior(smooth),
    });
    stickRef.current = false;
    setShowJump(true);
    return true;
  }, []);

  // Scroll fatto dall'utente: aggiorna "sono in fondo?" e il pulsante ⬇.
  const handleScroll = useCallback(() => {
    if (performance.now() < ignoreScrollUntilRef.current) return;
    const el = scrollerRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = distance < STICK_THRESHOLD_PX;
    stickRef.current = atBottom;
    setShowJump(!atBottom);
  }, []);

  // Nuovo contenuto (messaggio, errore, indicatore di attesa):
  // - se l'utente ha appena inviato, o la chat è appena ripartita, scendo sempre in fondo;
  // - se era già in fondo e arriva una risposta più alta della zona visibile, ne porto
  //   l'inizio in alto (alignLongAnswer);
  // - se era già in fondo, in tutti gli altri casi lo seguo;
  // - altrimenti non lo disturbo e mostro il pulsante ⬇.
  // Il lavoro avviene in un callback di requestAnimationFrame: così legge le misure
  // dopo il disegno e aggiorna lo stato fuori dal corpo dell'effetto.
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (last?.role === "user" || messages.length === 1) {
      stickRef.current = true;
    }
    // Il benvenuto (unico messaggio) non è una risposta da allineare.
    const isAnswer = last?.role === "assistant" && messages.length > 1;
    if (isAnswer) lastAnswerIdRef.current = last.id;

    const frame = requestAnimationFrame(() => {
      if (stickRef.current) {
        if (!(isAnswer && alignLongAnswer(true))) {
          scrollToBottom(true);
          setShowJump(false);
        }
      } else {
        setShowJump(true);
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [messages, busy, scrollToBottom, alignLongAnswer]);

  // Quando un grafico finisce di caricarsi l'altezza della bolla cresce:
  // - se non ero in fondo (anche perché la risposta è già stata portata in alto)
  //   non mi muovo e segnalo che c'è altro sotto;
  // - se ero in fondo e ora la risposta è più alta della zona visibile ne porto
  //   l'inizio in alto; altrimenti resto in fondo (istantaneo).
  const handleChartLoad = useCallback(() => {
    if (!stickRef.current) {
      setShowJump(true);
      return;
    }
    if (!alignLongAnswer(false)) scrollToBottom(false);
  }, [alignLongAnswer, scrollToBottom]);

  // Click sul pulsante ⬇: da qui in poi si torna a seguire le risposte.
  const handleJump = useCallback(() => {
    stickRef.current = true;
    setShowJump(false);
    scrollToBottom(true);
  }, [scrollToBottom]);

  return (
    // Guscio: altezza della finestra, niente scroll di pagina; il padding in alto
    // rispetta la tacca degli smartphone (safe area).
    <div className="flex h-dvh flex-col overflow-hidden bg-[radial-gradient(ellipse_at_top,var(--color-pitch-900),var(--color-pitch-950))] pt-[env(safe-area-inset-top)] text-white">
      <header className="mx-auto flex w-full max-w-7xl shrink-0 items-center justify-between px-4 py-3 lg:px-6">
        <h1 className="font-display text-2xl font-bold tracking-wide">
          Scout<span className="text-edge">Edge</span>
        </h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setNotesOpen(true)}
            aria-haspopup="dialog"
            title="Note sul progetto"
            className={HEADER_BUTTON_CLASS}
          >
            Note
          </button>
          <button type="button" onClick={newChat} className={HEADER_BUTTON_CLASS}>
            Nuova chat
          </button>
        </div>
      </header>

      <div className="mx-auto flex min-h-0 w-full max-w-7xl flex-1 flex-col px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:px-6 lg:pb-6">
        {/* Banner offline: avvisa subito, senza aspettare che un invio fallisca */}
        {!online && (
          <div
            role="status"
            className="mb-2 shrink-0 rounded-lg border border-amber-300/40 bg-amber-950/80 px-3 py-2 text-sm text-amber-100"
          >
            Sei offline: i messaggi non possono essere inviati finché la
            connessione non torna.
          </div>
        )}

        {/* Riquadro del campo: chat e pannello stanno sopra, con un margine
            interno (inset-[3%]) che li stacca dai bordi del campo. */}
        <main className="relative min-h-0 flex-1 overflow-hidden rounded-2xl border border-white/10 shadow-2xl shadow-black/60">
          <PitchBackground />

          <div className="absolute inset-[3%] flex gap-3 p-1.5 lg:gap-6 lg:p-7">
            {/* Colonna della chat: min-h-0 serve perché il contenitore dei messaggi
                possa restringersi e scorrere invece di allargare la pagina. */}
            <div className="relative flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-white/25 bg-pitch-950/70 lg:w-104 lg:flex-none">
              {/* Wrapper "relative": il pulsante ⬇ si posiziona rispetto alla zona
                  dei messaggi, e la lista (absolute inset-0) non dipende dal contenuto. */}
              <div className="relative min-h-0 flex-1">
                {/* scrollbar-none: la barra di scorrimento sul campo scuro stonava;
                    si scorre con rotella/trackpad/tocco e c'è il pulsante ⬇. */}
                <div
                  ref={scrollerRef}
                  onScroll={handleScroll}
                  role="log"
                  aria-live="polite"
                  className="scrollbar-none absolute inset-0 flex flex-col gap-2.5 overflow-y-auto overscroll-contain px-4 py-4"
                >
                  {messages.map((m) =>
                    m.role === "error" ? (
                      <ErrorCard
                        key={m.id}
                        message={m.text}
                        offline={m.offline}
                        onRetry={m.retryable ? () => retry(m) : undefined}
                        disabled={busy}
                      />
                    ) : (
                      <MessageBubble
                        key={m.id}
                        message={m}
                        onChartLoad={handleChartLoad}
                      />
                    ),
                  )}

                  {/* Le card di suggerimento compaiono solo con la chat appena aperta */}
                  {messages.length === 1 && !busy && <Welcome onPick={send} />}
                  {busy && <Thinking />}
                </div>

                {showJump && (
                  <button
                    type="button"
                    onClick={handleJump}
                    aria-label="Vai all'ultimo messaggio"
                    title="Vai all'ultimo messaggio"
                    className="absolute bottom-3 right-4 grid size-9 animate-fade-up place-items-center rounded-full border border-edge/60 bg-pitch-950/90 text-edge shadow-lg transition hover:bg-edge hover:text-pitch-950"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      className="size-4"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M12 5v14m0 0l-6-6m6 6l6-6" />
                    </svg>
                  </button>
                )}
              </div>

              <div className="shrink-0 border-t border-white/10 p-3">
                <ChatInput onSend={send} busy={busy} />
              </div>
            </div>

            {/* Colonna dei grafici: nascosta sotto 1024px; da lì in su ha la stessa
                altezza della chat perché le due colonne si allungano insieme. */}
            <div className="hidden min-w-0 flex-1 lg:flex">
              <ChartsPanel
                src={lastChartSrc}
                onZoom={() => setZoomOpen(true)}
                onDownload={download}
                downloading={downloading}
                downloadError={downloadError}
              />
            </div>
          </div>
        </main>
      </div>

      {/* Montate solo quando servono: si aprono al montaggio, onClose le smonta */}
      {zoomOpen && lastChartSrc && (
        <ChartDialog src={lastChartSrc} onClose={() => setZoomOpen(false)} />
      )}
      {notesOpen && <NotesDialog onClose={() => setNotesOpen(false)} />}
    </div>
  );
}
