/**
 * GET /charts/:filename (CONTRATTO_API.md): proxy verso il data agent.
 *
 * Il browser parla solo con il back end, quindi i PNG generati da FastAPI
 * passano da qui. La route non legge mai file dal disco: il nome ricevuto non
 * viene usato come percorso, ma solo (dopo la validazione) per chiedere il
 * file a FastAPI. Gli errori sono lanciati come HttpError e li trasforma il
 * middleware di errore (Express 5 inoltra da solo le eccezioni degli handler
 * async).
 */
import { Router } from "express";
import { CHART_FILENAME_PATTERN, fetchChart } from "../services/dataAgentService.js";
import { HttpError } from "../http/errors.js";

const router = Router();

router.get("/charts/:filename", async (req, res) => {
  const { filename } = req.params;

  // Protezione da path traversal: Express decodifica %2F in "/", quindi un
  // nome come "../../etc/passwd" arriva qui come stringa e viene scartato.
  if (!CHART_FILENAME_PATTERN.test(filename)) {
    throw new HttpError(400, "INVALID_REQUEST", "Il nome del grafico non è valido.");
  }

  let image;
  try {
    image = await fetchChart(filename);
  } catch (error) {
    // Il dettaglio è già nel log di dataAgentService. Il contratto non prevede
    // un codice dedicato per "grafico non disponibile": si usa INTERNAL_ERROR.
    console.error(`[charts] recupero di ${filename} fallito (${error.code ?? error.name})`);
    throw new HttpError(500, "INTERNAL_ERROR", "Il grafico non è al momento disponibile.");
  }

  if (image === null) {
    throw new HttpError(404, "NOT_FOUND", "Grafico non trovato.");
  }

  // nosniff: il browser deve trattare la risposta come immagine e basta.
  res.set({ "Content-Type": "image/png", "X-Content-Type-Options": "nosniff" });
  res.send(image);
});

export default router;
