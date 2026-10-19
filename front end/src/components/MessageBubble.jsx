import { memo } from "react";
import Avatar from "./Avatar";
import ChartImage from "./ChartImage";
import MessageContent from "./MessageContent";
import ToolBadges from "./ToolBadges";

/**
 * Fumetto di un messaggio: utente, assistente o avviso di sistema ('notice').
 * Le schede di errore ('error') hanno un componente a parte (ErrorCard).
 *
 * Il contenuto dell'assistente è, nell'ordine: risposta in Markdown, grafico (se c'è),
 * etichette delle fonti.
 *
 * memo: i messaggi già mostrati non si ridisegnano quando ne arriva uno nuovo. Funziona
 * perché l'oggetto `message` non cambia mai dopo la creazione e `onChartLoad` è stabile.
 *
 * @param {{ message: object, onChartLoad?: () => void }} props
 */
function MessageBubble({ message, onChartLoad }) {
  const { role, text, time, chartSrc, toolsUsed, sources } = message;

  // Avviso di sistema (es. sessione scaduta): pillola discreta al centro.
  if (role === "notice") {
    return (
      <div className="flex animate-fade-up justify-center">
        <p className="rounded-full border border-amber-300/40 bg-amber-300/10 px-3 py-1 text-center text-xs text-amber-200">
          {text}
        </p>
      </div>
    );
  }

  const isUser = role === "user";

  return (
    // data-message-id: la chat ritrova da qui il fumetto dell'ultima risposta per
    // misurarne l'altezza e portarne l'inizio in alto se è molto lunga.
    <div
      data-message-id={message.id}
      className={`flex items-end gap-2 ${
        isUser
          ? "origin-bottom-right animate-send justify-end"
          : "animate-fade-up justify-start"
      }`}
    >
      {!isUser && <Avatar />}
      <div
        className={`relative min-w-0 max-w-[82%] wrap-break-word rounded-2xl px-3.5 pb-1.5 pt-2.5 text-[15px] leading-snug shadow-md ${
          isUser
            ? "rounded-br-md bg-edge text-pitch-950 before:absolute before:-right-1.5 before:bottom-0 before:size-3 before:bg-edge before:[clip-path:polygon(0_0,100%_100%,0_100%)]"
            : "rounded-bl-md border border-white/10 bg-pitch-950/90 text-white"
        }`}
      >
        {isUser ? text : <MessageContent text={text} />}
        {chartSrc && <ChartImage src={chartSrc} onLoad={onChartLoad} />}
        {!isUser && (
          <ToolBadges toolsUsed={toolsUsed ?? []} sources={sources ?? []} />
        )}
        <span
          className={`mt-0.5 block text-right text-[10px] ${isUser ? "text-pitch-950/60" : "text-white/60"}`}
        >
          {time}
        </span>
      </div>
    </div>
  );
}

export default memo(MessageBubble);
