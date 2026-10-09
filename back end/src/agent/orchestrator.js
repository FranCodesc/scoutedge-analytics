/**
 * Orchestratore (B7, DESIGN_ORCHESTRATORE.md §3): ciclo ReAct scritto a mano.
 *
 * Il modello decide quali strumenti chiamare (function calling), noi li
 * eseguiamo e gli restituiamo i risultati, finché risponde senza chiamarne
 * altri. Il ciclo è manuale perché `createAgent` sta nel pacchetto generico
 * `langchain`, che il progetto esclude per scelta.
 *
 * Errori:
 * - del modello dell'orchestratore (OpenAI non raggiungibile, rate limit,
 *   chiave non valida): si PROPAGANO, la route risponde 502 LLM_ERROR;
 * - degli strumenti: non arrivano mai qui, diventano testo "ERRORE_STRUMENTO"
 *   dentro tools.js e il turno prosegue.
 */
import { ChatOpenAI } from "@langchain/openai";
import {
  AIMessage,
  HumanMessage,
  SystemMessage,
  ToolMessage,
} from "@langchain/core/messages";
import { SYSTEM_PROMPT } from "./systemPrompt.js";
import { createTurnTools } from "./tools.js";

/** Modello dell'orchestratore. Se i test di routing falliscono si valuta gpt-4o. */
export const ORCHESTRATOR_MODEL = "gpt-4o-mini";

/** Chiamate massime al modello con i tool disponibili; oltre, chiamata finale senza tool. */
export const MAX_ITERATIONS = 4;

const FINAL_ANSWER_INSTRUCTION =
  "Rispondi ora usando solo i risultati già ottenuti, senza chiamare strumenti.";

/**
 * Converte la history del sessionStore ({ role, content }) in messaggi
 * LangChain. La history contiene solo domande e risposte finali, mai i
 * risultati dei tool (contratto API).
 */
function historyToMessages(history) {
  return history.map((m) =>
    m.role === "user" ? new HumanMessage(m.content) : new AIMessage(m.content),
  );
}

/** Estrae il testo da un AIMessage (content può essere stringa o lista di parti). */
function textOf(message) {
  const { content } = message;
  if (typeof content === "string") return content.trim();
  if (Array.isArray(content)) {
    return content
      .map((part) => (typeof part === "string" ? part : (part.text ?? "")))
      .join("")
      .trim();
  }
  return "";
}

/** Interrompe il turno se la route ha già annullato la richiesta (timeout 120 s). */
function throwIfAborted(signal) {
  if (signal?.aborted) {
    throw signal.reason ?? new Error("Richiesta interrotta.");
  }
}

/**
 * Esegue un turno di conversazione.
 *
 * @param {object} params
 * @param {string} params.message  messaggio dell'utente (già validato dalla route)
 * @param {Array<{role: "user"|"assistant", content: string}>} params.history
 *        history della sessione, senza il messaggio corrente
 * @param {AbortSignal} [params.signal]  annulla le chiamate al modello
 * @returns {Promise<{reply: string, toolsUsed: string[], sources: string[], chartUrl: string|null}>}
 */
export async function runOrchestrator({ message, history = [], signal }) {
  // Stato del turno: nuovo a ogni richiesta, nessuna condivisione tra richieste.
  const { tools, runToolCall, getCollected } = createTurnTools();

  const model = new ChatOpenAI({ model: ORCHESTRATOR_MODEL, temperature: 0 });
  const modelWithTools = model.bindTools(tools);

  const messages = [
    new SystemMessage(SYSTEM_PROMPT),
    ...historyToMessages(history),
    new HumanMessage(message),
  ];

  let reply = null;

  for (let i = 0; i < MAX_ITERATIONS; i++) {
    throwIfAborted(signal);

    const response = await modelWithTools.invoke(messages, { signal });
    messages.push(response);

    const toolCalls = response.tool_calls ?? [];
    if (toolCalls.length === 0) {
      reply = textOf(response);
      break;
    }

    // Tool IN SEQUENZA, mai in parallelo: lo stato globale di matplotlib nel
    // data agent non regge chiamate concorrenti. runToolCall non lancia mai.
    for (const toolCall of toolCalls) {
      const result = await runToolCall(toolCall);
      messages.push(new ToolMessage({ tool_call_id: toolCall.id, content: result }));
    }
  }

  // Limite di iterazioni raggiunto con il modello che chiedeva ancora tool:
  // ultima chiamata SENZA tool, per ottenere comunque una risposta.
  if (reply === null) {
    throwIfAborted(signal);
    messages.push(new SystemMessage(FINAL_ANSWER_INSTRUCTION));
    const finalResponse = await model.invoke(messages, { signal });
    reply = textOf(finalResponse);
  }

  if (!reply) {
    // Meglio un errore esplicito (502 LLM_ERROR) che una risposta vuota.
    throw new Error("Il modello non ha prodotto una risposta.");
  }

  return { reply, ...getCollected() };
}
