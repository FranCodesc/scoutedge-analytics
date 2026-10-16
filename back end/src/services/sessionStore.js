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
 * Store in memoria: sessionId → sessione. In memoria per scelta (contratto
 * API): un riavvio del back end azzera tutto e il client riceve
 * semplicemente newSession: true.
 * @type {Map<string, Session>}
 */
const sessions = new Map();

/** @param {Session} session */
function isExpired(session) {
  return Date.now() - session.lastActivity > SESSION_TTL_MS;
}

/**
 * Restituisce la sessione indicata oppure ne crea una nuova.
 *
 * Una sessione nuova si crea se l'id manca, è sconosciuto o è scaduto
 * (isNew: true): per il contratto non è un errore. Il formato UUID NON si
 * valida qui, spetta alla route.
 *
 * La scadenza si controlla anche qui, e non solo nella pulizia periodica,
 * perché tra due passaggi del timer una sessione può essere già scaduta.
 *
 * La history restituita è una copia: chi la riceve non può modificare lo
 * store per sbaglio. Chiamare acquire() subito dopo, senza un await in
 * mezzo: il codice sincrono non può essere interrotto da un'altra richiesta.
 *
 * @param {string} [sessionId]
 * @returns {{ sessionId: string, history: Message[], isNew: boolean }}
 */
export function getOrCreateSession(sessionId) {
  const existing = sessionId ? sessions.get(sessionId) : undefined;

  if (existing && !isExpired(existing)) {
    existing.lastActivity = Date.now();
    return { sessionId, history: [...existing.history], isNew: false };
  }

  // Sessione scaduta: va eliminata prima di crearne una nuova con un altro id.
  if (existing) sessions.delete(sessionId);

  const newId = randomUUID();
  sessions.set(newId, { history: [], lastActivity: Date.now(), busy: false });
  return { sessionId: newId, history: [], isNew: true };
}

/**
 * Blocca la sessione per la durata di una richiesta (SESSION_BUSY).
 * Va sempre accompagnato da release() in un blocco finally.
 *
 * @param {string} sessionId id restituito da getOrCreateSession
 * @returns {boolean} true se il lucchetto è stato preso, false se la
 *   sessione era già occupata da un'altra richiesta
 * @throws {Error} se la sessione non esiste: è un errore di programmazione
 *   (la route chiama sempre prima getOrCreateSession), da non confondere
 *   con SESSION_BUSY
 */
export function acquire(sessionId) {
  const session = sessions.get(sessionId);
  if (!session) {
    throw new Error("acquire() su una sessione inesistente.");
  }
  if (session.busy) return false;
  session.busy = true;
  return true;
}

/**
 * Libera la sessione. Da chiamare sempre in un blocco finally, anche se la
 * richiesta è fallita: altrimenti la sessione resterebbe occupata per sempre.
 * Su una sessione inesistente non fa nulla.
 *
 * @param {string} sessionId
 */
export function release(sessionId) {
  const session = sessions.get(sessionId);
  if (session) session.busy = false;
}

/**
 * Aggiunge alla history la coppia domanda/risposta di un turno riuscito.
 * Da chiamare SOLO in caso di successo (contratto API): un turno fallito
 * non deve lasciare tracce nella memoria della conversazione.
 *
 * Il taglio toglie coppie intere dall'inizio finché la history rientra nel
 * limite: così non inizia mai con un messaggio dell'assistente (una history
 * che comincia con una risposta senza domanda confonde l'LLM).
 *
 * @param {string} sessionId
 * @param {string} userMessage
 * @param {string} assistantReply
 * @returns {boolean} false se la sessione non esiste più (la risposta va
 *   comunque consegnata; al turno dopo il client riceverà newSession: true)
 */
export function appendTurn(sessionId, userMessage, assistantReply) {
  const session = sessions.get(sessionId);
  if (!session) return false;

  session.history.push(
    { role: "user", content: userMessage },
    { role: "assistant", content: assistantReply },
  );
  while (session.history.length > MAX_MESSAGES) {
    session.history.splice(0, 2);
  }
  session.lastActivity = Date.now();
  return true;
}

/**
 * Elimina le sessioni scadute. Salta quelle occupate: una richiesta in
 * corso non deve perdere la sessione sotto i piedi. Esportata anche per
 * poterla provare senza aspettare il timer.
 *
 * @returns {number} quante sessioni ha eliminato
 */
export function cleanupExpiredSessions() {
  let removed = 0;
  for (const [id, session] of sessions) {
    if (!session.busy && isExpired(session)) {
      sessions.delete(id);
      removed += 1;
    }
  }
  return removed;
}

// unref(): il timer non deve tenere vivo il processo, altrimenti Node non
// uscirebbe mai (ad esempio negli script di prova).
setInterval(cleanupExpiredSessions, CLEANUP_INTERVAL_MS).unref();
