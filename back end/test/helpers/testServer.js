import assert from "node:assert/strict";
import { mock } from "node:test";
import { createApp } from "../../src/app.js";
import { createSessionStore } from "../../src/services/sessionStore.js";

/** Risultato di un turno riuscito, nella forma restituita da runOrchestrator. */
export const OK_RESULT = Object.freeze({
  reply: "Risposta di prova.",
  toolsUsed: ["search_handbook"],
  sources: ["7. SLA e procedura di supporto"],
  chartUrl: null,
});

const openServers = [];

/** Chiude tutti i server avviati dai test (da chiamare in afterEach). */
export async function closeAllServers() {
  for (const server of openServers.splice(0)) {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
}

/** I log delle route (una riga per richiesta, errori) non devono sporcare l'output dei test. */
export function silenceConsole() {
  mock.method(console, "log", () => {});
  mock.method(console, "error", () => {});
  mock.method(console, "warn", () => {});
}

/**
 * Avvia l'app vera (createApp) su una porta libera di 127.0.0.1, con orchestratore,
 * servizio dei grafici e store delle sessioni simulati. Nessuna rete esterna.
 *
 * @param {object} [options]  opzioni di createApp (rateLimitConfig, frontendOrigin,
 *   chatTimeoutMs, trustProxy) più, facoltativi, `fetchChart` e `sessionStore` da sostituire
 */
export async function startTestApp({ fetchChart, sessionStore, ...appOptions } = {}) {
  let impl = async () => OK_RESULT;
  const runOrchestrator = mock.fn((args) => impl(args));
  const chartFetcher = fetchChart ?? mock.fn(async () => null);
  const store = sessionStore ?? createSessionStore();

  const app = createApp({
    ...appOptions,
    runOrchestrator,
    fetchChart: chartFetcher,
    sessionStore: store,
  });

  const server = await new Promise((resolve) => {
    const s = app.listen(0, "127.0.0.1", () => resolve(s));
  });
  openServers.push(server);
  const base = `http://127.0.0.1:${server.address().port}`;

  const send = (method, path, init = {}) => fetch(`${base}${path}`, { method, ...init });

  return {
    base,
    runOrchestrator,
    fetchChart: chartFetcher,
    sessionStore: store,
    /** Cambia il comportamento dell'orchestratore finto per i test successivi. */
    setOrchestrator(fn) {
      impl = fn;
    },
    send,
    get: (path, headers) => send("GET", path, { headers }),
    /** POST /api/chat: `body` in JSON, oppure `raw` per un corpo scritto a mano. */
    post(body, { raw, headers = {} } = {}) {
      return send("POST", "/api/chat", {
        headers: { "Content-Type": "application/json", ...headers },
        body: raw ?? JSON.stringify(body),
      });
    },
  };
}

/**
 * Controlla una risposta di errore: stato, codice e forma esatta
 * { error: { code, message } }, senza dettagli interni. Restituisce il corpo.
 */
export async function expectError(res, status, code) {
  assert.equal(res.status, status);
  assert.match(res.headers.get("content-type") ?? "", /application\/json/);
  const body = await res.json();
  assert.deepEqual(Object.keys(body), ["error"]);
  assert.deepEqual(Object.keys(body.error).sort(), ["code", "message"]);
  assert.equal(body.error.code, code);
  assert.ok(body.error.message.trim().length > 0);
  assert.doesNotMatch(body.error.message, /\.js:\d+|node_modules|sk-|stack/i);
  return body;
}

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Aspetta che `condition()` diventi vera (controllo ogni 5 ms). */
export async function waitFor(condition, timeoutMs = 2000) {
  const startedAt = Date.now();
  while (!condition()) {
    if (Date.now() - startedAt > timeoutMs) throw new Error("waitFor: tempo scaduto");
    await sleep(5);
  }
}

/** Una promessa che si risolve quando lo decide il test. */
export function deferred() {
  let resolve;
  const promise = new Promise((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
