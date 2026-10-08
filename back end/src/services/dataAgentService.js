/** Timeout della chiamata al data agent (contratto API: 90 s). */
const DATA_AGENT_TIMEOUT_MS = 90_000;

/**
 * Forma attesa del path del grafico restituito da FastAPI. Si ricontrolla
 * qui, oltre che nel data agent, perché il back end lo userà per costruire
 * l'URL del proxy dei grafici (B8): meglio non fidarsi del dato in ingresso.
 */
const CHART_URL_PATTERN = /^\/charts\/chart_[0-9a-f]{8}\.png$/;

/**
 * Errore del data agent con un codice leggibile da chi chiama.
 *
 * Il messaggio è pulito e senza dettagli tecnici: il dettaglio (testo di
 * FastAPI, errori di rete) va solo in console.error, perché il contratto
 * vieta di mostrare al browser errori interni.
 *
 * Codici: TIMEOUT (oltre il tempo massimo), UNREACHABLE (servizio non
 * raggiungibile o non configurato), UPSTREAM_ERROR (il servizio ha risposto
 * con un errore o con una risposta inattesa).
 */
export class DataAgentError extends Error {
  /**
   * @param {"TIMEOUT"|"UNREACHABLE"|"UPSTREAM_ERROR"} code
   * @param {string} message messaggio pulito, senza dettagli tecnici
   */
  constructor(code, message) {
    super(message);
    this.name = "DataAgentError";
    this.code = code;
  }
}

/**
 * Legge DATA_AGENT_URL e controlla che sia un URL http(s) con un host.
 *
 * Si legge qui dentro e non a livello di modulo, come in chromaClient.js,
 * così il risultato non dipende dall'ordine di import di dotenv. Il
 * controllo del protocollo è lo stesso: new URL("127.0.0.1:8000") non
 * fallisce, ma legge "127.0.0.1:" come protocollo e darebbe valori sbagliati.
 *
 * @returns {string} URL di base senza "/" finale
 * @throws {DataAgentError} UNREACHABLE se manca o è malformata (il dettaglio
 *   della configurazione sbagliata va nel log, non nel messaggio)
 */
function getDataAgentBaseUrl() {
  const rawUrl = process.env.DATA_AGENT_URL;

  let url = null;
  try {
    url = rawUrl ? new URL(rawUrl) : null;
  } catch {
    // url resta null e si segnala l'errore qui sotto
  }

  if (!url || !["http:", "https:"].includes(url.protocol) || !url.hostname) {
    console.error(
      "[dataAgentService] DATA_AGENT_URL mancante o non valida: deve iniziare con http:// o https:// (es. http://127.0.0.1:8000).",
    );
    throw new DataAgentError(
      "UNREACHABLE",
      "Il servizio di analisi dati non è al momento raggiungibile.",
    );
  }

  return url.href.replace(/\/$/, "");
}

/**
 * Invia una domanda al microservizio Python (FastAPI) per l'analisi dati.
 *
 * Il data agent non ha memoria conversazionale: la domanda deve essere già
 * autonoma (la riformulazione spetta all'orchestratore).
 *
 * @param {string} question domanda autonoma sui dati
 * @param {{ timeoutMs?: number }} [options] timeoutMs serve solo per
 *   provare il timeout senza aspettare 90 s; chi chiama con un solo
 *   argomento ottiene il valore del contratto
 * @returns {Promise<{ answer: string, chartUrl: string|null }>} chartUrl è
 *   il path relativo del grafico (es. /charts/chart_ab12cd34.png) o null
 * @throws {DataAgentError} con code TIMEOUT, UNREACHABLE o UPSTREAM_ERROR
 */
export async function analyzeWithDataAgent(
  question,
  { timeoutMs = DATA_AGENT_TIMEOUT_MS } = {},
) {
  const baseUrl = getDataAgentBaseUrl();

  // Un unico try/catch attorno a fetch e lettura del corpo: il timeout di
  // AbortSignal.timeout può scattare anche mentre si legge la risposta, e
  // così la classificazione degli errori sta in un solo punto.
  try {
    const response = await fetch(`${baseUrl}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: AbortSignal.timeout(timeoutMs),
    });

    if (!response.ok) {
      // Il corpo del 502 di FastAPI contiene il testo grezzo dell'eccezione:
      // solo nel log, mai nel messaggio.
      const detail = await response.text();
      console.error(`[dataAgentService] risposta ${response.status}: ${detail}`);
      throw new DataAgentError(
        "UPSTREAM_ERROR",
        "Il servizio di analisi dati non è riuscito a completare l'analisi.",
      );
    }

    const body = await response.json();
    if (typeof body?.answer !== "string") {
      console.error("[dataAgentService] risposta senza il campo 'answer':", body);
      throw new DataAgentError(
        "UPSTREAM_ERROR",
        "Il servizio di analisi dati non è riuscito a completare l'analisi.",
      );
    }

    // chart_url è un dettaglio interno di FastAPI: al resto del back end
    // arriva come chartUrl, e solo se ha la forma attesa.
    let chartUrl = null;
    if (body.chart_url != null) {
      if (CHART_URL_PATTERN.test(body.chart_url)) {
        chartUrl = body.chart_url;
      } else {
        console.error("[dataAgentService] chart_url scartato (formato inatteso):", body.chart_url);
      }
    }

    return { answer: body.answer, chartUrl };
  } catch (error) {
    if (error instanceof DataAgentError) throw error;

    if (error.name === "TimeoutError") {
      console.error(`[dataAgentService] timeout dopo ${timeoutMs} ms`);
      throw new DataAgentError(
        "TIMEOUT",
        "L'analisi dei dati ha impiegato troppo tempo e non è stata completata.",
      );
    }

    // response.json() fallisce con SyntaxError se il corpo non è JSON.
    if (error instanceof SyntaxError) {
      console.error("[dataAgentService] risposta non in formato JSON:", error.message);
      throw new DataAgentError(
        "UPSTREAM_ERROR",
        "Il servizio di analisi dati non è riuscito a completare l'analisi.",
      );
    }

    // Tutto il resto è un errore di rete (connessione rifiutata, DNS…).
    console.error("[dataAgentService] data agent non raggiungibile:", error.cause?.code ?? error.message);
    throw new DataAgentError(
      "UNREACHABLE",
      "Il servizio di analisi dati non è al momento raggiungibile.",
    );
  }
}
