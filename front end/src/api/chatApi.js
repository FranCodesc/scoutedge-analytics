/**
 * Client per il back end di ScoutEdge (contratto API v1.0).
 * È l'unico modulo del front end che parla con il server.
 */

// Letto una sola volta all'avvio. Se manca la variabile si avvisa in console
// e si usa il default di sviluppo, così l'app non si rompe in silenzio.
const DEFAULT_API_URL = 'http://localhost:3001'
const API_URL = import.meta.env.VITE_API_URL || DEFAULT_API_URL
if (!import.meta.env.VITE_API_URL) {
  console.warn(`VITE_API_URL non è definita: uso ${DEFAULT_API_URL}`)
}

/**
 * Errore normalizzato: il resto dell'app gestisce un solo tipo di errore.
 * `code` è un codice del contratto (INVALID_REQUEST, SESSION_BUSY, TIMEOUT…)
 * oppure uno dei due codici interni al front end (NETWORK_ERROR, CLIENT_TIMEOUT).
 * `message` è sempre in italiano e mostrabile direttamente all'utente.
 * `status` è l'HTTP status, o null se non c'è stata una risposta del server.
 */
export class ApiError extends Error {
  constructor({ status = null, code, message }) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

// Il back end interrompe la pipeline a 120 s (504 TIMEOUT). Il contratto chiede che il
// front end non abbandoni prima di 130 s, così l'utente riceve l'errore vero del server
// e non un timeout inventato dal client.
const CLIENT_TIMEOUT_MS = 130_000

// Messaggi dei due codici interni e del caso "risposta non interpretabile".
const MESSAGES = {
  NETWORK_ERROR:
    'Impossibile contattare il server. Controlla che il back end sia avviato e riprova.',
  CLIENT_TIMEOUT:
    'La risposta sta richiedendo troppo tempo. Riprova tra qualche istante.',
  INTERNAL_ERROR: 'Si è verificato un errore imprevisto. Riprova tra un attimo.',
}

/**
 * Legge il corpo come JSON. Restituisce null se il corpo non è JSON valido
 * (es. una pagina HTML di errore di un proxy). Altri errori, come l'abort per
 * timeout o la rete caduta a metà lettura, vengono propagati: li gestisce sendMessage.
 */
async function readJson(response) {
  try {
    return await response.json()
  } catch (err) {
    if (err instanceof SyntaxError) return null
    throw err
  }
}

/**
 * Trasforma una risposta non 2xx in ApiError. Se il corpo ha il formato del contratto
 * ({ error: { code, message } }) si usano i valori del back end; altrimenti non ci si
 * fida di ciò che è arrivato e si mostra un messaggio generico.
 */
function errorFromResponse(status, data) {
  const code = data?.error?.code
  const message = data?.error?.message
  if (typeof code === 'string' && typeof message === 'string') {
    return new ApiError({ status, code, message })
  }
  return new ApiError({ status, code: 'INTERNAL_ERROR', message: MESSAGES.INTERNAL_ERROR })
}

/**
 * Invia un messaggio all'agente (POST /api/chat).
 *
 * @param {{ message: string, sessionId?: string | null }} params
 *   `sessionId` va omesso alla prima richiesta o dopo "Nuova chat": il server ne crea uno.
 * @returns {Promise<{ sessionId: string, newSession: boolean, reply: string,
 *   chartUrl: string | null, toolsUsed: string[], sources: { section: string }[] }>}
 *   L'oggetto del contratto, così com'è.
 * @throws {ApiError} per qualsiasi errore: del server (codici del contratto),
 *   di rete (NETWORK_ERROR) o di timeout del client (CLIENT_TIMEOUT).
 */
export async function sendMessage({ message, sessionId }) {
  // sessionId nel body solo se c'è: un valore null o vuoto verrebbe respinto dal server.
  const body = sessionId ? { message, sessionId } : { message }

  // Il timer interrompe la fetch dopo CLIENT_TIMEOUT_MS. La variabile timedOut ci serve
  // per distinguere un abort per timeout da una rete caduta: entrambi arrivano come errore.
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, CLIENT_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    const data = await readJson(response)

    if (!response.ok) throw errorFromResponse(response.status, data)
    // 200 ma corpo illeggibile: non è un caso previsto dal contratto, lo trattiamo come errore.
    if (data === null) {
      throw new ApiError({
        status: response.status,
        code: 'INTERNAL_ERROR',
        message: MESSAGES.INTERNAL_ERROR,
      })
    }
    return data
  } catch (err) {
    // Gli ApiError sono già normalizzati: si rilanciano così come sono.
    if (err instanceof ApiError) throw err
    // Tutto il resto (fetch fallita, abort) non ha una risposta del server.
    throw new ApiError({
      code: timedOut ? 'CLIENT_TIMEOUT' : 'NETWORK_ERROR',
      message: timedOut ? MESSAGES.CLIENT_TIMEOUT : MESSAGES.NETWORK_ERROR,
    })
  } finally {
    // Il timer va sempre fermato, altrimenti scatterebbe anche a risposta già arrivata.
    clearTimeout(timer)
  }
}

// Formato dei nomi dei grafici deciso dal contratto: chart_ + 8 cifre esadecimali.
const CHART_URL_PATTERN = /^\/charts\/chart_[0-9a-f]{8}\.png$/

/**
 * Costruisce l'URL dell'immagine di un grafico a partire dal `chartUrl` della risposta.
 * Il valore finisce in un attributo `src`, quindi non ci si fida ciecamente del server:
 * se non ha esattamente la forma attesa (path relativo del back end, nome del file nel
 * formato del contratto) si restituisce null e l'immagine non viene mostrata.
 *
 * @param {string | null | undefined} chartUrl
 * @returns {string | null}
 */
export function chartSrc(chartUrl) {
  if (typeof chartUrl !== 'string' || !CHART_URL_PATTERN.test(chartUrl)) return null
  return `${API_URL}${chartUrl}`
}