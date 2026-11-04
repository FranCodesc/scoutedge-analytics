/**
 * Costruzione dell'app Express, senza avviarla (nessun listen).
 *
 * Le dipendenze hanno come valore predefinito quelle vere: i test passano
 * versioni simulate, così non servono rete, chiavi né servizi accesi.
 * La configurazione (limite di frequenza, trust proxy, origine CORS) arriva
 * da chi chiama: la lettura delle variabili d'ambiente sta in index.js.
 */
import express from "express";
import cors from "cors";
import { createChartsRouter } from "./routes/charts.js";
import { createChatRouter, CHAT_TIMEOUT_MS } from "./routes/chat.js";
import { notFoundHandler, errorHandler } from "./http/errors.js";
import { createRateLimiters } from "./http/rateLimit.js";
import { runOrchestrator as realRunOrchestrator } from "./agent/orchestrator.js";
import { fetchChart as realFetchChart } from "./services/dataAgentService.js";
import { defaultSessionStore } from "./services/sessionStore.js";

/**
 * @param {object} [options]
 * @param {string} [options.frontendOrigin]  origine ammessa dalla CORS
 * @param {{ windowMin: number, perIp: number, global: number } | null} [options.rateLimitConfig]
 *   null = limite di frequenza disattivato
 * @param {number} [options.trustProxy]  numero di proxy fidati; undefined = nessuno
 * @param {Function} [options.runOrchestrator]
 * @param {Function} [options.fetchChart]
 * @param {object} [options.sessionStore]
 * @param {number} [options.chatTimeoutMs]
 */
export function createApp({
  frontendOrigin = "http://localhost:5173",
  rateLimitConfig = null,
  trustProxy,
  runOrchestrator = realRunOrchestrator,
  fetchChart = realFetchChart,
  sessionStore = defaultSessionStore,
  chatTimeoutMs = CHAT_TIMEOUT_MS,
} = {}) {
  const app = express();

  // Non annunciare Express nelle intestazioni: informazione inutile per un attaccante.
  app.disable("x-powered-by");

  // Dietro un proxy (nginx) l'IP del client sta in X-Forwarded-For. Ci si fida
  // solo del numero di proxy dichiarato: senza TRUST_PROXY l'intestazione si
  // ignora, perché un client potrebbe falsificarla per aggirare il limite.
  if (trustProxy !== undefined) {
    app.set("trust proxy", trustProxy);
  }

  // ordine rispettato: CORS → limite di frequenza → JSON → route → 404 → errori.
  // - CORS prima del limite: un 429 senza intestazioni CORS verrebbe bloccato dal
  //   browser e il front end non potrebbe mostrarne il messaggio.
  // - Limite prima di express.json: così contano anche le richieste con JSON non
  //   valido o corpo troppo grande.
  // - Il middleware di errore deve stare per ultimo per intercettare anche gli
  //   errori del parser JSON.
  app.use(cors({ origin: frontendOrigin }));

  if (rateLimitConfig) {
    // Solo POST /api/chat: GET /, /charts e le richieste preflight non contano.
    app.post("/api/chat", ...createRateLimiters(rateLimitConfig));
  }

  app.use(express.json({ limit: "10kb" }));

  app.get("/", (req, res) => {
    res.json({ status: "ok" });
  });

  app.use(createChartsRouter({ fetchChart }));
  app.use(createChatRouter({ runOrchestrator, store: sessionStore, timeoutMs: chatTimeoutMs }));

  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
}
