/**
 * Strumenti dell'orchestratore (docs/DESIGN_ORCHESTRATORE.md §4):
 * `search_handbook` (RAG sul manuale) e `analyze_data` (data agent Python).
 *
 * Stato per turno, senza stato globale: `createTurnTools()` va chiamata UNA
 * VOLTA PER RICHIESTA. Tutto ciò che si raccoglie durante il turno
 * (`toolsUsed`, `sources`, `chartUrl`) vive nella closure di quella chiamata,
 * quindi due richieste concorrenti non possono mescolare i propri risultati.
 *
 * Regola sugli errori: nessun tool lancia mai verso l'orchestratore. Ogni
 * guasto diventa un testo "ERRORE_STRUMENTO: ..." che il modello legge e
 * dichiara all'utente; il turno continua e la route risponde comunque 200.
 * Nel testo va solo un messaggio pulito: i dettagli (che potrebbero contenere
 * URL o percorsi) restano in console.error.
 */
import { tool } from "@langchain/core/tools";
import { z } from "zod";
import { searchHandbook } from "../services/ragService.js";
import {
  analyzeWithDataAgent,
  DataAgentError,
} from "../services/dataAgentService.js";

/** Distanza coseno massima (assoluta) per tenere un passaggio del manuale. */
export const MAX_DISTANCE = 0.6;

/**
 * Scarto massimo (relativo) dalla distanza migliore. Senza questa soglia un
 * passaggio a 0.58 verrebbe tenuto anche quando il migliore è a 0.29, e
 * inquinerebbe `sources` con sezioni solo vagamente collegate.
 */
export const MAX_DISTANCE_GAP = 0.12;

/** Quanti passaggi chiedere a Chroma prima di applicare le soglie. */
const TOP_K = 4;

const NO_PASSAGES =
  "Nessun passaggio pertinente trovato nel manuale per questa ricerca.";

/**
 * Frase che il CODICE (non il modello) aggiunge alla domanda per il data
 * agent quando l'utente ha chiesto un grafico. Definita in un solo punto: è
 * ciò che rende la richiesta di grafico deterministica (v1.2). Con la v1.1,
 * affidata al testo libero del modello, la richiesta spariva 6 volte su 6.
 */
export const CHART_REQUEST_SENTENCE =
  "Genera anche un grafico adatto a mostrare il risultato.";

/**
 * Applica le due soglie di rilevanza ai passaggi restituiti da ragService.
 * La distanza migliore è calcolata con Math.min, senza fidarsi dell'ordine.
 *
 * @param {Array<{distance: number}>} passages
 * @returns {Array} i soli passaggi pertinenti, nell'ordine ricevuto
 */
export function filterRelevantPassages(passages) {
  if (passages.length === 0) return [];
  const best = Math.min(...passages.map((p) => p.distance));
  return passages.filter(
    (p) => p.distance <= MAX_DISTANCE && p.distance <= best + MAX_DISTANCE_GAP,
  );
}

/**
 * Crea i tool di UN turno e lo stato che raccolgono.
 *
 * @returns {{
 *   tools: Array,
 *   runToolCall: (toolCall: {name: string, args: object}) => Promise<string>,
 *   getCollected: () => {toolsUsed: string[], sources: string[], chartUrl: string|null}
 * }}
 */
export function createTurnTools() {
  // Stato del turno: vive solo in questa closure.
  const toolsUsed = [];
  const sources = [];
  let chartUrl = null;

  const searchHandbookTool = tool(
    async ({ query }) => {
      try {
        const { passages } = await searchHandbook(query, TOP_K);
        const relevant = filterRelevantPassages(passages);

        if (relevant.length === 0) return NO_PASSAGES;

        // `sources`: solo le sezioni dei passaggi sopra soglia, senza
        // duplicati, nell'ordine di pertinenza; unione tra più chiamate.
        for (const p of relevant) {
          if (!sources.includes(p.section)) sources.push(p.section);
        }

        const blocks = relevant.map((p, i) => {
          const label = p.subsection
            ? `${p.section} › ${p.subsection}`
            : p.section;
          return `[${i + 1}] ${label}\n${p.text}`;
        });
        return `Passaggi pertinenti del manuale:\n\n${blocks.join("\n\n")}`;
      } catch (error) {
        // Chroma spento, collection mancante, embedding fallito: dettaglio
        // solo nel log, al modello arriva un messaggio pulito.
        console.error("[search_handbook] errore:", error);
        return "ERRORE_STRUMENTO: il manuale non è al momento consultabile.";
      }
    },
    {
      name: "search_handbook",
      description:
        "Cerca nel manuale interno di ScoutEdge Analytics: piani di abbonamento, metodologia di scouting e di calcolo del rating, criteri di valutazione per ruolo, glossario delle metriche, policy dati e privacy, procedura di data cleaning, SLA ed escalation, FAQ del Client Success. Usalo per regole, procedure, definizioni e metodologia, mai per numeri sui dati.",
      schema: z.object({
        query: z
          .string()
          .describe(
            "Frase breve in italiano sull'argomento da cercare, senza riferimenti alla conversazione.",
          ),
      }),
    },
  );

  const analyzeDataTool = tool(
    async ({ question, chart }) => {
      try {
        // La richiesta di grafico la aggiunge il codice, non il modello.
        const fullQuestion = chart
          ? `${question.trim()} ${CHART_REQUEST_SENTENCE}`
          : question;
        const result = await analyzeWithDataAgent(fullQuestion);

        // Vale l'ultimo grafico non nullo tra le chiamate del turno, anche se
        // `chart` era false: se il servizio ne ha generato uno, si mostra.
        if (result.chartUrl) chartUrl = result.chartUrl;

        // Il risultato dichiara sempre l'esito del grafico, così il modello
        // non lo annuncia dalla memoria (v1.2).
        let text = `Risultato dell'analisi:\n${result.answer}`;
        if (result.chartUrl) {
          text +=
            "\n(È stato generato un grafico: lo trovi qui sotto.)";
        } else if (chart) {
          text += "\n(Il grafico richiesto non è stato generato.)";
        }
        return text;
      } catch (error) {
        console.error("[analyze_data] errore:", error);
        // DataAgentError ha già un messaggio pulito; qualunque altro errore
        // (bug, errore di rete non previsto) riceve un messaggio generico.
        const message =
          error instanceof DataAgentError
            ? error.message
            : "il servizio di analisi dati non è al momento disponibile.";
        return `ERRORE_STRUMENTO: ${message}`;
      }
    },
    {
      name: "analyze_data",
      description:
        "Fa analizzare il dataset delle osservazioni di scouting (130 giocatori, 25 club, stagioni 2023/24-2025/26: metriche di performance, scout_rating, valori di mercato, contratti, infortuni) da un servizio che esegue codice Python e può generare grafici. Usalo per qualunque numero, conteggio, media, classifica, confronto, andamento o grafico, e per le correzioni applicate al dataset. Il servizio non vede la conversazione.",
      schema: z.object({
        question: z
          .string()
          .describe(
            "Domanda completa e autonoma in italiano: riferimenti alla conversazione sostituiti da valori espliciti, espressioni temporali della domanda corrente conservate.",
          ),
        chart: z
          .boolean()
          .describe(
            "true se l'utente ha chiesto un grafico, un diagramma o una visualizzazione; altrimenti false.",
          ),
      }),
    },
  );

  const tools = [searchHandbookTool, analyzeDataTool];
  const toolsByName = Object.fromEntries(tools.map((t) => [t.name, t]));

  /**
   * Esegue una tool call richiesta dal modello. NON lancia mai: qualunque
   * problema diventa un testo ERRORE_STRUMENTO. Registra il nome del tool in
   * `toolsUsed` PRIMA di eseguirlo, così compare anche se fallisce.
   *
   * @param {{name: string, args: object}} toolCall
   * @returns {Promise<string>} il contenuto del ToolMessage
   */
  async function runToolCall(toolCall) {
    const { name, args } = toolCall;
    // Prova del routing: nome e argomenti (non il risultato completo).
    console.log(`[tool] ${name}`, JSON.stringify(args));

    const target = toolsByName[name];
    if (!target) {
      console.error(
        `[tool] strumento sconosciuto richiesto dal modello: ${name}`,
      );
      return "ERRORE_STRUMENTO: strumento non disponibile.";
    }

    if (!toolsUsed.includes(name)) toolsUsed.push(name);

    try {
      const result = await target.invoke(args);
      return typeof result === "string" ? result : JSON.stringify(result);
    } catch (error) {
      // Rete di sicurezza: argomenti che non passano lo schema zod o bug
      // imprevisti fuori dai try/catch interni ai tool.
      console.error(`[tool] ${name} fallito:`, error);
      return "ERRORE_STRUMENTO: lo strumento non è riuscito a completare la richiesta.";
    }
  }

  /** Copia dello stato raccolto finora (l'orchestratore la legge a fine turno). */
  function getCollected() {
    return { toolsUsed: [...toolsUsed], sources: [...sources], chartUrl };
  }

  return { tools, runToolCall, getCollected };
}
