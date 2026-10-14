import { useState } from "react";

// Limite del contratto sul messaggio (il back end rifiuta oltre 2000 caratteri).
const MAX_LENGTH = 2000;
// Il conteggio compare solo vicino al limite, per non distrarre.
const COUNTER_FROM = 1800;

/**
 * Campo di testo e pulsante di invio.
 *
 * @param {{
 *   onSend: (text: string) => boolean,
 *   busy: boolean,
 * }} props
 *   onSend restituisce true se il messaggio è partito: solo allora il campo si svuota.
 *   Se è vuoto o c'è già una richiesta in corso resta com'è.
 */
export default function ChatInput({ onSend, busy }) {
  const [value, setValue] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    if (onSend(value)) setValue("");
  }

  const nearLimit = value.length >= COUNTER_FROM;

  return (
    <form onSubmit={handleSubmit}>
      <div className="flex items-center gap-2 rounded-full border border-white/15 bg-pitch-900 p-1 pl-4 shadow-lg shadow-black/40 focus-within:border-edge">
        {/* text-base (16px): evita lo zoom automatico di iOS al focus.
            Durante l'attesa: readOnly e non disabled, così su mobile la tastiera non si chiude. */}
        <input
          id="chat-message"
          name="message"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          maxLength={MAX_LENGTH}
          readOnly={busy}
          aria-disabled={busy}
          aria-label="Scrivi un messaggio all'assistente"
          placeholder={
            busy ? "L'assistente sta elaborando…" : "Scrivi all'assistente…"
          }
          enterKeyHint="send"
          autoComplete="off"
          className="min-w-0 flex-1 bg-transparent py-2 text-base text-white outline-none placeholder:text-white/55"
        />
        <button
          type="submit"
          aria-label="Invia"
          disabled={!value.trim() || busy}
          className="grid size-11 shrink-0 place-items-center rounded-full bg-edge text-pitch-950 transition disabled:opacity-40"
        >
          {busy ? (
            <span className="size-5 animate-spin rounded-full border-2 border-pitch-950/30 border-t-pitch-950" />
          ) : (
            <svg
              viewBox="0 0 24 24"
              className="size-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          )}
        </button>
      </div>
      {nearLimit && (
        <p
          className={`mt-1 pr-3 text-right text-xs ${value.length >= MAX_LENGTH ? "text-red-300" : "text-white/60"}`}
        >
          {value.length}/{MAX_LENGTH}
        </p>
      )}
    </form>
  );
}
