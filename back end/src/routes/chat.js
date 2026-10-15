/**
 * POST /api/chat (docs/CONTRATTO_API.md v1.0, docs/DESIGN_ORCHESTRATORE.md v1.5 §2-§3).
 *
 * Flusso: validazione → sessione + lucchetto → orchestratore con timeout →
 * risposta. Gli errori previsti sono HttpError, che il middleware di errore
 * trasforma nel formato del contratto.
 */
import { Router } from "express";
import { runOrchestrator } from "../agent/orchestrator.js";
import {
  acquire,
  appendTurn,
  getOrCreateSession,
  release,
} from "../services/sessionStore.js";
import { HttpError } from "../http/errors.js";

/** Timeout complessivo della pipeline (contratto API: 120 s → 504 TIMEOUT). */
export const CHAT_TIMEOUT_MS = 120_000;

const MAX_MESSAGE_LENGTH = 2000;

/** UUID v4: la "4" di versione e la variante [89ab]; maiuscole ammesse. */
const UUID_V4_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const router = Router();

/**
 * Valida il body PRIMA di qualsiasi chiamata allo store o all'LLM.
 * Con Content-Type diverso da JSON Express 5 lascia req.body undefined: rientra
 * nel primo controllo.
 *
 * @returns {{ message: string, sessionId: string|undefined }} message già trim()-ato
 * @throws {HttpError} 400 INVALID_REQUEST
 */
function validateChatBody(body) {
  const invalid = (text) => new HttpError(400, "INVALID_REQUEST", text);

  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    throw invalid("Il corpo della richiesta deve essere un oggetto JSON.");
  }
  if (typeof body.message !== "string") {
    throw invalid("Il messaggio è obbligatorio e deve essere un testo.");
  }

  const message = body.message.trim();
  if (message.length === 0) {
    throw invalid("Il messaggio non può essere vuoto.");
  }
  if (message.length > MAX_MESSAGE_LENGTH) {
    throw invalid(`Il messaggio non può superare i ${MAX_MESSAGE_LENGTH} caratteri.`);
  }

  // Facoltativo: assente = undefined. null o altri tipi sono errori.
  const { sessionId } = body;
  if (
    sessionId !== undefined &&
    (typeof sessionId !== "string" || !UUID_V4_PATTERN.test(sessionId))
  ) {
    throw invalid("L'identificativo di sessione non è valido.");
  }

  return { message, sessionId };
}

/** Una riga di log per richiesta: niente testo del messaggio. */
function logRequest(sessionId, toolsUsed, startedAt, outcome) {
  const tools = toolsUsed ? `[${toolsUsed.join(",")}]` : "-";
  console.log(
    `[chat] sessione=${sessionId.slice(0, 8)} tool=${tools} durata=${Date.now() - startedAt}ms esito=${outcome}`,
  );
}

const timeoutError = () =>
  new HttpError(504, "TIMEOUT", "L'elaborazione ha impiegato troppo tempo. Riprova con una domanda più semplice.");

router.post("/api/chat", async (req, res) => {
  const startedAt = Date.now();
  const { message, sessionId: requestedId } = validateChatBody(req.body);

  // Nessun await tra queste due righe: il codice sincrono non può essere
  // interrotto da un'altra richiesta, quindi il controllo del lucchetto è atomico.
  const { sessionId, history, isNew } = getOrCreateSession(requestedId);
  if (!acquire(sessionId)) {
    logRequest(sessionId, null, startedAt, "sessione_occupata");
    throw new HttpError(
      409,
      "SESSION_BUSY",
      "È già in corso una richiesta per questa conversazione. Attendi la risposta e riprova.",
    );
  }

  const controller = new AbortController();

  // Il "lavoro" parte subito dopo acquire: il suo finally è l'UNICO punto che
  // rilascia il lucchetto, e lo fa quando l'elaborazione è davvero finita, non
  // quando parte il 504. Così, dopo un timeout, una nuova domanda sulla stessa
  // sessione resta respinta (409) finché la vecchia non ha terminato.
  const work = (async () => {
    let timer;
    try {
      timer = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
      const result = await runOrchestrator({ message, history, signal: controller.signal });
      // Un turno scaduto non deve finire nella history: il client ha ricevuto 504.
      if (!controller.signal.aborted) {
        appendTurn(sessionId, message, result.reply);
      }
      return result;
    } finally {
      clearTimeout(timer);
      release(sessionId);
    }
  })();

  // Se il timeout vince la gara, il lavoro può fallire più tardi: senza questo
  // .catch sarebbe un unhandled rejection. Si logga soltanto.
  work.catch((error) => {
    if (controller.signal.aborted) {
      console.error("[chat] elaborazione terminata dopo il timeout:", error?.name ?? error);
    }
  });

  // Promise che si rifiuta all'abort. Il .catch vuoto evita l'unhandled rejection
  // nel caso in cui sia il lavoro a vincere e la promise resti inutilizzata.
  const timeout = new Promise((_, reject) => {
    controller.signal.addEventListener("abort", () => reject(timeoutError()), { once: true });
  });
  timeout.catch(() => {});

  let result;
  try {
    result = await Promise.race([work, timeout]);
  } catch (error) {
    if (error instanceof HttpError || controller.signal.aborted) {
      logRequest(sessionId, null, startedAt, "timeout");
      throw timeoutError();
    }
    // Per il design (§3) qui arrivano solo gli errori del modello: gli errori
    // dei tool sono già testo. Il dettaglio resta nel log.
    console.error("[chat] errore del modello:", error);
    logRequest(sessionId, null, startedAt, "errore_llm");
    throw new HttpError(
      502,
      "LLM_ERROR",
      "Il servizio di intelligenza artificiale non è al momento disponibile. Riprova tra poco.",
    );
  }

  logRequest(sessionId, result.toolsUsed, startedAt, "ok");
  res.json({
    sessionId,
    newSession: isNew,
    reply: result.reply,
    chartUrl: result.chartUrl,
    toolsUsed: result.toolsUsed,
    // runOrchestrator restituisce stringhe; il contratto pubblico vuole [{ section }].
    sources: result.sources.map((section) => ({ section })),
  });
});

export default router;
