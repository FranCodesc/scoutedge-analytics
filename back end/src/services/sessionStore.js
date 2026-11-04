import { randomUUID } from "node:crypto";

/**
 * Costanti dello store in un solo punto (contratto API: 20 messaggi,
 * scadenza dopo 30 minuti di inattività).
 */
export const MAX_MESSAGES = 20;
export const SESSION_TTL_MS = 30 * 60 * 1000;
const CLEANUP_INTERVAL_MS = 5 * 60 * 1000;

/**
 * @typedef {{ role: "user" | "assistant", content: string }} Message
 * @typedef {{ history: Message[], lastActivity: number, busy: boolean }} Session
 */

/**
 * Crea uno store di sessioni indipendente, in memoria per scelta (contratto
 * API): un riavvio del back end azzera tutto e il client riceve newSession: true.
 *
 * `now` si può iniettare per provare la scadenza senza aspettare 30 minuti;
 * i valori predefiniti sono quelli del contratto.
 */
export function createSessionStore({
  now = Date.now,
  ttlMs = SESSION_TTL_MS,
  maxMessages = MAX_MESSAGES,
} = {}) {
  /** @type {Map<string, Session>} */
  const sessions = new Map();

  /** @param {Session} session */
  function isExpired(session) {
    return now() - session.lastActivity > ttlMs;
  }

  /**
   * Restituisce la sessione indicata oppure ne crea una nuova (id mancante,
   * sconosciuto o scaduto: per il contratto non è un errore). Il formato UUID
   * si valida nella route. La history restituita è una copia. Chiamare
   * acquire() subito dopo, senza un await in mezzo.
   *
   * @param {string} [sessionId]
   * @returns {{ sessionId: string, history: Message[], isNew: boolean }}
   */
  function getOrCreateSession(sessionId) {
    const existing = sessionId ? sessions.get(sessionId) : undefined;

    if (existing && !isExpired(existing)) {
      existing.lastActivity = now();
      return { sessionId, history: [...existing.history], isNew: false };
    }

    // Sessione scaduta: va eliminata prima di crearne una nuova con un altro id.
    if (existing) sessions.delete(sessionId);

    const newId = randomUUID();
    sessions.set(newId, { history: [], lastActivity: now(), busy: false });
    return { sessionId: newId, history: [], isNew: true };
  }

  /**
   * Blocca la sessione per la durata di una richiesta (SESSION_BUSY).
   * Va sempre accompagnato da release() in un blocco finally.
   *
   * @returns {boolean} true se il lucchetto è stato preso, false se era già occupata
   * @throws {Error} se la sessione non esiste (errore di programmazione)
   */
  function acquire(sessionId) {
    const session = sessions.get(sessionId);
    if (!session) {
      throw new Error("acquire() su una sessione inesistente.");
    }
    if (session.busy) return false;
    session.busy = true;
    return true;
  }

  /** Libera la sessione. Su una sessione inesistente non fa nulla. */
  function release(sessionId) {
    const session = sessions.get(sessionId);
    if (session) session.busy = false;
  }

  /**
   * Aggiunge alla history la coppia domanda/risposta di un turno riuscito.
   * Il taglio toglie coppie intere dall'inizio, così la history non inizia
   * mai con un messaggio dell'assistente.
   *
   * @returns {boolean} false se la sessione non esiste più
   */
  function appendTurn(sessionId, userMessage, assistantReply) {
    const session = sessions.get(sessionId);
    if (!session) return false;

    session.history.push(
      { role: "user", content: userMessage },
      { role: "assistant", content: assistantReply },
    );
    while (session.history.length > maxMessages) {
      session.history.splice(0, 2);
    }
    session.lastActivity = now();
    return true;
  }

  /**
   * Elimina le sessioni scadute, saltando quelle occupate.
   * @returns {number} quante sessioni ha eliminato
   */
  function cleanupExpiredSessions() {
    let removed = 0;
    for (const [id, session] of sessions) {
      if (!session.busy && isExpired(session)) {
        sessions.delete(id);
        removed += 1;
      }
    }
    return removed;
  }

  return { getOrCreateSession, acquire, release, appendTurn, cleanupExpiredSessions };
}

// Istanza usata dal back end vero. Le esportazioni per nome restano quelle di prima.
export const defaultSessionStore = createSessionStore();
export const {
  getOrCreateSession,
  acquire,
  release,
  appendTurn,
  cleanupExpiredSessions,
} = defaultSessionStore;

// unref(): il timer non deve tenere vivo il processo, altrimenti Node non
// uscirebbe mai (ad esempio negli script di prova e nei test).
setInterval(defaultSessionStore.cleanupExpiredSessions, CLEANUP_INTERVAL_MS).unref();
