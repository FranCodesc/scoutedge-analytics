import Avatar from "./Avatar";

/**
 * Scheda di errore con "Riprova". Il messaggio è quello di ApiError (già in italiano e
 * mostrabile così com'è). La variante "offline" cambia titolo e icona: vale quando il
 * browser è offline o il server non risponde.
 * "Riprova" compare solo se viene passato `onRetry`: per gli errori in cui è la richiesta
 * a essere sbagliata (es. messaggio troppo lungo) rinviarla darebbe lo stesso rifiuto.
 *
 * @param {{
 *   message: string,
 *   offline?: boolean,
 *   onRetry?: () => void,
 *   disabled?: boolean,
 * }} props
 */
export default function ErrorCard({
  message,
  offline = false,
  onRetry,
  disabled = false,
}) {
  return (
    <div className="flex animate-fade-up items-end gap-2" role="alert">
      <Avatar />
      <div className="max-w-[82%] rounded-2xl rounded-bl-md border border-red-400/40 bg-pitch-950/95 p-3.5 shadow-md">
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-red-400/15 text-red-300">
            <svg
              viewBox="0 0 24 24"
              className="size-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              {offline ? (
                <path d="M2 8.8a15 15 0 0 1 4.2-2.6M22 8.8a15 15 0 0 0-8.3-3.7M5 12.9a10 10 0 0 1 3.6-2.3M19 12.9a10 10 0 0 0-3.3-2.2M8.5 16.4a5 5 0 0 1 7 0M12 20h.01M3 3l18 18" />
              ) : (
                <path d="M12 9v4m0 4h.01M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
              )}
            </svg>
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold">
              {offline ? "Nessuna connessione" : "Qualcosa è andato storto"}
            </p>
            <p className="mt-0.5 text-xs leading-snug text-white/70">
              {message}
            </p>
          </div>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            disabled={disabled}
            className="mt-3 flex min-h-10 w-full items-center justify-center gap-2 rounded-xl border border-red-300/40 text-sm font-medium text-red-200 transition hover:bg-red-400/10 active:scale-[0.98] disabled:opacity-40"
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
              <path d="M21 12a9 9 0 1 1-3-6.7M21 3v6h-6" />
            </svg>
            Riprova
          </button>
        )}
      </div>
    </div>
  );
}
