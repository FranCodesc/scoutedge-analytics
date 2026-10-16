import { OpenAIEmbeddings } from "@langchain/openai";

/**
 * Modello di embedding usato sia in ingestion sia in retrieval.
 * Definito in un unico punto: se i chunk fossero indicati con un modello e
 * le domande con un altro, i vettori vivrebbero in spazi diversi e la
 * ricerca restituirebbe risultati sbagliati senza alcun errore.
 */
export const EMBEDDING_MODEL = "text-embedding-3-small";

/**
 * Crea il client di embedding OpenAI.
 *
 * Si crea dentro la funzione e non a livello di modulo perché la chiave
 * OPENAI_API_KEY viene letta da process.env al momento della creazione:
 * così il risultato non dipende dall'ordine di import di dotenv.
 *
 * @returns {OpenAIEmbeddings} con embedDocuments(testi) per i chunk e
 *   embedQuery(testo) per la domanda dell'utente
 */
export function getEmbeddings() {
  return new OpenAIEmbeddings({ model: EMBEDDING_MODEL });
}
