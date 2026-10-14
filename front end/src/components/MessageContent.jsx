import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/*
 * Render del Markdown delle risposte. Sicurezza:
 *  - niente rehype-raw e niente dangerouslySetInnerHTML: l'HTML grezzo nel testo viene
 *    mostrato come testo, mai interpretato;
 *  - react-markdown scarta da solo i link con schemi pericolosi (es. javascript:);
 *  - le immagini sono escluse: il contratto dice che `reply` non contiene mai immagini
 *    (il grafico arriva da chartUrl), quindi un ![](url) sarebbe un caricamento di una
 *    risorsa esterna scelta da chi ha scritto il testo.
 */
const components = {
  // I link si aprono in una nuova scheda, senza dare accesso alla pagina di origine.
  // Se react-markdown ha scartato l'indirizzo (schema non ammesso, es. javascript:)
  // resta solo il testo, senza un link che non porta da nessuna parte.
  a: ({ href, children }) =>
    href ? (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  // Le tabelle larghe (analisi dei dati) scorrono in orizzontale dentro il fumetto
  // invece di allargare la pagina.
  table: ({ children }) => (
    <div className="overflow-x-auto">
      <table>{children}</table>
    </div>
  ),
};

/** @param {{ text: string }} props */
export default function MessageContent({ text }) {
  return (
    <div
      className="prose prose-invert prose-sm max-w-none
        prose-p:my-2 prose-p:text-white prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5 prose-li:text-white
        prose-strong:text-white prose-a:text-edge prose-code:text-edge
        prose-code:before:content-none prose-code:after:content-none
        *:first:mt-0 *:last:mb-0"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        disallowedElements={["img"]}
        components={components}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
