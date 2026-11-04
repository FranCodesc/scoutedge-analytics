import { test, describe, beforeEach, afterEach, mock } from "node:test";
import assert from "node:assert/strict";
import {
  startTestApp,
  closeAllServers,
  silenceConsole,
  expectError,
  sleep,
  waitFor,
  deferred,
  OK_RESULT,
} from "./helpers/testServer.js";

const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const UNKNOWN_ID = "3f1c2a9e-7b4d-4e8a-9c1f-2d5e6a7b8c9d";

beforeEach(silenceConsole);
afterEach(async () => {
  mock.restoreAll();
  await closeAllServers();
});

describe("POST /api/chat — risposta 200", () => {
  test("restituisce tutti i campi del contratto, e solo quelli", async () => {
    const app = await startTestApp();
    app.setOrchestrator(async () => ({
      reply: "Per le richieste ad alta priorità: 2 ore lavorative.",
      toolsUsed: ["search_handbook", "analyze_data"],
      sources: ["7. SLA e procedura di supporto", "8. FAQ"],
      chartUrl: "/charts/chart_ab12cd34.png",
    }));

    const res = await app.post({ message: "Qual è lo SLA?" });
    assert.equal(res.status, 200);
    const body = await res.json();

    assert.deepEqual(Object.keys(body).sort(), [
      "chartUrl",
      "newSession",
      "reply",
      "sessionId",
      "sources",
      "toolsUsed",
    ]);
    assert.match(body.sessionId, UUID_V4);
    assert.equal(body.newSession, true);
    assert.equal(
      body.reply,
      "Per le richieste ad alta priorità: 2 ore lavorative.",
    );
    assert.equal(body.chartUrl, "/charts/chart_ab12cd34.png");
    assert.deepEqual(body.toolsUsed, ["search_handbook", "analyze_data"]);
    // L'orchestratore restituisce stringhe, il contratto pubblico vuole [{ section }].
    assert.deepEqual(body.sources, [
      { section: "7. SLA e procedura di supporto" },
      { section: "8. FAQ" },
    ]);
  });

  test("senza strumenti né grafico: chartUrl null, toolsUsed e sources vuoti", async () => {
    const app = await startTestApp();
    app.setOrchestrator(async () => ({
      reply: "Ciao!",
      toolsUsed: [],
      sources: [],
      chartUrl: null,
    }));
    const body = await (await app.post({ message: "Ciao!" })).json();
    assert.equal(body.chartUrl, null);
    assert.deepEqual(body.toolsUsed, []);
    assert.deepEqual(body.sources, []);
  });

  test("all'orchestratore arrivano il messaggio senza spazi, la history vuota e un segnale di annullamento", async () => {
    const app = await startTestApp();
    await app.post({ message: "   Ciao   " });

    const args = app.runOrchestrator.mock.calls[0].arguments[0];
    assert.equal(args.message, "Ciao");
    assert.deepEqual(args.history, []);
    assert.ok(args.signal instanceof AbortSignal);
  });

  test("la risposta ha le intestazioni giuste: JSON, nessun x-powered-by", async () => {
    const app = await startTestApp();
    const res = await app.post({ message: "Ciao" });
    assert.match(res.headers.get("content-type"), /application\/json/);
    assert.equal(res.headers.get("x-powered-by"), null);
  });

  test("un messaggio di esattamente 2000 caratteri è accettato (anche con spazi attorno)", async () => {
    const app = await startTestApp();
    const res = await app.post({ message: `  ${"a".repeat(2000)}  ` });
    assert.equal(res.status, 200);
    assert.equal(
      app.runOrchestrator.mock.calls[0].arguments[0].message.length,
      2000,
    );
  });
});

describe("POST /api/chat — sessioni", () => {
  test("stessa sessione: newSession false, stesso id, e l'orchestratore riceve la history del turno precedente", async () => {
    const app = await startTestApp();
    const first = await (await app.post({ message: "Prima domanda" })).json();
    const second = await (
      await app.post({ message: "Seconda", sessionId: first.sessionId })
    ).json();

    assert.equal(first.newSession, true);
    assert.equal(second.newSession, false);
    assert.equal(second.sessionId, first.sessionId);
    assert.deepEqual(app.runOrchestrator.mock.calls[1].arguments[0].history, [
      { role: "user", content: "Prima domanda" },
      { role: "assistant", content: OK_RESULT.reply },
    ]);
  });

  test("sessionId valido ma sconosciuto → 200 con una sessione nuova e un altro id (non è un errore)", async () => {
    const app = await startTestApp();
    const res = await app.post({ message: "Ciao", sessionId: UNKNOWN_ID });
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.newSession, true);
    assert.notEqual(body.sessionId, UNKNOWN_ID);
    assert.match(body.sessionId, UUID_V4);
  });

  test("UUID v4 in maiuscolo è accettato", async () => {
    const app = await startTestApp();
    const res = await app.post({
      message: "Ciao",
      sessionId: UNKNOWN_ID.toUpperCase(),
    });
    assert.equal(res.status, 200);
  });

  test("un turno fallito (502) non lascia tracce nella history e non blocca la sessione", async () => {
    const app = await startTestApp();
    const { sessionId } = await (await app.post({ message: "uno" })).json();

    app.setOrchestrator(async () => {
      throw new Error("OpenAI 401 sk-segreta");
    });
    await expectError(
      await app.post({ message: "due", sessionId }),
      502,
      "LLM_ERROR",
    );

    app.setOrchestrator(async () => OK_RESULT);
    const third = await app.post({ message: "tre", sessionId });
    assert.equal(
      third.status,
      200,
      "il lucchetto è stato rilasciato dopo l'errore",
    );
    const history = app.runOrchestrator.mock.calls.at(-1).arguments[0].history;
    assert.deepEqual(
      history.map((m) => m.content),
      ["uno", OK_RESULT.reply],
    );
  });
});

describe("POST /api/chat — validazione (400 INVALID_REQUEST)", () => {
  const invalidBodies = [
    ["message vuoto", { message: "" }],
    ["message di soli spazi", { message: "  \n\t " }],
    ["message assente", {}],
    ["message numero", { message: 42 }],
    ["message null", { message: null }],
    ["message di 2001 caratteri", { message: "a".repeat(2001) }],
    ["sessionId non UUID", { message: "ciao", sessionId: "abc" }],
    ["sessionId null", { message: "ciao", sessionId: null }],
    ["sessionId numero", { message: "ciao", sessionId: 123 }],
    [
      "UUID che non è v4",
      { message: "ciao", sessionId: "3f1c2a9e-7b4d-1e8a-9c1f-2d5e6a7b8c9d" },
    ],
    ["body array", []],
    ["body stringa", "ciao"],
  ];

  for (const [label, body] of invalidBodies) {
    test(`${label} → 400, senza chiamare l'orchestratore`, async () => {
      const app = await startTestApp();
      await expectError(await app.post(body), 400, "INVALID_REQUEST");
      assert.equal(app.runOrchestrator.mock.callCount(), 0);
    });
  }

  test("JSON malformato → 400", async () => {
    const app = await startTestApp();
    await expectError(
      await app.post(undefined, { raw: '{"message":' }),
      400,
      "INVALID_REQUEST",
    );
    assert.equal(app.runOrchestrator.mock.callCount(), 0);
  });

  test("Content-Type diverso da JSON → 400", async () => {
    const app = await startTestApp();
    const res = await app.post(undefined, {
      raw: "ciao",
      headers: { "Content-Type": "text/plain" },
    });
    await expectError(res, 400, "INVALID_REQUEST");
    assert.equal(app.runOrchestrator.mock.callCount(), 0);
  });
});

describe("POST /api/chat — altri errori", () => {
  test("body oltre 10 kb → 413 PAYLOAD_TOO_LARGE", async () => {
    const app = await startTestApp();
    await expectError(
      await app.post({ message: "a".repeat(11_000) }),
      413,
      "PAYLOAD_TOO_LARGE",
    );
    assert.equal(app.runOrchestrator.mock.callCount(), 0);
  });

  for (const [method, path] of [
    ["GET", "/nonesiste"],
    ["POST", "/nonesiste"],
    ["GET", "/api/chat"],
    ["DELETE", "/api/chat"],
  ]) {
    test(`${method} ${path} → 404 NOT_FOUND`, async () => {
      const app = await startTestApp();
      const body = await expectError(
        await app.send(method, path),
        404,
        "NOT_FOUND",
      );
      assert.equal(body.error.message, "Risorsa non trovata.");
    });
  }

  test("errore dell'orchestratore (rete, chiave, rate limit di OpenAI) → 502 LLM_ERROR senza dettagli", async () => {
    const app = await startTestApp();
    app.setOrchestrator(async () => {
      throw new Error(
        "401 Incorrect API key provided: sk-segreta at https://api.openai.com/v1",
      );
    });

    const res = await app.post({ message: "Ciao" });
    const body = await expectError(res, 502, "LLM_ERROR");
    assert.equal(
      body.error.message,
      "Il servizio di intelligenza artificiale non è al momento disponibile. Riprova tra poco.",
    );
    assert.doesNotMatch(JSON.stringify(body), /sk-segreta|openai/i);
  });

  test("errore imprevisto → 500 INTERNAL_ERROR generico, senza dettagli", async () => {
    const faultyStore = {
      getOrCreateSession() {
        throw new Error("password del database = segreta");
      },
      acquire() {},
      release() {},
      appendTurn() {},
    };
    const app = await startTestApp({ sessionStore: faultyStore });

    const body = await expectError(
      await app.post({ message: "Ciao" }),
      500,
      "INTERNAL_ERROR",
    );
    assert.equal(
      body.error.message,
      "Si è verificato un errore imprevisto. Riprova tra poco.",
    );
    assert.doesNotMatch(JSON.stringify(body), /segreta|database/);
  });
});

describe("POST /api/chat — sessione occupata (409)", () => {
  test("una seconda richiesta sulla stessa sessione mentre la prima è in corso → 409; a lavoro finito si riprende", async () => {
    const app = await startTestApp();
    const { sessionId } = await (await app.post({ message: "seed" })).json();

    const gate = deferred();
    // Solo la richiesta "lenta" aspetta il gate; le altre rispondono subito.
    app.setOrchestrator(({ message }) =>
      message === "lenta"
        ? gate.promise.then(() => OK_RESULT)
        : Promise.resolve(OK_RESULT),
    );
    const slow = app.post({ message: "lenta", sessionId }); // non si aspetta: resta in corso
    await waitFor(() => app.runOrchestrator.mock.callCount() === 2);

    const busy = await app.post({ message: "intrusa", sessionId });
    await expectError(busy, 409, "SESSION_BUSY");
    assert.equal(
      app.runOrchestrator.mock.callCount(),
      2,
      "la richiesta respinta non arriva all'orchestratore",
    );

    // Un'altra sessione non è bloccata.
    const other = await app.post({ message: "altra sessione" });
    assert.equal(other.status, 200);

    gate.resolve();
    assert.equal((await slow).status, 200);

    app.setOrchestrator(async () => OK_RESULT);
    assert.equal((await app.post({ message: "dopo", sessionId })).status, 200);
  });
});

describe("POST /api/chat — timeout (504)", () => {
  test("oltre il tempo massimo → 504 TIMEOUT; la sessione resta occupata finché il lavoro non finisce; il turno scaduto non entra nella history", async () => {
    const app = await startTestApp({ chatTimeoutMs: 50 });
    const { sessionId } = await (await app.post({ message: "seed" })).json();

    // Un orchestratore che ignora il segnale e finisce solo quando lo decide il test.
    const gate = deferred();
    app.setOrchestrator(() => gate.promise.then(() => OK_RESULT));
    await expectError(
      await app.post({ message: "troppo lenta", sessionId }),
      504,
      "TIMEOUT",
    );

    // Il lavoro non è finito: la stessa sessione resta occupata.
    await expectError(
      await app.post({ message: "subito dopo", sessionId }),
      409,
      "SESSION_BUSY",
    );

    // A lavoro concluso il lucchetto si libera.
    gate.resolve();
    app.setOrchestrator(async () => OK_RESULT);
    let status;
    for (let i = 0; i < 100; i++) {
      const res = await app.post({ message: "terza", sessionId });
      status = res.status;
      if (status === 200) break;
      await sleep(10);
    }
    assert.equal(
      status,
      200,
      "la sessione deve liberarsi quando il lavoro termina",
    );

    const history = app.runOrchestrator.mock.calls.at(-1).arguments[0].history;
    assert.deepEqual(
      history.map((m) => m.content),
      ["seed", OK_RESULT.reply],
    );
  });

  test("un orchestratore che rispetta il segnale (come quello vero) → 504 e sessione libera subito", async () => {
    const app = await startTestApp({ chatTimeoutMs: 50 });
    const { sessionId } = await (await app.post({ message: "seed" })).json();

    app.setOrchestrator(
      ({ signal }) =>
        new Promise((_, reject) => {
          signal.addEventListener(
            "abort",
            () => reject(signal.reason ?? new Error("interrotta")),
            { once: true },
          );
        }),
    );
    await expectError(
      await app.post({ message: "lenta", sessionId }),
      504,
      "TIMEOUT",
    );

    app.setOrchestrator(async () => OK_RESULT);
    let status;
    for (let i = 0; i < 100; i++) {
      status = (await app.post({ message: "dopo", sessionId })).status;
      if (status === 200) break;
      await sleep(10);
    }
    assert.equal(status, 200);
  });
});

describe("limite di frequenza (429)", () => {
  const config = (overrides) => ({
    windowMin: 15,
    perIp: 100,
    global: 100,
    ...overrides,
  });
  const ORIGIN = "https://demo.example";

  test("per client: oltre il limite → 429 RATE_LIMITED con Retry-After e intestazioni CORS", async () => {
    const app = await startTestApp({
      rateLimitConfig: config({ perIp: 2 }),
      frontendOrigin: ORIGIN,
    });

    // Le richieste non valide contano comunque: il limite sta prima della validazione.
    assert.equal((await app.post({})).status, 400);
    assert.equal((await app.post({})).status, 400);

    const limited = await app.post({}, { headers: { Origin: ORIGIN } });
    const body = await expectError(limited, 429, "RATE_LIMITED");
    assert.equal(
      body.error.message,
      "Troppe richieste in poco tempo. Riprova tra qualche minuto.",
    );

    const retryAfter = Number(limited.headers.get("retry-after"));
    assert.ok(
      Number.isInteger(retryAfter) && retryAfter > 0 && retryAfter <= 15 * 60,
      `Retry-After = ${retryAfter}`,
    );
    assert.equal(limited.headers.get("access-control-allow-origin"), ORIGIN);
    assert.equal(app.runOrchestrator.mock.callCount(), 0);
  });

  test("globale: oltre il limite totale → 429 RATE_LIMITED", async () => {
    const app = await startTestApp({ rateLimitConfig: config({ global: 2 }) });
    assert.equal((await app.post({})).status, 400);
    assert.equal((await app.post({})).status, 400);
    await expectError(await app.post({}), 429, "RATE_LIMITED");
  });

  test("GET / , GET /charts/... e i preflight CORS non contano per il limite", async () => {
    const app = await startTestApp({
      rateLimitConfig: config({ perIp: 2 }),
      frontendOrigin: ORIGIN,
    });

    for (let i = 0; i < 5; i++) {
      assert.equal((await app.get("/")).status, 200);
      assert.equal((await app.get("/charts/chart_ab12cd34.png")).status, 404);
      const preflight = await app.send("OPTIONS", "/api/chat", {
        headers: { Origin: ORIGIN, "Access-Control-Request-Method": "POST" },
      });
      assert.equal(preflight.status, 204);
    }

    assert.equal((await app.post({})).status, 400);
    assert.equal((await app.post({})).status, 400);
    await expectError(await app.post({}), 429, "RATE_LIMITED");
  });

  test("senza configurazione il limite è spento", async () => {
    const app = await startTestApp();
    for (let i = 0; i < 25; i++) {
      assert.equal((await app.post({})).status, 400);
    }
  });
});

describe("CORS", () => {
  test("origine predefinita: il server di sviluppo del front end", async () => {
    const app = await startTestApp();
    const res = await app.get("/", { Origin: "http://localhost:5173" });
    assert.equal(
      res.headers.get("access-control-allow-origin"),
      "http://localhost:5173",
    );
  });

  test("origine configurata: quella indicata", async () => {
    const app = await startTestApp({ frontendOrigin: "https://demo.example" });
    const res = await app.get("/", { Origin: "https://demo.example" });
    assert.equal(
      res.headers.get("access-control-allow-origin"),
      "https://demo.example",
    );
  });
});
