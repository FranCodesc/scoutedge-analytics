const DATA_AGENT_URL = process.env.DATA_AGENT_URL || "http://127.0.0.1:8000";

/**
 * Invia una domanda al microservizio Python (FastAPI) per l'analisi dati.
 * Restituisce { answer, chart_url }.
 */
export async function analyzeWithDataAgent(question) {
  const response = await fetch(`${DATA_AGENT_URL}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });

  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`Data agent error (${response.status}): ${errorBody}`);
  }

  return response.json(); // { answer, chart_url }
}