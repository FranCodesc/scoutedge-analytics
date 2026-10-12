import "dotenv/config";
import express from "express";
import cors from "cors";
import chartsRouter from "./routes/charts.js";
import { notFoundHandler, errorHandler } from "./http/errors.js";
import chatRouter from "./routes/chat.js";

const app = express();
const PORT = process.env.PORT || 3001;
const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || "http://localhost:5173";

// Non annunciare Express nelle intestazioni: informazione inutile per un attaccante.
app.disable("x-powered-by");

// ordine rispettato: CORS → JSON → route → 404 → errori. Il middleware di errore
// deve stare per ultimo per intercettare anche gli errori del parser JSON.
app.use(cors({ origin: FRONTEND_ORIGIN }));
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
