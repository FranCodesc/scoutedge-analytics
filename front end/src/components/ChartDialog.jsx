import { useEffect, useRef, useState } from "react";

/**
 * Finestra con il grafico ingrandito, basata sull'elemento nativo <dialog>.
 * Con showModal() il browser pensa a: sfondo oscurato, blocco dell'interazione con il
 * resto della pagina, focus tenuto dentro la finestra, chiusura con Esc e ritorno del
 * focus al pulsante "Ingrandisci" alla chiusura.
 *
 * Il componente va montato solo quando la finestra deve essere aperta e smontato alla
 * chiusura: l'apertura avviene al montaggio, la chiusura chiama onClose.
 *
 * Se l'immagine non si carica (file cancellato, servizio riavviato) al suo posto compare
 * un testo di riserva e la finestra resta aperta, chiudibile come sempre.
 *
 * @param {{ src: string, onClose: () => void }} props
 *   src: indirizzo già validato da chartSrc().
 */
export default function ChartDialog({ src, onClose }) {
  const dialogRef = useRef(null);

  // Se l'immagine non si carica (file cancellato dalla pulizia dei grafici, servizio
  // riavviato) si mostra un testo al posto dell'icona rotta; la finestra resta aperta.
  const [failed, setFailed] = useState(false);

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
      aria-label="Grafico ingrandito"
      // m-auto: il reset di Tailwind azzera i margini che centrano la finestra.
      className="m-auto w-[min(92vw,64rem)] overflow-visible bg-transparent p-0 backdrop:bg-black/80 backdrop:backdrop-blur-sm"
    >
      <div className="relative rounded-xl bg-white p-2 shadow-2xl">
        {failed ? (
          <p className="grid min-h-48 place-items-center p-6 text-center text-sm text-pitch-950">
            Il grafico non è al momento disponibile.
          </p>
        ) : (
          <img
            src={src}
            alt="Grafico generato dall'analisi dei dati"
            onError={() => setFailed(true)}
            className="block max-h-[calc(92dvh-1rem)] w-full rounded-lg object-contain"
          />
        )}
        <button
          type="button"
          onClick={() => dialogRef.current?.close()}
          aria-label="Chiudi"
          title="Chiudi"
          className="absolute -right-3 -top-3 grid size-9 place-items-center rounded-full border border-white/30 bg-pitch-950 text-white shadow-lg transition hover:border-edge hover:text-edge"
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
    </dialog>
  );
}
