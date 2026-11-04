import { test, describe, beforeEach, afterEach, mock } from "node:test";
import assert from "node:assert/strict";
import {
  analyzeWithDataAgent,
  fetchChart,
  DataAgentError,
  CHART_FILENAME_PATTERN,
} from "../src/services/dataAgentService.js";

const BASE = "http://127.0.0.1:8000";
const originalUrl = process.env.DATA_AGENT_URL;

/** Sostituisce fetch con `impl` e restituisce il mock (per leggere le chiamate). */
function mockFetch(impl) {
  return mock.method(globalThis, "fetch", impl);
}

const jsonResponse = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

/** Controlla che la promessa fallisca con un DataAgentError di quel codice e un messaggio pulito. */
async function rejectsWithCode(promise, code) {
  await assert.rejects(promise, (error) => {
    assert.ok(
      error instanceof DataAgentError,
      `atteso DataAgentError, ricevuto ${error?.name}`,
    );
    assert.equal(error.code, code);
    assert.ok(error.message.length > 0);
    // Il messaggio va all'LLM e poi all'utente: niente indirizzi, tracce o errori di rete.
    assert.doesNotMatch(
      error.message,
      /127\.0\.0\.1|Traceback|ECONNREFUSED|fetch failed/,
    );
    return true;
  });
}

beforeEach(() => {
  process.env.DATA_AGENT_URL = BASE;
  // Il dettaglio tecnico va nel log: lo si silenzia nei test e lo si può ispezionare.
  mock.method(console, "error", () => {});
});

afterEach(() => {
  mock.restoreAll();
  if (originalUrl === undefined) delete process.env.DATA_AGENT_URL;
  else process.env.DATA_AGENT_URL = originalUrl;
});

describe("CHART_FILENAME_PATTERN", () => {
  test("accetta chart_ + 8 esadecimali minuscoli + .png", () => {
    assert.ok(CHART_FILENAME_PATTERN.test("chart_ab12cd34.png"));
    assert.ok(CHART_FILENAME_PATTERN.test("chart_00000000.png"));
  });

  for (const bad of [
    "chart_XYZ.png",
    "chart_AB12CD34.png",
    "chart_ab12cd3.png",
    "chart_ab12cd345.png",
    "chart_ab12cd34.PNG",
    "chart_ab12cd34.png.exe",
    "../chart_ab12cd34.png",
    "x/chart_ab12cd34.png",
    "",
  ]) {
    test(`rifiuta "${bad}"`, () => {
      assert.equal(CHART_FILENAME_PATTERN.test(bad), false);
    });
  }
});

describe("analyzeWithDataAgent", () => {
  test("richiesta: POST su /analyze con la domanda in JSON e un segnale di timeout", async () => {
    const m = mockFetch(async () =>
      jsonResponse({ answer: "130", chart_url: null }),
    );
    await analyzeWithDataAgent("Quanti giocatori ci sono?");

    assert.equal(m.mock.callCount(), 1);
    const [url, options] = m.mock.calls[0].arguments;
    assert.equal(url, `${BASE}/analyze`);
    assert.equal(options.method, "POST");
    assert.equal(options.headers["Content-Type"], "application/json");
    assert.deepEqual(JSON.parse(options.body), {
      question: "Quanti giocatori ci sono?",
    });
    assert.ok(options.signal instanceof AbortSignal);
  });

  test("chart_url di FastAPI diventa chartUrl", async () => {
    mockFetch(async () =>
      jsonResponse({ answer: "ecco", chart_url: "/charts/chart_ab12cd34.png" }),
    );
    const result = await analyzeWithDataAgent("domanda");
    assert.deepEqual(result, {
      answer: "ecco",
      chartUrl: "/charts/chart_ab12cd34.png",
    });
    assert.equal("chart_url" in result, false);
  });

  test("senza grafico: chart_url null o assente → chartUrl null", async () => {
    mockFetch(async () => jsonResponse({ answer: "a", chart_url: null }));
    assert.equal((await analyzeWithDataAgent("d")).chartUrl, null);
    mockFetch(async () => jsonResponse({ answer: "a" }));
    assert.equal((await analyzeWithDataAgent("d")).chartUrl, null);
  });

  for (const bad of [
    "../../etc/passwd",
    "/charts/chart_XYZ.png",
    "/charts/../chart_ab12cd34.png",
    "http://evil.example/charts/chart_ab12cd34.png",
    "chart_ab12cd34.png",
  ]) {
    test(`chart_url con forma inattesa "${bad}" → scartato (chartUrl null) e segnalato nel log`, async () => {
      mockFetch(async () => jsonResponse({ answer: "a", chart_url: bad }));
      const result = await analyzeWithDataAgent("d");
      assert.equal(result.chartUrl, null);
      assert.equal(result.answer, "a");
      assert.ok(console.error.mock.callCount() >= 1);
    });
  }

  test("DATA_AGENT_URL con la barra finale non produce doppie barre", async () => {
    process.env.DATA_AGENT_URL = `${BASE}/`;
    const m = mockFetch(async () => jsonResponse({ answer: "a" }));
    await analyzeWithDataAgent("d");
    assert.equal(m.mock.calls[0].arguments[0], `${BASE}/analyze`);
  });

  for (const [label, value] of [
    ["mancante", undefined],
    ["senza protocollo", "127.0.0.1:8000"],
    ["con protocollo non http", "ftp://127.0.0.1:8000"],
    ["non è un URL", "not a url"],
  ]) {
    test(`DATA_AGENT_URL ${label} → UNREACHABLE, senza chiamare la rete`, async () => {
      if (value === undefined) delete process.env.DATA_AGENT_URL;
      else process.env.DATA_AGENT_URL = value;
      const m = mockFetch(async () => jsonResponse({ answer: "a" }));
      await rejectsWithCode(analyzeWithDataAgent("d"), "UNREACHABLE");
      assert.equal(m.mock.callCount(), 0);
    });
  }

  test("FastAPI risponde con un errore → UPSTREAM_ERROR; il testo grezzo resta nel log, non nel messaggio", async () => {
    mockFetch(
      async () =>
        new Response("Traceback (most recent call last): segreto", {
          status: 502,
        }),
    );
    await rejectsWithCode(analyzeWithDataAgent("d"), "UPSTREAM_ERROR");
    const logged = console.error.mock.calls
      .map((c) => c.arguments.join(" "))
      .join("\n");
    assert.match(logged, /502/);
    assert.match(logged, /Traceback/);
  });

  test("risposta 200 senza il campo answer → UPSTREAM_ERROR", async () => {
    mockFetch(async () => jsonResponse({ risposta: "a" }));
    await rejectsWithCode(analyzeWithDataAgent("d"), "UPSTREAM_ERROR");
  });

  test("answer non testuale → UPSTREAM_ERROR", async () => {
    mockFetch(async () => jsonResponse({ answer: 42 }));
    await rejectsWithCode(analyzeWithDataAgent("d"), "UPSTREAM_ERROR");
  });

  test("corpo che non è JSON → UPSTREAM_ERROR", async () => {
    mockFetch(async () => new Response("<html>errore</html>", { status: 200 }));
    await rejectsWithCode(analyzeWithDataAgent("d"), "UPSTREAM_ERROR");
  });

  test("connessione rifiutata → UNREACHABLE", async () => {
    mockFetch(async () => {
      throw Object.assign(new TypeError("fetch failed"), {
        cause: { code: "ECONNREFUSED" },
      });
    });
    await rejectsWithCode(analyzeWithDataAgent("d"), "UNREACHABLE");
  });

  test("errore di timeout di fetch → TIMEOUT", async () => {
    mockFetch(async () => {
      throw new DOMException("The operation timed out.", "TimeoutError");
    });
    await rejectsWithCode(analyzeWithDataAgent("d"), "TIMEOUT");
  });

  test("timeout vero: un servizio che non risponde viene interrotto da timeoutMs → TIMEOUT", async () => {
    // La finta rispetta il segnale come farebbe fetch: non risponde mai, si interrompe all'abort.
    mockFetch(
      (url, { signal }) =>
        new Promise((_, reject) => {
          signal.addEventListener("abort", () => reject(signal.reason), {
            once: true,
          });
        }),
    );
    const startedAt = Date.now();
    await rejectsWithCode(
      analyzeWithDataAgent("d", { timeoutMs: 30 }),
      "TIMEOUT",
    );
    assert.ok(
      Date.now() - startedAt < 2000,
      "il timeout ridotto deve scattare subito",
    );
  });
});

describe("fetchChart", () => {
  const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const pngResponse = () =>
    new Response(png, {
      status: 200,
      headers: { "Content-Type": "image/png" },
    });

  test("scarica il PNG da /charts/<nome> e lo restituisce come Buffer", async () => {
    const m = mockFetch(async () => pngResponse());
    const image = await fetchChart("chart_ab12cd34.png");
    assert.ok(Buffer.isBuffer(image));
    assert.deepEqual(image, png);
    assert.equal(
      m.mock.calls[0].arguments[0],
      `${BASE}/charts/chart_ab12cd34.png`,
    );
  });

  for (const bad of ["../x", "chart_XYZ.png", "chart_ab12cd34.png/../x", ""]) {
    test(`nome non valido "${bad}" → errore, senza chiamare la rete`, async () => {
      const m = mockFetch(async () => pngResponse());
      await assert.rejects(fetchChart(bad), /nome del file non valido/);
      assert.equal(m.mock.callCount(), 0);
    });
  }

  test("404 di FastAPI → null (grafico inesistente o cancellato: non è un errore)", async () => {
    mockFetch(async () => new Response("not found", { status: 404 }));
    assert.equal(await fetchChart("chart_ab12cd34.png"), null);
  });

  test("altro errore di FastAPI → UPSTREAM_ERROR", async () => {
    mockFetch(async () => new Response("boom", { status: 500 }));
    await rejectsWithCode(fetchChart("chart_ab12cd34.png"), "UPSTREAM_ERROR");
  });

  test("200 ma non un PNG (es. una pagina HTML) → UPSTREAM_ERROR, non viene inoltrato", async () => {
    mockFetch(
      async () =>
        new Response("<html></html>", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        }),
    );
    await rejectsWithCode(fetchChart("chart_ab12cd34.png"), "UPSTREAM_ERROR");
  });

  test("200 senza Content-Type → UPSTREAM_ERROR", async () => {
    mockFetch(async () => new Response(png, { status: 200 }));
    await rejectsWithCode(fetchChart("chart_ab12cd34.png"), "UPSTREAM_ERROR");
  });

  test("servizio non raggiungibile → UNREACHABLE", async () => {
    mockFetch(async () => {
      throw Object.assign(new TypeError("fetch failed"), {
        cause: { code: "ECONNREFUSED" },
      });
    });
    await rejectsWithCode(fetchChart("chart_ab12cd34.png"), "UNREACHABLE");
  });

  test("timeout → TIMEOUT", async () => {
    mockFetch(async () => {
      throw new DOMException("The operation timed out.", "TimeoutError");
    });
    await rejectsWithCode(fetchChart("chart_ab12cd34.png"), "TIMEOUT");
  });

  test("DATA_AGENT_URL mancante → UNREACHABLE", async () => {
    delete process.env.DATA_AGENT_URL;
    mockFetch(async () => pngResponse());
    await rejectsWithCode(fetchChart("chart_ab12cd34.png"), "UNREACHABLE");
  });
});
