import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  createSessionStore,
  MAX_MESSAGES,
  SESSION_TTL_MS,
} from "../src/services/sessionStore.js";

const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MINUTE = 60 * 1000;

/** Store con orologio controllabile: `clock.advance(ms)` fa passare il tempo. */
function makeStore(options = {}) {
  const clock = {
    t: 1_000_000,
    advance(ms) {
      this.t += ms;
    },
  };
  const store = createSessionStore({ now: () => clock.t, ...options });
  return { store, clock };
}

describe("costanti del contratto", () => {
  test("20 messaggi e 30 minuti", () => {
    assert.equal(MAX_MESSAGES, 20);
    assert.equal(SESSION_TTL_MS, 30 * MINUTE);
  });
});

describe("getOrCreateSession", () => {
  test("senza id crea una sessione nuova con UUID v4 e history vuota", () => {
    const { store } = makeStore();
    const s = store.getOrCreateSession();
    assert.equal(s.isNew, true);
    assert.match(s.sessionId, UUID_V4);
    assert.deepEqual(s.history, []);
  });

  test("con un id esistente continua la stessa sessione", () => {
    const { store } = makeStore();
    const first = store.getOrCreateSession();
    const second = store.getOrCreateSession(first.sessionId);
    assert.equal(second.isNew, false);
    assert.equal(second.sessionId, first.sessionId);
  });

  test("con un id sconosciuto crea una sessione nuova con un altro id (non è un errore)", () => {
    const { store } = makeStore();
    const unknown = "3f1c2a9e-7b4d-4e8a-9c1f-2d5e6a7b8c9d";
    const s = store.getOrCreateSession(unknown);
    assert.equal(s.isNew, true);
    assert.notEqual(s.sessionId, unknown);
  });

  test("la history restituita è una copia: modificarla non cambia lo store", () => {
    const { store } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    store.appendTurn(sessionId, "domanda", "risposta");
    const copy = store.getOrCreateSession(sessionId).history;
    copy.push({ role: "user", content: "intruso" });
    assert.equal(store.getOrCreateSession(sessionId).history.length, 2);
  });

  test("due store sono indipendenti", () => {
    const a = makeStore().store;
    const b = makeStore().store;
    const { sessionId } = a.getOrCreateSession();
    assert.equal(b.getOrCreateSession(sessionId).isNew, true);
  });
});

describe("appendTurn e limite di 20 messaggi", () => {
  test("salva la coppia domanda/risposta nell'ordine giusto", () => {
    const { store } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    assert.equal(store.appendTurn(sessionId, "domanda 1", "risposta 1"), true);
    assert.deepEqual(store.getOrCreateSession(sessionId).history, [
      { role: "user", content: "domanda 1" },
      { role: "assistant", content: "risposta 1" },
    ]);
  });

  test("su una sessione inesistente restituisce false e non lancia", () => {
    const { store } = makeStore();
    assert.equal(store.appendTurn("non-esiste", "d", "r"), false);
  });

  test("10 turni = 20 messaggi: nessun taglio", () => {
    const { store } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    for (let i = 1; i <= 10; i++) store.appendTurn(sessionId, `d${i}`, `r${i}`);
    const { history } = store.getOrCreateSession(sessionId);
    assert.equal(history.length, 20);
    assert.equal(history[0].content, "d1");
  });

  test("all'11° turno si perde il più vecchio, a coppie: resta 20 e inizia con l'utente", () => {
    const { store } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    for (let i = 1; i <= 11; i++) store.appendTurn(sessionId, `d${i}`, `r${i}`);
    const { history } = store.getOrCreateSession(sessionId);
    assert.equal(history.length, 20);
    assert.deepEqual(history[0], { role: "user", content: "d2" });
    assert.deepEqual(history.at(-1), { role: "assistant", content: "r11" });
  });

  test("con molti turni resta sempre al massimo 20", () => {
    const { store } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    for (let i = 1; i <= 50; i++) store.appendTurn(sessionId, `d${i}`, `r${i}`);
    const { history } = store.getOrCreateSession(sessionId);
    assert.equal(history.length, 20);
    assert.equal(history[0].role, "user");
  });

  test("il limite si può cambiare con maxMessages", () => {
    const { store } = makeStore({ maxMessages: 4 });
    const { sessionId } = store.getOrCreateSession();
    for (let i = 1; i <= 3; i++) store.appendTurn(sessionId, `d${i}`, `r${i}`);
    assert.deepEqual(
      store.getOrCreateSession(sessionId).history.map((m) => m.content),
      ["d2", "r2", "d3", "r3"],
    );
  });
});

describe("scadenza dopo 30 minuti di inattività", () => {
  test("esattamente a 30 minuti la sessione è ancora valida; un millisecondo dopo no", () => {
    const { store, clock } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    clock.advance(SESSION_TTL_MS);
    assert.equal(store.getOrCreateSession(sessionId).isNew, false);

    clock.advance(SESSION_TTL_MS + 1);
    const expired = store.getOrCreateSession(sessionId);
    assert.equal(expired.isNew, true);
    assert.notEqual(expired.sessionId, sessionId);
    assert.deepEqual(expired.history, []);
  });

  test("una sessione scaduta perde la history", () => {
    const { store, clock } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    store.appendTurn(sessionId, "d", "r");
    clock.advance(31 * MINUTE);
    assert.deepEqual(store.getOrCreateSession(sessionId).history, []);
  });

  test("ogni accesso rinnova la scadenza", () => {
    const { store, clock } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    clock.advance(20 * MINUTE);
    assert.equal(store.getOrCreateSession(sessionId).isNew, false);
    clock.advance(20 * MINUTE); // 40 minuti dalla creazione, 20 dall'ultimo accesso
    assert.equal(store.getOrCreateSession(sessionId).isNew, false);
  });

  test("anche appendTurn rinnova la scadenza", () => {
    const { store, clock } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    clock.advance(25 * MINUTE);
    store.appendTurn(sessionId, "d", "r");
    clock.advance(25 * MINUTE);
    assert.equal(store.getOrCreateSession(sessionId).isNew, false);
  });

  test("il ttl si può cambiare con ttlMs", () => {
    const { store, clock } = makeStore({ ttlMs: 1000 });
    const { sessionId } = store.getOrCreateSession();
    clock.advance(1001);
    assert.equal(store.getOrCreateSession(sessionId).isNew, true);
  });
});

describe("acquire e release (SESSION_BUSY)", () => {
  test("il secondo acquire sulla stessa sessione fallisce finché non c'è release", () => {
    const { store } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    assert.equal(store.acquire(sessionId), true);
    assert.equal(store.acquire(sessionId), false);
    store.release(sessionId);
    assert.equal(store.acquire(sessionId), true);
  });

  test("sessioni diverse non si bloccano a vicenda", () => {
    const { store } = makeStore();
    const a = store.getOrCreateSession().sessionId;
    const b = store.getOrCreateSession().sessionId;
    assert.equal(store.acquire(a), true);
    assert.equal(store.acquire(b), true);
  });

  test("acquire su una sessione inesistente è un errore di programmazione (lancia)", () => {
    const { store } = makeStore();
    assert.throws(() => store.acquire("non-esiste"), /sessione inesistente/);
  });

  test("release su una sessione inesistente non fa nulla", () => {
    const { store } = makeStore();
    assert.doesNotThrow(() => store.release("non-esiste"));
  });
});

describe("cleanupExpiredSessions", () => {
  test("elimina le scadute e restituisce quante; tiene le fresche", () => {
    const { store, clock } = makeStore();
    const old1 = store.getOrCreateSession().sessionId;
    const old2 = store.getOrCreateSession().sessionId;
    clock.advance(31 * MINUTE);
    const fresh = store.getOrCreateSession().sessionId;

    assert.equal(store.cleanupExpiredSessions(), 2);
    assert.equal(store.getOrCreateSession(old1).isNew, true);
    assert.equal(store.getOrCreateSession(old2).isNew, true);
    assert.equal(store.getOrCreateSession(fresh).isNew, false);
  });

  test("salta le sessioni occupate, anche se scadute", () => {
    const { store, clock } = makeStore();
    const { sessionId } = store.getOrCreateSession();
    store.acquire(sessionId);
    clock.advance(31 * MINUTE);
    assert.equal(store.cleanupExpiredSessions(), 0);

    store.release(sessionId);
    assert.equal(store.cleanupExpiredSessions(), 1);
  });

  test("senza sessioni scadute restituisce 0", () => {
    const { store } = makeStore();
    store.getOrCreateSession();
    assert.equal(store.cleanupExpiredSessions(), 0);
  });
});
