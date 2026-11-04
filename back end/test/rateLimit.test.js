import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadRateLimitConfig, readTrustProxy } from "../src/http/rateLimit.js";

const valid = {
  RATE_LIMIT_WINDOW_MIN: "15",
  RATE_LIMIT_PER_IP: "20",
  RATE_LIMIT_GLOBAL: "100",
};

describe("loadRateLimitConfig", () => {
  test("nessuna variabile → limite disattivato (null)", () => {
    assert.equal(loadRateLimitConfig({}), null);
  });

  test("variabili vuote o di soli spazi valgono come assenti", () => {
    const env = {
      RATE_LIMIT_WINDOW_MIN: "",
      RATE_LIMIT_PER_IP: "  ",
      RATE_LIMIT_GLOBAL: "",
    };
    assert.equal(loadRateLimitConfig(env), null);
  });

  test("tutte e tre valide → configurazione con numeri (i valori della demo)", () => {
    assert.deepEqual(loadRateLimitConfig(valid), {
      windowMin: 15,
      perIp: 20,
      global: 100,
    });
  });

  test("gli spazi attorno ai valori sono ignorati", () => {
    const env = { ...valid, RATE_LIMIT_PER_IP: " 20 " };
    assert.equal(loadRateLimitConfig(env).perIp, 20);
  });

  test("le altre variabili dell'ambiente non contano", () => {
    assert.equal(
      loadRateLimitConfig({ PORT: "3001", OPENAI_API_KEY: "x" }),
      null,
    );
  });

  for (const missing of Object.keys(valid)) {
    test(`configurazione parziale: manca ${missing} → errore che la nomina`, () => {
      const env = { ...valid };
      delete env[missing];
      assert.throws(
        () => loadRateLimitConfig(env),
        (err) => {
          assert.match(err.message, /solo in parte/);
          assert.ok(err.message.includes(missing));
          return true;
        },
      );
    });
  }

  test("una sola variabile presente → errore (mancano le altre due)", () => {
    assert.throws(
      () => loadRateLimitConfig({ RATE_LIMIT_PER_IP: "20" }),
      /RATE_LIMIT_WINDOW_MIN, RATE_LIMIT_GLOBAL/,
    );
  });

  for (const bad of [
    "0",
    "-1",
    "abc",
    "3abc",
    "1e3",
    "1.5",
    "01",
    "99999999999999999999",
  ]) {
    test(`valore non valido "${bad}" → errore che nomina la variabile`, () => {
      assert.throws(
        () => loadRateLimitConfig({ ...valid, RATE_LIMIT_PER_IP: bad }),
        /RATE_LIMIT_PER_IP deve essere un intero positivo/,
      );
    });
  }

  test("finestra: 1440 minuti (24 ore) è il massimo ammesso", () => {
    const ok = loadRateLimitConfig({ ...valid, RATE_LIMIT_WINDOW_MIN: "1440" });
    assert.equal(ok.windowMin, 1440);
    assert.throws(
      () => loadRateLimitConfig({ ...valid, RATE_LIMIT_WINDOW_MIN: "1441" }),
      /non può superare 1440/,
    );
  });

  test("anche il limite globale e quello della finestra sono validati", () => {
    assert.throws(
      () => loadRateLimitConfig({ ...valid, RATE_LIMIT_GLOBAL: "0" }),
      /RATE_LIMIT_GLOBAL/,
    );
    assert.throws(
      () => loadRateLimitConfig({ ...valid, RATE_LIMIT_WINDOW_MIN: "x" }),
      /RATE_LIMIT_WINDOW_MIN/,
    );
  });
});

describe("readTrustProxy", () => {
  test("assente o vuota → undefined (nessuna fiducia nelle intestazioni)", () => {
    assert.equal(readTrustProxy({}), undefined);
    assert.equal(readTrustProxy({ TRUST_PROXY: "" }), undefined);
    assert.equal(readTrustProxy({ TRUST_PROXY: "   " }), undefined);
  });

  test("interi ≥ 0 → numero (0 è ammesso, 2 è il valore della demo)", () => {
    assert.equal(readTrustProxy({ TRUST_PROXY: "0" }), 0);
    assert.equal(readTrustProxy({ TRUST_PROXY: "2" }), 2);
    assert.equal(readTrustProxy({ TRUST_PROXY: " 1 " }), 1);
  });

  for (const bad of ["-1", "abc", "1.5", "1e2", "true", "2 proxy"]) {
    test(`valore non valido "${bad}" → errore che nomina TRUST_PROXY`, () => {
      assert.throws(
        () => readTrustProxy({ TRUST_PROXY: bad }),
        /TRUST_PROXY deve essere un intero/,
      );
    });
  }
});
