/**
 * Costruisce le etichette nell'ordine di `toolsUsed` (ordine di primo utilizzo, dal contratto):
 *  - search_handbook con passaggi trovati → una etichetta per ogni sezione in `sources`;
 *  - search_handbook senza sezioni citate (nessun passaggio trovato, oppure manuale
 *    non raggiungibile: il front end non distingue i due casi) → etichetta neutra;
 *  - analyze_data → "Analisi dati".
 * Con `toolsUsed` vuoto non c'è nessuna etichetta. Valori sconosciuti sono ignorati,
 * così un nuovo strumento del back end non rompe l'interfaccia.
 */
function buildLabels(toolsUsed, sources) {
  const labels = [];
  for (const tool of toolsUsed) {
    if (tool === "search_handbook") {
      if (sources.length === 0) {
        labels.push("📄 Handbook (nessuna sezione citata)");
      } else {
        for (const { section } of sources)
          labels.push(`📄 Handbook — ${section}`);
      }
    } else if (tool === "analyze_data") {
      labels.push("📊 Analisi dati");
    }
  }
  return labels;
}

/**
 * Etichette discrete che mostrano da dove viene la risposta (manuale e/o analisi dati).
 * @param {{ toolsUsed: string[], sources: { section: string }[] }} props
 */
export default function ToolBadges({ toolsUsed, sources }) {
  const labels = buildLabels(toolsUsed, sources);
  if (labels.length === 0) return null;

  return (
    <ul
      aria-label="Fonti della risposta"
      className="mt-2 flex flex-wrap gap-1.5"
    >
      {labels.map((label) => (
        <li
          key={label}
          className="rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5 text-[11px] leading-tight text-white/80"
        >
          {label}
        </li>
      ))}
    </ul>
  );
}
