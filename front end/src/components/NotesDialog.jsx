import { useEffect, useRef } from "react";

// Testo delle note: solo contenuto statico, nessuna chiamata di rete. Se l'architettura
// o i limiti cambiano, va riletto insieme al README della radice del repository.
const SECTIONS = [
  {
    title: "Cos'è",
    text: "Progetto finale del master «AI e Agenti AI per il Business» (Start2Impact / UniMarconi). ScoutEdge Analytics è un'azienda immaginaria che vende software di scouting e performance analytics ai club di calcio.",
  },
  {
    title: "Come funziona",
    text: "Per ogni domanda un modello linguistico decide da solo la strada: cercare nel manuale interno dell'azienda (RAG su ChromaDB), far analizzare il dataset delle osservazioni di scouting a un servizio Python, anche con grafici, oppure usare prima il manuale e poi i dati. Se la domanda non c'entra con ScoutEdge, lo dice.",
  },
  {
    title: "Architettura",
    text: "Front end React e Vite; back end Node.js con Express e LangChain.js, che orchestra gli strumenti con il function calling; data agent FastAPI con pandas; ChromaDB per il manuale. Il browser parla solo con il back end.",
  },
  {
    title: "Limiti",
    text: "Il data agent esegue codice generato dal modello senza sandbox: il sistema è pensato per un uso locale e dimostrativo. Le risposte dei modelli non sono deterministiche, quindi i numeri importanti vanno verificati. In produzione servirebbero una sandbox isolata, autenticazione e limiti di frequenza.",
  },
];

// Autore del progetto, mostrato in fondo alle note.
const AUTHOR = "Francesco Benassi";

/**
 * Finestra "Note sul progetto", basata sull'elemento nativo <dialog> come ChartDialog:
 * con showModal() il browser pensa a sfondo oscurato, blocco del resto della pagina,
 * focus tenuto dentro, chiusura con Esc e ritorno del focus al pulsante "Note".
 *
 * Il componente va montato solo quando la finestra deve essere aperta e smontato alla
 * chiusura: l'apertura avviene al montaggio, la chiusura chiama onClose.
 * Nessuna animazione: così "riduci movimento" è rispettato senza regole in più.
 *
 * @param {{ onClose: () => void }} props
 */
export default function NotesDialog({ onClose }) {
  const dialogRef = useRef(null);

  // Apertura al montaggio. Il controllo `open` evita un errore se l'effetto
  // dovesse girare due volte (StrictMode in sviluppo).
  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={dialogRef}
      // "close" scatta con Esc, con il pulsante ✕ e con il click fuori: in ogni caso
      // lo stato di chi ci ha montato viene aggiornato qui, in un solo punto.
      onClose={onClose}
      // Il click sullo sfondo oscurato ha come bersaglio il <dialog> stesso (il
      // contenuto è nel div interno): in quel caso si chiude.
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
      aria-labelledby="notes-title"
      // m-auto: il reset di Tailwind azzera i margini che centrano la finestra.
      // text-white: nel livello superiore il testo non eredita il colore della pagina.
      className="m-auto w-[min(92vw,34rem)] overflow-hidden rounded-xl border border-white/25 bg-pitch-950 p-0 text-white shadow-2xl backdrop:bg-black/80 backdrop:backdrop-blur-sm"
    >
      {/* Il contenuto scorre dentro la finestra: su schermi bassi (telefono in
          orizzontale) la finestra non esce dallo schermo. */}
      <div className="max-h-[85dvh] overflow-y-auto p-5">
        <div className="flex items-start justify-between gap-3">
          <h2
            id="notes-title"
            className="font-display text-2xl font-bold tracking-wide"
          >
            Note sul progetto
          </h2>
          <button
            type="button"
            onClick={() => dialogRef.current?.close()}
            aria-label="Chiudi"
            title="Chiudi"
            className="grid size-8 shrink-0 place-items-center rounded-lg border border-white/15 text-white/70 transition hover:border-edge hover:text-edge"
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
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="mt-3 space-y-4">
          {SECTIONS.map(({ title, text }) => (
            <section key={title}>
              <h3 className="text-xs font-semibold uppercase tracking-widest text-edge">
                {title}
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-white/85">
                {text}
              </p>
            </section>
          ))}
        </div>

        <p className="mt-5 border-t border-white/10 pt-3 text-xs text-white/60">
          Autore: <span className="font-semibold text-white/85">{AUTHOR}</span>
        </p>
      </div>
    </dialog>
  );
}
