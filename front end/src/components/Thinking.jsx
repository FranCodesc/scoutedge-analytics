import { useEffect, useState } from "react";
import Avatar from "./Avatar";

// Dopo questo tempo si avvisa che le analisi sui dati possono essere lente.
const SLOW_AFTER_MS = 10_000;

/**
 * Indicatore di attesa ("Sto elaborando…"). Il componente esiste solo mentre c'è una
 * richiesta in corso: ogni attesa riparte da zero, quindi l'avviso "lento" compare
 * solo se la richiesta dura davvero.
 * Il testo è volutamente neutro: non sappiamo quale strumento sta lavorando, e non
 * mostriamo passaggi inventati.
 */
export default function Thinking() {
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(id);
  }, []);

  return (
    <div
      className="flex animate-fade-up items-end gap-2"
      role="status"
      aria-label="L'assistente sta elaborando la risposta"
    >
      <Avatar />
      <div className="rounded-2xl rounded-bl-md border border-white/10 bg-pitch-950/90 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex gap-1" aria-hidden="true">
            {[0, 150, 300].map((delay) => (
              <span
                key={delay}
                className="size-2 animate-bounce rounded-full bg-edge"
                style={{ animationDelay: `${delay}ms` }}
              />
            ))}
          </div>
          <span className="text-sm text-white/80">
            Sto elaborando la richiesta…
          </span>
        </div>
        {slow && (
          <p className="mt-2 max-w-xs animate-fade-up text-xs text-white/60">
            Le analisi sui dati possono richiedere fino a un minuto.
          </p>
        )}
      </div>
    </div>
  );
}
