import { getChromaClient, COLLECTION_NAME } from "./chromaClient.js";
import { getEmbeddings } from "./embeddings.js";

/**
 * Quanti chunk restituire per domanda. 4 lascia spazio alle domande che
 * toccano più sezioni (es. una FAQ e la sezione a cui rimanda) senza
 * riempire il contesto dell'LLM di testo poco pertinente.
 */
const DEFAULT_TOP_K = 4;

/**
 * @typedef {Object} Passage
 * @property {string} id                 id del chunk (es. "sec-3-1")
 * @property {string} text               testo del chunk, titolo incluso
 * @property {string} section            titolo "##" della sezione
 * @property {string|null} subsection    sottosezione o domanda FAQ, se c'è
 * @property {number|null} distance      distanza coseno dalla domanda
 *   (0 = identico; più è alta, meno il chunk è pertinente)
 */

/**
 * Cerca nell'handbook i chunk più vicini alla domanda.
 *
 * L'embedding della domanda usa lo stesso modello dell'ingestion
 * (getEmbeddings): vettori calcolati con modelli diversi vivrebbero in
 * spazi diversi e la ricerca darebbe risultati sbagliati senza errori.
 *
 * Gli errori (Chroma spento, collection mancante, OpenAI non raggiungibile)
 * non si catturano qui: spetta all'orchestratore trasformarli in un
 * risultato del tool, come prevede il contratto API.
 *
 * @param {string} question domanda dell'utente, già autonoma
 * @param {number} [topK=DEFAULT_TOP_K] numero di chunk da recuperare
 * @returns {Promise<{ passages: Passage[], sections: string[] }>} i
 *   passaggi in ordine di pertinenza e le section senza duplicati (per
 *   il campo "sources" del contratto)
 * @throws {Error} se la domanda è vuota o la ricerca fallisce
 */
export async function searchHandbook(question, topK = DEFAULT_TOP_K) {
  if (typeof question !== "string" || !question.trim()) {
    throw new Error("La domanda per la ricerca nell'handbook non può essere vuota.");
  }

  const queryEmbedding = await getEmbeddings().embedQuery(question);

  // getCollection e non getOrCreate: se la collection manca (ingestion non
  // eseguita) meglio un errore esplicito che una collection vuota che
  // risponderebbe "nessun risultato" in silenzio.
  const collection = await getChromaClient().getCollection({
    name: COLLECTION_NAME,
  });

  const result = await collection.query({
    queryEmbeddings: [queryEmbedding],
    nResults: topK,
    include: ["documents", "metadatas", "distances"],
  });

  // query() accetta più domande insieme e restituisce un array per ciascuna:
  // ne abbiamo mandata una sola, quindi tutto è nella posizione [0].
  const [ids] = result.ids;
  const [documents] = result.documents;
  const [metadatas] = result.metadatas;
  const [distances] = result.distances;

  /** @type {Passage[]} */
  const passages = ids.map((id, i) => ({
    id,
    text: documents[i],
    section: metadatas[i]?.section,
    subsection: metadatas[i]?.subsection ?? null,
    distance: distances[i],
  }));

  // Set mantiene l'ordine di inserimento: la section del chunk più
  // pertinente resta per prima.
  const sections = [...new Set(passages.map((passage) => passage.section))];

  return { passages, sections };
}
