/**
 * Limite di frequenza su POST /api/chat (docs/CONTRATTO_API.md, sezione
 * "Limite di frequenza").
 *
 * Due limiti sulla stessa finestra di tempo:
 * - per client (indirizzo IP);
 * - globale (somma di tutte le richieste), per proteggere la spesa anche se
 *   l'IP non è affidabile.
 *
 * La configurazione arriva da variabili d'ambiente lette una sola volta
 * all'avvio. Senza le variabili il limite è DISATTIVATO (uso in locale e
 * test). Se sono presenti solo in parte o con valori non validi, il back end
 * non deve partire: online, un limite spento per errore non deve passare
 * inosservato.
 */
import rateLimit from "express-rate-limit";
import { sendError } from "./errors.js";

/** Le tre variabili del limite: o ci sono tutte, o non c'è nessuna. */
const RATE_LIMIT_VARS = ["RATE_LIMIT_WINDOW_MIN", "RATE_LIMIT_PER_IP", "RATE_LIMIT_GLOBAL"];

/**
 * Finestra massima: 24 ore. I timer di Node superano il loro massimo oltre
 * 2^31-1 ms (circa 24,8 giorni) e scatterebbero subito: meglio rifiutare il
 * valore all'avvio.
 */
const MAX_WINDOW_MIN = 1440;

const RATE_LIMITED_MESSAGE = "Troppe richieste in poco tempo. Riprova tra qualche minuto.";

/** Una variabile vuota (es. "RATE_LIMIT_PER_IP=") vale come assente. */
function isSet(value) {
  return value !== undefined && value.trim() !== "";
}

/**
 * Legge un intero positivo da una stringa. Si controlla la stringa con una
 * regex invece di usare parseInt/Number da soli: parseInt("3abc") darebbe 3 e
 * Number("1e3") darebbe 1000, e un valore sbagliato passerebbe senza errori.
 */
function parsePositiveInt(name, raw) {
  const text = raw.trim();
  if (!/^[1-9]\d*$/.test(text) || !Number.isSafeInteger(Number(text))) {
    throw new Error(`${name} deve essere un intero positivo (valore ricevuto: "${text}").`);
  }
  return Number(text);
}

/**
 * Legge e valida le variabili del limite.
 *
 * @param {Record<string, string | undefined>} env normalmente process.env
 * @returns {{ windowMin: number, perIp: number, global: number } | null}
 *   null se il limite è disattivato (nessuna delle tre variabili impostata)
 * @throws {Error} se le variabili sono presenti solo in parte o non valide
 */
export function loadRateLimitConfig(env) {
  const present = RATE_LIMIT_VARS.filter((name) => isSet(env[name]));
  if (present.length === 0) return null;

  const missing = RATE_LIMIT_VARS.filter((name) => !present.includes(name));
  if (missing.length > 0) {
    throw new Error(
      `Limite di frequenza configurato solo in parte: manca ${missing.join(", ")}. ` +
        "Imposta tutte e tre le variabili oppure nessuna.",
    );
  }

  const windowMin = parsePositiveInt("RATE_LIMIT_WINDOW_MIN", env.RATE_LIMIT_WINDOW_MIN);
  if (windowMin > MAX_WINDOW_MIN) {
    throw new Error(`RATE_LIMIT_WINDOW_MIN non può superare ${MAX_WINDOW_MIN} minuti (ricevuto: ${windowMin}).`);
  }

  return {
    windowMin,
    perIp: parsePositiveInt("RATE_LIMIT_PER_IP", env.RATE_LIMIT_PER_IP),
    global: parsePositiveInt("RATE_LIMIT_GLOBAL", env.RATE_LIMIT_GLOBAL),
  };
}

/**
 * Numero di proxy tra internet e il back end (nginx, ecc.), da usare con
 * app.set("trust proxy", n). Se la variabile manca, Express non si fida di
 * X-Forwarded-For e l'IP del client è quello della connessione.
 *
 * @param {Record<string, string | undefined>} env normalmente process.env
 * @returns {number | undefined} undefined se TRUST_PROXY non è impostata
 * @throws {Error} se il valore non è un intero >= 0
 */
export function readTrustProxy(env) {
  if (!isSet(env.TRUST_PROXY)) return undefined;
  const text = env.TRUST_PROXY.trim();
  if (!/^\d+$/.test(text) || !Number.isSafeInteger(Number(text))) {
    throw new Error(`TRUST_PROXY deve essere un intero maggiore o uguale a 0 (valore ricevuto: "${text}").`);
  }
  return Number(text);
}

/**
 * Maschera l'IP per i log: il valore completo è un dato personale e non serve
 * a capire cosa è successo. IPv4: primi due numeri; IPv6: primi due gruppi.
 */
function maskIp(ip) {
  if (typeof ip !== "string" || ip === "") return "sconosciuto";
  // Node può dare gli IPv4 in forma "::ffff:1.2.3.4".
  const v4 = ip.replace(/^::ffff:/i, "");
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(v4)) {
    const [a, b] = v4.split(".");
    return `${a}.${b}.x.x`;
  }
  return `${ip.split(":").slice(0, 2).join(":")}:…`;
}

/**
 * Crea il gestore della risposta 429 per un tipo di limite. Nel log finiscono
 * solo il tipo di limite e l'IP mascherato: mai il testo del messaggio.
 * Retry-After lo imposta già la libreria (standardHeaders attivo) prima di
 * chiamare questo gestore.
 */
function createLimitHandler(kind) {
  return (req, res) => {
    console.warn(`[limite di frequenza] richiesta respinta (${kind}, client ${maskIp(req.ip)})`);
    sendError(res, 429, "RATE_LIMITED", RATE_LIMITED_MESSAGE);
  };
}

/**
 * Crea i due middleware, nell'ordine in cui vanno montati: prima il limite
 * per IP, poi quello globale. Chi viene bloccato dal primo non arriva al
 * secondo, quindi non consuma il limite globale.
 *
 * @param {{ windowMin: number, perIp: number, global: number }} config
 * @returns {import("express").RequestHandler[]}
 */
export function createRateLimiters(config) {
  const common = {
    windowMs: config.windowMin * 60_000,
    // Intestazioni RateLimit-* standard (draft-7) e Retry-After in secondi;
    // quelle "legacy" (X-RateLimit-*) non servono.
    standardHeaders: "draft-7",
    legacyHeaders: false,
  };

  const perIp = rateLimit({
    ...common,
    limit: config.perIp,
    handler: createLimitHandler("per IP"),
  });

  const global = rateLimit({
    ...common,
    limit: config.global,
    // Chiave unica: tutte le richieste finiscono nello stesso contatore.
    keyGenerator: () => "global",
    handler: createLimitHandler("globale"),
  });

  return [perIp, global];
}
