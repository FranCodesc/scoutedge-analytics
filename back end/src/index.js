import "dotenv/config";
import express from "express";
import cors from "cors";
import chartsRouter from "./routes/charts.js";
import { notFoundHandler, errorHandler } from "./http/errors.js";
import {
  createRateLimiters,
  loadRateLimitConfig,
  readTrustProxy,
} from "./http/rateLimit.js";
import chatRouter from "./routes/chat.js";

const app = express();
const PORT = process.env.PORT || 3001;
const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || "http://localhost:5173";

// Configurazione del limite di frequenza, letta una sola volta all'avvio. Se è
// incompleta o non valida il back end non parte: online, un limite spento per
// errore non deve passare inosservato.
let rateLimitConfig;
let trustProxy;
try {
  rateLimitConfig = loadRateLimitConfig(process.env);
  trustProxy = readTrustProxy(process.env);
} catch (err) {
  console.error(`Configurazione non valida: ${err.message}`);
  process.exit(1);
}

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
app.use(cors({ origin: FRONTEND_ORIGIN }));

if (rateLimitConfig) {
  // Solo POST /api/chat: GET /, /charts e le richieste preflight non contano.
  app.post("/api/chat", ...createRateLimiters(rateLimitConfig));
  console.log(
    `Limite di frequenza attivo su POST /api/chat: ${rateLimitConfig.perIp} richieste per client ` +
      `e ${rateLimitConfig.global} in totale ogni ${rateLimitConfig.windowMin} minuti` +
      (trustProxy !== undefined ? ` (trust proxy: ${trustProxy})` : ""),
  );
} else {
  console.log("Limite di frequenza disattivato (variabili RATE_LIMIT_* non impostate).");
}

app.use(express.json({ limit: "10kb" }));

app.get("/", (req, res) => {
  res.json({ status: "ok" });
});

app.use(chartsRouter);
app.use(chatRouter);

app.use(notFoundHandler);
app.use(errorHandler);

app.listen(PORT, () => {
  console.log(`Back end in ascolto su http://localhost:${PORT}`);
});
