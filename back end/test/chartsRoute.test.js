import http from "node:http";
import { test, describe, beforeEach, afterEach, mock } from "node:test";
import assert from "node:assert/strict";
import { DataAgentError } from "../src/services/dataAgentService.js";
import {
  startTestApp,
  closeAllServers,
  silenceConsole,
  expectError,
} from "./helpers/testServer.js";

const PNG = Buffer.from([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x01,
]);
const NAME = "chart_ab12cd34.png";

beforeEach(silenceConsole);
afterEach(async () => {
  mock.restoreAll();
  await closeAllServers();
});

/**
 * GET con il percorso scritto esattamente così, senza che il client lo normalizzi
 * (fetch trasformerebbe "/charts/../../etc/passwd" in "/etc/passwd" prima di inviarlo).
 */
function rawGet(base, path) {
  const { hostname, port } = new URL(base);
  return new Promise((resolve, reject) => {
    http
      .get({ hostname, port, path }, (res) => {
        let data = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () =>
          resolve({ status: res.statusCode, body: JSON.parse(data) }),
        );
      })
      .on("error", reject);
  });
}

describe("GET /", () => {
  test("health check: 200 { status: ok }", async () => {
    const app = await startTestApp();
    const res = await app.get("/");
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { status: "ok" });
  });
});

describe("GET /charts/:filename", () => {
  test("grafico esistente → 200 image/png con nosniff e gli stessi byte", async () => {
    const fetchChart = mock.fn(async () => PNG);
    const app = await startTestApp({ fetchChart });

    const res = await app.get(`/charts/${NAME}`);

    assert.equal(res.status, 200);
    assert.equal(res.headers.get("content-type"), "image/png");
    assert.equal(res.headers.get("x-content-type-options"), "nosniff");
    assert.deepEqual(Buffer.from(await res.arrayBuffer()), PNG);
    assert.deepEqual(fetchChart.mock.calls[0].arguments, [NAME]);
  });

  for (const bad of [
    "chart_XYZ.png",
    "chart_AB12CD34.png",
    "chart_ab12cd34.jpg",
    "..%2F..%2Fetc%2Fpasswd",
  ]) {
    test(`nome non valido "${bad}" → 400 INVALID_REQUEST, senza chiedere nulla al data agent`, async () => {
      const fetchChart = mock.fn(async () => PNG);
      const app = await startTestApp({ fetchChart });

      const body = await expectError(
        await app.get(`/charts/${bad}`),
        400,
        "INVALID_REQUEST",
      );

      assert.equal(body.error.message, "Il nome del grafico non è valido.");
      assert.equal(fetchChart.mock.callCount(), 0);
    });
  }

  test("percorso con ../ non normalizzato → 404 NOT_FOUND: non corrisponde a nessuna rotta e non legge nulla", async () => {
    const fetchChart = mock.fn(async () => PNG);
    const app = await startTestApp({ fetchChart });

    for (const path of [
      "/charts/../../etc/passwd",
      "/charts/%2e%2e/%2e%2e/etc/passwd",
    ]) {
      const { status, body } = await rawGet(app.base, path);
      assert.equal(status, 404, path);
      assert.equal(body.error.code, "NOT_FOUND", path);
    }
    assert.equal(fetchChart.mock.callCount(), 0);
  });

  test("grafico inesistente o cancellato dalla pulizia → 404 NOT_FOUND", async () => {
    const app = await startTestApp({ fetchChart: mock.fn(async () => null) });
    const body = await expectError(
      await app.get(`/charts/${NAME}`),
      404,
      "NOT_FOUND",
    );
    assert.equal(body.error.message, "Grafico non trovato.");
  });

  test("data agent in errore → 500 INTERNAL_ERROR con messaggio pulito, senza dettagli interni", async () => {
    const fetchChart = mock.fn(async () => {
      throw new DataAgentError(
        "UNREACHABLE",
        "dettaglio interno: http://127.0.0.1:8000 rifiutata",
      );
    });
    const app = await startTestApp({ fetchChart });

    const body = await expectError(
      await app.get(`/charts/${NAME}`),
      500,
      "INTERNAL_ERROR",
    );

    assert.equal(
      body.error.message,
      "Il grafico non è al momento disponibile.",
    );
    assert.doesNotMatch(JSON.stringify(body), /127\.0\.0\.1|dettaglio interno/);
  });

  test("solo GET: un POST su /charts/... → 404", async () => {
    const app = await startTestApp();
    await expectError(
      await app.send("POST", `/charts/${NAME}`),
      404,
      "NOT_FOUND",
    );
  });

  test("catena completa: il chartUrl restituito da /api/chat si scarica con GET", async () => {
    const fetchChart = mock.fn(async () => PNG);
    const app = await startTestApp({ fetchChart });
    app.setOrchestrator(async () => ({
      reply: "Ecco il grafico.",
      toolsUsed: ["analyze_data"],
      sources: [],
      chartUrl: `/charts/${NAME}`,
    }));

    const chat = await (
      await app.post({ message: "Mostrami un grafico" })
    ).json();
    const image = await app.get(chat.chartUrl);

    assert.equal(image.status, 200);
    assert.equal(image.headers.get("content-type"), "image/png");
    assert.deepEqual(Buffer.from(await image.arrayBuffer()), PNG);
  });
});
