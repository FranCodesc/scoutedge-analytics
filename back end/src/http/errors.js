/**
 * Formato unico degli errori HTTP (CONTRATTO_API.md, sezione "Errori"):
 *   { "error": { "code": "INVALID_REQUEST", "message": "..." } }
 *
 * Il message è in italiano e mostrabile all'utente. Qui non finiscono mai
 * stack trace né testo grezzo di OpenAI/FastAPI/Chroma: il dettaglio va solo
 * in console.error.
 */

/**
 * Errore "previsto" che una route vuole trasformare in una risposta precisa.
 * Le route lo lanciano (throw new HttpError(...)) e il middleware di errore lo
 * converte in JSON: così la gestione degli errori sta in un solo punto.
 */
export class HttpError extends Error {
  /**
   * @param {number} status codice HTTP (es. 400)
   * @param {string} code codice del contratto (es. "INVALID_REQUEST")
   * @param {string} message messaggio in italiano per l'utente
   */
  constructor(status, code, message) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.code = code;
  }
}

/**
 * Invia una risposta di errore nel formato del contratto.
 * Serve anche alle route che rispondono senza lanciare (es. il 504 del timeout).
 */
export function sendError(res, status, code, message) {
  return res.status(status).json({ error: { code, message } });
}

/** 404 per le rotte inesistenti. Va montato DOPO tutte le route. */
export function notFoundHandler(req, res) {
  sendError(res, 404, "NOT_FOUND", "Risorsa non trovata.");
}

/**
 * Middleware di errore. Express lo riconosce dai 4 parametri: `next` va
 * dichiarato anche se non lo usiamo, altrimenti viene trattato come un
 * middleware normale. Va montato per ultimo.
 *
 * Gli errori di express.json() hanno un campo `type`:
 * - entity.parse.failed → JSON malformato → 400
 * - entity.too.large → body oltre il limite → 413
 * Gli altri errori 4xx del parser (es. charset non supportato) diventano
 * 400 generico; tutto il resto è un 500 con messaggio generico.
 */
export function errorHandler(err, req, res, next) {
  // Se la risposta è già partita non si può più cambiare: si passa la mano a
  // Express, che chiude la connessione.
  if (res.headersSent) return next(err);

  if (err instanceof HttpError) {
    return sendError(res, err.status, err.code, err.message);
  }

  if (err?.type === "entity.parse.failed") {
    return sendError(res, 400, "INVALID_REQUEST", "Il corpo della richiesta non è un JSON valido.");
  }

  if (err?.type === "entity.too.large") {
    return sendError(res, 413, "PAYLOAD_TOO_LARGE", "La richiesta è troppo grande.");
  }

  if (Number.isInteger(err?.status) && err.status >= 400 && err.status < 500) {
    return sendError(res, 400, "INVALID_REQUEST", "La richiesta non è valida.");
  }

  // Errore imprevisto: il dettaglio resta nei log, all'utente un messaggio generico.
  console.error("[errore non gestito]", err);
  return sendError(res, 500, "INTERNAL_ERROR", "Si è verificato un errore imprevisto. Riprova tra poco.");
}
