import { useCallback, useMemo, useRef, useState } from "react";
import { ApiError, chartSrc, sendMessage } from "../api/chatApi";

/*
 * Modello del messaggio nella lista:
 *   { id, role, text, time, ...campi extra }
 * role:
 *   'user'      messaggio dell'utente
 *   'assistant' risposta (extra: chartSrc, toolsUsed, sources) oppure il benvenuto locale
 *   'error'     scheda di errore (extra: prompt per "Riprova", offline)
 *   'notice'    avviso di sistema (sessione scaduta)
 * La lista serve solo alla visualizzazione; la memoria dell'agente sta nella history del server.
 */

// Benvenuto solo locale: non viene mai inviato al server.
const WELCOME_TEXT =
  "Ciao, sono l'assistente di ScoutEdge ⚽ Posso rispondere alle domande sul manuale interno della piattaforma (piani, metodologia, SLA, procedure) e analizzare il dataset di scouting, anche con grafici. Da dove iniziamo?";

const SESSION_EXPIRED_TEXT =
  "La conversazione precedente è scaduta: ne è iniziata una nuova.";
const UNEXPECTED_ERROR_TEXT =
  "Si è verificato un errore imprevisto. Riprova tra un attimo.";

// Errori in cui è la richiesta a essere sbagliata: rinviarla darebbe lo stesso rifiuto,
// quindi la scheda di errore non offre "Riprova".
const NOT_RETRYABLE_CODES = new Set([
  "INVALID_REQUEST",
  "PAYLOAD_TOO_LARGE",
  "NOT_FOUND",
]);

const now = () =>
  new Date().toLocaleTimeString("it-IT", {
    hour: "2-digit",
    minute: "2-digit",
  });

// Gli id nascono fuori dagli aggiornamenti di stato: in StrictMode React può eseguire
// due volte la funzione passata a setMessages, e un id generato lì dentro cambierebbe.
let nextId = 1;
function makeMessage(role, text, extra = {}) {
  return { id: nextId++, role, text, time: now(), ...extra };
}

const createWelcome = () => makeMessage("assistant", WELCOME_TEXT);

/** Risposta 200 del contratto → messaggio dell'assistente. chartSrc() valida chartUrl. */
function fromResponse(data) {
  return makeMessage("assistant", data.reply, {
    chartSrc: chartSrc(data.chartUrl),
    toolsUsed: data.toolsUsed ?? [],
    sources: data.sources ?? [],
  });
}

/**
 * Errore → scheda di errore. sendMessage lancia solo ApiError, ma un bug nostro dentro
 * il try (es. un campo inatteso nella risposta) finirebbe qui: in quel caso messaggio
 * generico, mai il testo tecnico dell'eccezione.
 * La variante "offline" vale se il browser è offline o il server non risponde.
 */
function fromError(err, prompt) {
  const apiError = err instanceof ApiError ? err : null;
  return makeMessage(
    "error",
    apiError ? apiError.message : UNEXPECTED_ERROR_TEXT,
    {
      prompt,
      offline: !navigator.onLine || apiError?.code === "NETWORK_ERROR",
      retryable: !(apiError && NOT_RETRYABLE_CODES.has(apiError.code)),
    },
  );
}

/**
 * Stato e azioni della conversazione. È l'unico punto dell'interfaccia che usa chatApi.
 *
 * @returns {{
 *   messages: object[],
 *   busy: boolean,
 *   lastChartSrc: string | null,
 *   send: (text: string) => boolean,
 *   retry: (errorMessage: object) => void,
 *   newChat: () => void,
 * }}
 */
export function useChat() {
  const [messages, setMessages] = useState(() => [createWelcome()]);
  const [busy, setBusy] = useState(false);

  // sessionId: solo in memoria, mai in localStorage (ricaricare = nuova conversazione).
  // È un ref e non uno stato perché non serve a disegnare nulla e dentro le funzioni
  // asincrone va letto sempre aggiornato, non com'era al momento del render.
  const sessionIdRef = useRef(null);

  // Contatore di conversazione. "Nuova chat" lo incrementa: una richiesta ancora in
  // volo si accorge, al ritorno, che il contatore non è più il suo e non tocca nulla.
  const conversationRef = useRef(0);

  // Guardia sincrona contro il doppio invio. Lo stato `busy` cambia solo al render
  // successivo: due invii nello stesso istante leggerebbero entrambi `false`.
  const busyRef = useRef(false);

  /** Invia `prompt` al server e aggiunge alla lista la risposta o la scheda di errore. */
  const run = useCallback(async (prompt) => {
    const conversation = conversationRef.current;
    const sentSessionId = sessionIdRef.current;
    busyRef.current = true;
    setBusy(true);
    try {
      const data = await sendMessage({
        message: prompt,
        sessionId: sentSessionId,
      });
      // Da qui in poi ogni aggiornamento vale solo se la conversazione è ancora quella.
      if (conversation !== conversationRef.current) return;

      // Contratto: il sessionId si sovrascrive SEMPRE con quello ricevuto.
      sessionIdRef.current = data.sessionId;

      const added = [fromResponse(data)];
      // Sessione nuova a conversazione già avviata = quella vecchia è scaduta lato server.
      if (data.newSession && sentSessionId !== null) {
        added.unshift(makeMessage("notice", SESSION_EXPIRED_TEXT));
      }
      setMessages((m) => [...m, ...added]);
    } catch (err) {
      if (conversation !== conversationRef.current) return;
      setMessages((m) => [...m, fromError(err, prompt)]);
    } finally {
      // Anche lo sblocco dell'input è protetto: il `finally` di una richiesta VECCHIA
      // non deve sbloccare l'input mentre quella NUOVA è ancora in corso.
      if (conversation === conversationRef.current) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }, []);

  /** Invia un messaggio. Restituisce true se è partito (così l'input può svuotarsi). */
  const send = useCallback(
    (text) => {
      const value = text.trim();
      if (!value || busyRef.current) return false;
      const userMessage = makeMessage("user", value);
      setMessages((m) => [...m, userMessage]);
      run(value);
      return true;
    },
    [run],
  );

  /** Reinvia la domanda di una scheda di errore, senza duplicare il messaggio dell'utente. */
  const retry = useCallback(
    (errorMessage) => {
      if (busyRef.current) return;
      setMessages((m) => m.filter((x) => x.id !== errorMessage.id));
      run(errorMessage.prompt);
    },
    [run],
  );

  /** "Nuova chat": svuota tutto, scarta la richiesta in corso e sblocca subito l'input. */
  const newChat = useCallback(() => {
    conversationRef.current += 1;
    sessionIdRef.current = null;
    busyRef.current = false;
    setBusy(false);
    setMessages([createWelcome()]);
  }, []);

  // Ultimo grafico reale della conversazione: non è uno stato a parte, si ricava dai
  // messaggi. Così "Nuova chat" lo azzera da sola e non c'è nulla da tenere sincronizzato.
  const lastChartSrc = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].chartSrc) return messages[i].chartSrc;
    }
    return null;
  }, [messages]);

  return { messages, busy, lastChartSrc, send, retry, newChat };
}
