import { useState } from "react";

function IconButton({ label, onClick, disabled, children }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="grid size-8 place-items-center rounded-lg border border-white/15 text-white/70 transition hover:border-edge hover:text-edge disabled:pointer-events-none disabled:opacity-40"
    >
      <svg
        viewBox="0 0 24 24"
        className="size-4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {children}
      </svg>
    </button>
  );
}

/**
 * Pannello dei grafici (solo desktop): mostra in grande l'ULTIMO grafico reale della
 * conversazione. Senza grafici, uno stato vuoto senza dati inventati.
 * Le sue dimensioni non dipendono dal contenuto: stesso pannello da vuoto, con un
 * grafico o con un errore.
 *
 * @param {{
 *   src: string | null,
 *   onZoom?: () => void,
 *   onDownload?: () => void,
 *   downloading?: boolean,
 *   downloadError?: string | null,
 * }} props
 *   src: indirizzo già validato da chartSrc(), oppure null.
 *   onZoom e onDownload: se mancano, i rispettivi pulsanti restano spenti.
 *   downloading: true mentre il download è in corso (spegne "Scarica").
 *   downloadError: testo dell'errore di download, o null.
 */
export default function ChartsPanel({
  src,
  onZoom,
  onDownload,
  downloading,
  downloadError,
}) {
  // Si ricorda quale indirizzo non si è caricato (e non un semplice "fallito"): quando
  // arriva un grafico nuovo l'esito vecchio non vale più e non serve nessun reset.
  const [failedSrc, setFailedSrc] = useState(null);
  const failed = src !== null && failedSrc === src;
  const usable = src !== null && !failed;

  return (
    <section
      className="relative hidden min-w-0 flex-1 basis-0 origin-center flex-col overflow-hidden rounded-xl border border-white/25 bg-pitch-950/70 transition-transform duration-300 ease-out hover:z-10 hover:scale-[1.03] hover:shadow-2xl motion-reduce:transition-none motion-reduce:hover:scale-100 lg:flex"
      aria-label="Area grafici"
    >
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-2.5">
        <h2 className="font-display text-xl font-bold tracking-wide">
          Grafici
        </h2>
        <div className="flex gap-2">
          <IconButton
            label="Ingrandisci"
            onClick={onZoom}
            disabled={!usable || !onZoom}
          >
            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
          </IconButton>
          <IconButton
            label="Scarica"
            onClick={onDownload}
            disabled={!usable || !onDownload || downloading}
          >
            <path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16" />
          </IconButton>
        </div>
      </div>

      {downloadError && (
        <p
          role="alert"
          className="border-b border-red-300/30 bg-red-950/60 px-4 py-1.5 text-xs text-red-100"
        >
          {downloadError}
        </p>
      )}

      {/* Area del grafico a misura fissa: "relative" + contenuti in posizione
          assoluta, così le dimensioni dell'immagine non possono mai allargare
          o allungare il pannello. */}
      <div className="relative min-h-0 flex-1">
        {src === null && (
          <div className="absolute inset-0 grid place-items-center p-4 text-center">
            <div>
              <p className="text-sm font-semibold">Nessun grafico ancora</p>
              <p className="mx-auto mt-1 max-w-xs text-xs text-white/70">
                Chiedi un'analisi con un grafico: l'ultimo comparirà qui, in
                grande.
              </p>
            </div>
          </div>
        )}
        {failed && (
          <p className="absolute inset-0 grid place-items-center p-4 text-center text-sm text-white/70">
            Il grafico non è al momento disponibile.
          </p>
        )}
        {usable && (
          <img
            src={src}
            alt="Grafico generato dall'analisi dei dati"
            onError={() => setFailedSrc(src)}
            className="absolute inset-4 size-[calc(100%-2rem)] animate-fade-up rounded-lg bg-white object-contain"
          />
        )}
      </div>
    </section>
  );
}
