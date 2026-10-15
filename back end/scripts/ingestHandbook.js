import "dotenv/config";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { getChromaClient, COLLECTION_NAME } from "../src/services/chromaClient.js";
import { getEmbeddings } from "../src/services/embeddings.js";

/**
 * Percorso dell'handbook, calcolato dalla posizione di questo file e non
 * dalla cartella da cui si lancia lo script: così funziona da qualunque
 * directory (e anche con lo spazio in "back end").
 */
const HANDBOOK_PATH = fileURLToPath(
  new URL("../../data/platform_handbook.md", import.meta.url),
);

/** Sezioni divise per sottosezione "###" (§3: 3.1-3.4, una per chunk). */
const SECTIONS_SPLIT_BY_SUBSECTION = new Set(["3"]);

/** Sezione FAQ, divisa per domanda (una coppia D/R per chunk). */
const FAQ_SECTION = "8";

/**
 * @typedef {Object} Chunk
 * @property {string} id        id deterministico (es. "sec-3-1", "sec-8-q3")
 * @property {string} text      testo da indicizzare, inizia con i titoli
 * @property {{section: string, subsection?: string}} metadata
 */

/**
 * Toglie il separatore "---" che chiude ogni sezione nell'handbook: è un
 * elemento grafico, non contenuto, e sporcherebbe l'embedding.
 *
 * @param {string} text
 * @returns {string}
 */
function stripTrailingSeparator(text) {
  return text.trim().replace(/\n*---$/, "").trim();
}

/**
 * Divide l'handbook in chunk con una strategia mista:
 * intestazione esclusa; sezioni intere, tranne §3 (per "###") e §8 (per
 * domanda). Ogni chunk inizia con il titolo della sezione (e della
 * sottosezione o domanda), così l'embedding conserva il contesto: un
 * paragrafo come "Il rating è calibrato per ruolo" da solo non dice a quale
 * argomento appartiene.
 *
 * @param {string} markdown contenuto di platform_handbook.md
 * @returns {Chunk[]}
 * @throws {Error} se la struttura non è quella attesa (titolo senza
 *   numero, testo che andrebbe perso, id duplicati): meglio fermarsi che
 *   indicizzare un handbook letto a metà
 */
export function parseHandbook(markdown) {
  /** @type {Chunk[]} */
  const chunks = [];

  // Il primo pezzo (titolo, versione, "Ad uso di") precede la prima sezione
  // "## ": non porta contenuto utile e si scarta con slice(1).
  const sections = markdown.split(/^## /m).slice(1);

  for (const rawSection of sections) {
    const firstLineEnd = rawSection.indexOf("\n");
    const section = rawSection.slice(0, firstLineEnd).trim();
    const body = stripTrailingSeparator(rawSection.slice(firstLineEnd + 1));

    const number = section.match(/^(\d+)\./)?.[1];
    if (!number) {
      throw new Error(`Titolo di sezione senza numero: "${section}"`);
    }

    if (SECTIONS_SPLIT_BY_SUBSECTION.has(number)) {
      const [intro, ...subsections] = body.split(/^### /m);
      if (intro.trim()) {
        throw new Error(
          `Testo prima della prima sottosezione di "${section}": andrebbe perso.`,
        );
      }
      for (const rawSub of subsections) {
        const subLineEnd = rawSub.indexOf("\n");
        const subsection = rawSub.slice(0, subLineEnd).trim();
        const subNumber = subsection.match(/^(\d+\.\d+)/)?.[1];
        if (!subNumber) {
          throw new Error(`Sottosezione senza numero: "${subsection}"`);
        }
        chunks.push({
          id: `sec-${subNumber.replace(".", "-")}`,
          text: `${section}\n${subsection}\n\n${rawSub.slice(subLineEnd + 1).trim()}`,
          metadata: { section, subsection },
        });
      }
    } else if (number === FAQ_SECTION) {
      const [intro, ...faqs] = body.split(/^\*\*D: /m);
      if (intro.trim()) {
        throw new Error(
          `Testo prima della prima domanda di "${section}": andrebbe perso.`,
        );
      }
      faqs.forEach((rawFaq, index) => {
        // Dopo lo split resta "<domanda>**\nR: <risposta>".
        const questionEnd = rawFaq.indexOf("**");
        const question = rawFaq.slice(0, questionEnd).trim();
        const answer = rawFaq.slice(questionEnd + 2).trim();
        if (!answer.startsWith("R:")) {
          throw new Error(`Risposta mancante per la domanda ${index + 1} delle FAQ.`);
        }
        chunks.push({
          id: `sec-${number}-q${index + 1}`,
          text: `${section}\nD: ${question}\n${answer}`,
          metadata: { section, subsection: question },
        });
      });
    } else {
      // Nessun "subsection" nei metadati: Chroma accetta solo valori
      // scalari, quindi la chiave si omette invece di impostarla a null.
      chunks.push({
        id: `sec-${number}`,
        text: `${section}\n\n${body}`,
        metadata: { section },
      });
    }
  }

  // Un id duplicato farebbe sovrascrivere un chunk all'altro in upsert,
  // senza alcun errore: lo si intercetta qui.
  const uniqueIds = new Set(chunks.map((chunk) => chunk.id));
  if (uniqueIds.size !== chunks.length) {
    throw new Error("Id duplicati tra i chunk dell'handbook.");
  }

  return chunks;
}

/**
 * Calcola gli embedding dei chunk e li scrive in Chroma con upsert.
 *
 * Id deterministici + upsert rendono l'operazione idempotente: rilanciare
 * lo script aggiorna gli stessi record invece di duplicarli. L'upsert però
 * non rimuove i chunk che spariscono dall'handbook (es. una sezione tolta
 * in una versione futura), quindi alla fine si cancellano gli id presenti
 * in Chroma e non più nel documento: così count() resta uguale al numero
 * di chunk del file.
 *
 * @param {Chunk[]} chunks
 * @returns {Promise<{dimension: number, removed: number, total: number}>}
 *   dimensione dei vettori, chunk orfani cancellati, chunk presenti alla fine
 */
async function indexChunks(chunks) {
  // Una sola chiamata per tutti i testi: sono 18, ben sotto il limite del
  // batch (embedDocuments li raggrupperebbe comunque da solo).
  const embeddings = await getEmbeddings().embedDocuments(
    chunks.map((chunk) => chunk.text),
  );

  const collection = await getChromaClient().getOrCreateCollection({
    name: COLLECTION_NAME,
    // null = nessuna funzione di embedding di Chroma: i vettori li
    // calcoliamo noi con OpenAI e li passiamo esplicitamente. Senza questo,
    // Chroma userebbe un modello locale diverso e i vettori di ingestion e
    // retrieval vivrebbero in spazi differenti.
    embeddingFunction: null,
    // Distanza coseno: valori leggibili (0 = identico). Si fissa alla
    // creazione e non è modificabile dopo.
    configuration: { hnsw: { space: "cosine" } },
  });

  await collection.upsert({
    ids: chunks.map((chunk) => chunk.id),
    embeddings,
    documents: chunks.map((chunk) => chunk.text),
    metadatas: chunks.map((chunk) => chunk.metadata),
  });

  const wantedIds = new Set(chunks.map((chunk) => chunk.id));
  const existing = await collection.get({ include: [] });
  const orphanIds = existing.ids.filter((id) => !wantedIds.has(id));
  if (orphanIds.length > 0) {
    await collection.delete({ ids: orphanIds });
  }

  return {
    dimension: embeddings[0].length,
    removed: orphanIds.length,
    total: await collection.count(),
  };
}

async function main() {
  const markdown = await readFile(HANDBOOK_PATH, "utf8");
  const chunks = parseHandbook(markdown);
  console.log(`Chunk prodotti dal parsing: ${chunks.length}`);

  const { dimension, removed, total } = await indexChunks(chunks);
  console.log(`Embedding: ${chunks.length} vettori da ${dimension} dimensioni`);
  console.log(`Chunk orfani rimossi: ${removed}`);
  console.log(`Chunk nella collection "${COLLECTION_NAME}": ${total}`);
}

main().catch((error) => {
  console.error("Ingestion fallita:", error.message);
  process.exit(1);
});
