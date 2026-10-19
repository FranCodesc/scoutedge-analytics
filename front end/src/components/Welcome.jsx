// Le 4 domande della demo. `prompt` è il testo esatto che viene inviato; titolo e
// descrizione sono solo etichette della scheda.
const SUGGESTIONS = [
  {
    icon: "🕑",
    title: "Tempi di risposta",
    hint: "SLA per le richieste ad alta priorità",
    prompt:
      "Qual è il tempo di prima risposta per una richiesta ad alta priorità?",
  },
  {
    icon: "💰",
    title: "Valore di mercato",
    hint: "I 10 giocatori più preziosi, con grafico",
    prompt:
      "Quali sono i 10 giocatori con il valore di mercato attuale più alto? Mostrami anche un grafico.",
  },
  {
    icon: "🛡️",
    title: "Difensori centrali",
    hint: "Metodologia e i 3 CB migliori nei duelli",
    prompt:
      "Secondo la metodologia, quali metriche contano di più per i difensori centrali? Poi mostrami i 3 CB con il duels_won_pct attuale più alto.",
  },
  {
    icon: "🧹",
    title: "Pulizia dei dati",
    hint: "Le correzioni applicate al dataset",
    prompt: "Quali correzioni avete applicato ai dati?",
  },
];

/**
 * Schermata di benvenuto: schede con le domande suggerite. Un clic invia la domanda.
 * @param {{ onPick: (prompt: string) => void }} props
 */
export default function Welcome({ onPick }) {
  return (
    <div className="mt-1 grid animate-fade-up gap-2">
      <p className="px-1 text-xs font-medium uppercase tracking-widest text-white/90 [text-shadow:0_1px_3px_rgba(0,0,0,0.6)]">
        Prova a chiedere
      </p>
      {SUGGESTIONS.map((s) => (
        <button
          key={s.title}
          type="button"
          onClick={() => onPick(s.prompt)}
          className="flex items-center gap-3 rounded-xl border border-white/15 bg-pitch-950/80 p-3 text-left transition hover:border-edge hover:bg-pitch-950 active:scale-[0.98]"
        >
          <span
            className="grid size-10 shrink-0 place-items-center rounded-lg bg-white/5 text-xl"
            aria-hidden="true"
          >
            {s.icon}
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold">{s.title}</span>
            <span className="block text-xs text-white/55">{s.hint}</span>
          </span>
        </button>
      ))}
    </div>
  );
}
