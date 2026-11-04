import "dotenv/config";
import { createApp } from "./app.js";
import { loadRateLimitConfig, readTrustProxy } from "./http/rateLimit.js";

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

const app = createApp({
  frontendOrigin: FRONTEND_ORIGIN,
  rateLimitConfig,
  trustProxy,
});

if (rateLimitConfig) {
  console.log(
    `Limite di frequenza attivo su POST /api/chat: ${rateLimitConfig.perIp} richieste per client ` +
      `e ${rateLimitConfig.global} in totale ogni ${rateLimitConfig.windowMin} minuti` +
      (trustProxy !== undefined ? ` (trust proxy: ${trustProxy})` : ""),
  );
} else {
  console.log("Limite di frequenza disattivato (variabili RATE_LIMIT_* non impostate).");
}

app.listen(PORT, () => {
  console.log(`Back end in ascolto su http://localhost:${PORT}`);
});
