import { ChromaClient } from "chromadb";

/**
 * Nome della collection che contiene i chunk dell'handbook.
 * Definito qui, in un unico punto, perché lo usano sia l'ingestion (B3)
 * sia il retrieval (B4): se i due nomi divergessero, la RAG cercherebbe
 * in una collection vuota senza dare errori.
 */
export const COLLECTION_NAME = "platform-handbook";

/**
 * Crea un client per il server Chroma indicato da CHROMA_URL.
 *
 * Il client di chromadb 3.x non accetta un URL unico ma tre parametri
 * separati (host, port, ssl), quindi CHROMA_URL (es. http://localhost:8001)
 * viene scomposto con new URL().
 *
 * La variabile si legge qui dentro e non a livello di modulo: così il
 * risultato non dipende dall'ordine in cui dotenv e questo file vengono
 * importati.
 *
 * @returns {ChromaClient} client pronto all'uso (nessuna connessione aperta
 *   finché non si chiama un metodo: è solo un wrapper HTTP senza stato)
 * @throws {Error} se CHROMA_URL manca o non è un URL http(s) valido
 */
export function getChromaClient() {
  const rawUrl = process.env.CHROMA_URL;
  if (!rawUrl) {
    throw new Error(
      "CHROMA_URL non è definita: aggiungila a .env (es. CHROMA_URL=http://localhost:8001).",
    );
  }

  // new URL() non fallisce con "localhost:8001": legge "localhost:" come
  // protocollo e restituirebbe host e porta sbagliati senza alcun errore.
  // Per questo si controllano esplicitamente protocollo e hostname.
  // Con "localhost" (senza porta) new URL() lancia invece un TypeError:
  // lo si intercetta per dare lo stesso messaggio chiaro in entrambi i casi.
  // Il valore di CHROMA_URL non va nel messaggio: potrebbe contenere credenziali.
  let url = null;
  try {
    url = new URL(rawUrl);
  } catch {
    // url resta null e si lancia l'errore qui sotto
  }
  if (!url || !["http:", "https:"].includes(url.protocol) || !url.hostname) {
    throw new Error(
      "CHROMA_URL deve iniziare con http:// o https:// e contenere un host (es. http://localhost:8001).",
    );
  }

  const ssl = url.protocol === "https:";
  // url.port è una stringa vuota se la porta è quella di default del protocollo.
  const port = url.port ? Number(url.port) : ssl ? 443 : 80;

  return new ChromaClient({ host: url.hostname, port, ssl });
}
