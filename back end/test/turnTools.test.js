import { test, describe, beforeEach, afterEach, mock } from "node:test";
import assert from "node:assert/strict";
import { createTurnTools, CHART_REQUEST_SENTENCE } from "../src/agent/tools.js";
import { DataAgentError } from "../src/services/dataAgentService.js";

/** Un passaggio del manuale, come lo restituisce ragService. */
const passage = (distance, section, subsection = null) => ({
  id: `${section}-${distance}`,
  text: `testo di ${section}`,
  section,
  subsection,
  distance,
});

/** searchHandbook finto: restituisce sempre gli stessi passaggi. */
function fakeSearch(passages) {
  return mock.fn(async () => ({
    passages,
    sections: [...new Set(passages.map((p) => p.section))],
  }));
}

/** analyzeWithDataAgent finto: una risposta fissa o una sequenza di risposte. */
function fakeAnalyze(...results) {
  let i = 0;
  return mock.fn(async () => {
    const r = results[Math.min(i++, results.length - 1)];
    if (r instanceof Error) throw r;
    return r;
  });
}

beforeEach(() => {
  // runToolCall stampa il routing e gli errori: nei test si silenziano.
  mock.method(console, "log", () => {});
  mock.method(console, "error", () => {});
});
afterEach(() => mock.restoreAll());

describe("search_handbook", () => {
  test("chiama la ricerca con la query e 4 passaggi, e formatta i passaggi pertinenti", async () => {
    const search = fakeSearch([
      passage(0.3, "7. SLA", "7.1 Tempi"),
      passage(0.35, "8. FAQ"),
    ]);
    const { runToolCall } = createTurnTools({ searchHandbook: search });

    const text = await runToolCall({
      name: "search_handbook",
      args: { query: "SLA priorità alta" },
    });

    assert.deepEqual(search.mock.calls[0].arguments, ["SLA priorità alta", 4]);
    assert.match(text, /^Passaggi pertinenti del manuale:/);
    assert.match(text, /\[1\] 7\. SLA › 7\.1 Tempi\ntesto di 7\. SLA/);
    assert.match(text, /\[2\] 8\. FAQ\ntesto di 8\. FAQ/);
  });

  test("sources: solo le sezioni dei passaggi sopra soglia, senza duplicati, in ordine di pertinenza", async () => {
    const search = fakeSearch([
      passage(0.3, "3. Metodologia", "3.1"),
      passage(0.33, "3. Metodologia", "3.4"), // stessa sezione: non si ripete
      passage(0.36, "8. FAQ"),
      passage(0.55, "4. Dati"), // sotto 0,60 ma oltre il gap dal migliore: scartato
    ]);
    const { runToolCall, getCollected } = createTurnTools({
      searchHandbook: search,
    });
    await runToolCall({
      name: "search_handbook",
      args: { query: "scout_rating" },
    });

    assert.deepEqual(getCollected().sources, ["3. Metodologia", "8. FAQ"]);
  });

  test("più ricerche nello stesso turno: le sezioni si uniscono senza duplicati", async () => {
    const first = fakeSearch([passage(0.3, "7. SLA")]);
    const second = fakeSearch([
      passage(0.3, "7. SLA"),
      passage(0.32, "6. Data cleaning"),
    ]);
    let call = 0;
    const search = mock.fn(async (...args) =>
      call++ === 0 ? first(...args) : second(...args),
    );
    const { runToolCall, getCollected } = createTurnTools({
      searchHandbook: search,
    });

    await runToolCall({ name: "search_handbook", args: { query: "uno" } });
    await runToolCall({ name: "search_handbook", args: { query: "due" } });

    assert.deepEqual(getCollected().sources, ["7. SLA", "6. Data cleaning"]);
  });

  test("nessun passaggio pertinente → testo dedicato, sources vuote, ma lo strumento risulta usato", async () => {
    const search = fakeSearch([
      passage(0.9, "1. Intro"),
      passage(0.93, "2. Piani"),
    ]);
    const { runToolCall, getCollected } = createTurnTools({
      searchHandbook: search,
    });

    const text = await runToolCall({
      name: "search_handbook",
      args: { query: "capitale della Francia" },
    });

    assert.equal(
      text,
      "Nessun passaggio pertinente trovato nel manuale per questa ricerca.",
    );
    assert.deepEqual(getCollected().sources, []);
    assert.deepEqual(getCollected().toolsUsed, ["search_handbook"]);
  });

  test("Chroma o embedding in errore → ERRORE_STRUMENTO pulito, nessun dettaglio tecnico, nessuna fonte", async () => {
    const search = mock.fn(async () => {
      throw new Error("connect ECONNREFUSED 127.0.0.1:8001 chiave=sk-segreta");
    });
    const { runToolCall, getCollected } = createTurnTools({
      searchHandbook: search,
    });

    const text = await runToolCall({
      name: "search_handbook",
      args: { query: "SLA" },
    });

    assert.equal(
      text,
      "ERRORE_STRUMENTO: il manuale non è al momento consultabile.",
    );
    assert.doesNotMatch(text, /ECONNREFUSED|sk-segreta|8001/);
    assert.deepEqual(getCollected().toolsUsed, ["search_handbook"]);
    assert.deepEqual(getCollected().sources, []);
  });
});

describe("analyze_data", () => {
  test("chart true: il CODICE aggiunge la frase del grafico alla domanda", async () => {
    const analyze = fakeAnalyze({
      answer: "ok",
      chartUrl: "/charts/chart_ab12cd34.png",
    });
    const { runToolCall } = createTurnTools({ analyzeWithDataAgent: analyze });

    await runToolCall({
      name: "analyze_data",
      args: { question: "  Top 10 per valore.  ", chart: true },
    });

    assert.equal(
      analyze.mock.calls[0].arguments[0],
      `Top 10 per valore. ${CHART_REQUEST_SENTENCE}`,
    );
  });

  test("chart false: la domanda arriva al data agent senza modifiche", async () => {
    const analyze = fakeAnalyze({ answer: "130", chartUrl: null });
    const { runToolCall } = createTurnTools({ analyzeWithDataAgent: analyze });

    await runToolCall({
      name: "analyze_data",
      args: { question: "Quanti giocatori?", chart: false },
    });

    assert.equal(analyze.mock.calls[0].arguments[0], "Quanti giocatori?");
  });

  test("con grafico: il testo per il modello lo dichiara e chartUrl viene raccolto", async () => {
    const analyze = fakeAnalyze({
      answer: "Ecco i dati.",
      chartUrl: "/charts/chart_ab12cd34.png",
    });
    const { runToolCall, getCollected } = createTurnTools({
      analyzeWithDataAgent: analyze,
    });

    const text = await runToolCall({
      name: "analyze_data",
      args: { question: "q", chart: true },
    });

    assert.match(text, /^Risultato dell'analisi:\nEcco i dati\./);
    assert.match(text, /È stato generato un grafico/);
    assert.equal(getCollected().chartUrl, "/charts/chart_ab12cd34.png");
    assert.deepEqual(getCollected().toolsUsed, ["analyze_data"]);
  });

  test("grafico richiesto ma non generato → il testo lo dichiara, chartUrl resta null", async () => {
    const analyze = fakeAnalyze({ answer: "Ecco.", chartUrl: null });
    const { runToolCall, getCollected } = createTurnTools({
      analyzeWithDataAgent: analyze,
    });

    const text = await runToolCall({
      name: "analyze_data",
      args: { question: "q", chart: true },
    });

    assert.match(text, /Il grafico richiesto non è stato generato/);
    assert.equal(getCollected().chartUrl, null);
  });

  test("grafico non richiesto e non generato → nessuna nota sul grafico", async () => {
    const analyze = fakeAnalyze({ answer: "Ecco.", chartUrl: null });
    const { runToolCall } = createTurnTools({ analyzeWithDataAgent: analyze });

    const text = await runToolCall({
      name: "analyze_data",
      args: { question: "q", chart: false },
    });

    assert.equal(text, "Risultato dell'analisi:\nEcco.");
  });

  test("grafico non richiesto ma generato dal servizio → si mostra comunque", async () => {
    const analyze = fakeAnalyze({
      answer: "Ecco.",
      chartUrl: "/charts/chart_00000001.png",
    });
    const { runToolCall, getCollected } = createTurnTools({
      analyzeWithDataAgent: analyze,
    });

    await runToolCall({
      name: "analyze_data",
      args: { question: "q", chart: false },
    });

    assert.equal(getCollected().chartUrl, "/charts/chart_00000001.png");
  });

  test("più chiamate: vale l'ultimo grafico non nullo, uno nullo successivo non lo cancella", async () => {
    const analyze = fakeAnalyze(
      { answer: "a", chartUrl: "/charts/chart_00000001.png" },
      { answer: "b", chartUrl: "/charts/chart_00000002.png" },
      { answer: "c", chartUrl: null },
    );
    const { runToolCall, getCollected } = createTurnTools({
      analyzeWithDataAgent: analyze,
    });

    for (let i = 0; i < 3; i++) {
      await runToolCall({
        name: "analyze_data",
        args: { question: `q${i}`, chart: false },
      });
    }

    assert.equal(getCollected().chartUrl, "/charts/chart_00000002.png");
    assert.deepEqual(
      getCollected().toolsUsed,
      ["analyze_data"],
      "senza duplicati",
    );
  });

  for (const code of ["TIMEOUT", "UNREACHABLE", "UPSTREAM_ERROR"]) {
    test(`DataAgentError ${code} → ERRORE_STRUMENTO con il suo messaggio pulito`, async () => {
      const analyze = fakeAnalyze(
        new DataAgentError(code, "Messaggio pulito del servizio."),
      );
      const { runToolCall, getCollected } = createTurnTools({
        analyzeWithDataAgent: analyze,
      });

      const text = await runToolCall({
        name: "analyze_data",
        args: { question: "q", chart: false },
      });

      assert.equal(text, "ERRORE_STRUMENTO: Messaggio pulito del servizio.");
      assert.deepEqual(
        getCollected().toolsUsed,
        ["analyze_data"],
        "lo strumento tentato è registrato",
      );
      assert.equal(getCollected().chartUrl, null);
    });
  }

  test("un errore qualunque (bug, rete) → messaggio generico, senza dettagli", async () => {
    const analyze = fakeAnalyze(
      new Error("TypeError: x is undefined at /app/secret.js:42"),
    );
    const { runToolCall } = createTurnTools({ analyzeWithDataAgent: analyze });

    const text = await runToolCall({
      name: "analyze_data",
      args: { question: "q", chart: false },
    });

    assert.equal(
      text,
      "ERRORE_STRUMENTO: il servizio di analisi dati non è al momento disponibile.",
    );
    assert.doesNotMatch(text, /secret|TypeError/);
  });
});

describe("runToolCall e stato del turno", () => {
  test("strumento sconosciuto → ERRORE_STRUMENTO e non entra in toolsUsed", async () => {
    const { runToolCall, getCollected } = createTurnTools({});
    const text = await runToolCall({ name: "esegui_codice", args: {} });

    assert.equal(text, "ERRORE_STRUMENTO: strumento non disponibile.");
    assert.deepEqual(getCollected().toolsUsed, []);
  });

  test("argomenti che non rispettano lo schema → ERRORE_STRUMENTO, nessuna eccezione verso l'orchestratore", async () => {
    const analyze = fakeAnalyze({ answer: "a", chartUrl: null });
    const { runToolCall } = createTurnTools({ analyzeWithDataAgent: analyze });

    const text = await runToolCall({
      name: "analyze_data",
      args: { chart: true },
    }); // manca question

    assert.match(text, /^ERRORE_STRUMENTO:/);
    assert.equal(analyze.mock.callCount(), 0, "il servizio non viene chiamato");
  });

  test("toolsUsed: senza duplicati, nell'ordine del primo utilizzo", async () => {
    const { runToolCall, getCollected } = createTurnTools({
      searchHandbook: fakeSearch([passage(0.3, "S")]),
      analyzeWithDataAgent: fakeAnalyze({ answer: "a", chartUrl: null }),
    });

    await runToolCall({ name: "search_handbook", args: { query: "a" } });
    await runToolCall({
      name: "analyze_data",
      args: { question: "q", chart: false },
    });
    await runToolCall({ name: "search_handbook", args: { query: "b" } });

    assert.deepEqual(getCollected().toolsUsed, [
      "search_handbook",
      "analyze_data",
    ]);
  });

  test("due turni (due createTurnTools) non condividono lo stato", async () => {
    const a = createTurnTools({
      analyzeWithDataAgent: fakeAnalyze({
        answer: "x",
        chartUrl: "/charts/chart_00000001.png",
      }),
    });
    const b = createTurnTools({
      analyzeWithDataAgent: fakeAnalyze({ answer: "y", chartUrl: null }),
    });

    await a.runToolCall({
      name: "analyze_data",
      args: { question: "q", chart: false },
    });
    await b.runToolCall({
      name: "analyze_data",
      args: { question: "q", chart: false },
    });

    assert.equal(a.getCollected().chartUrl, "/charts/chart_00000001.png");
    assert.equal(b.getCollected().chartUrl, null);
  });

  test("getCollected restituisce copie: modificarle non cambia lo stato del turno", async () => {
    const { runToolCall, getCollected } = createTurnTools({
      searchHandbook: fakeSearch([passage(0.3, "S")]),
    });
    await runToolCall({ name: "search_handbook", args: { query: "a" } });

    getCollected().toolsUsed.push("intruso");
    getCollected().sources.push("intruso");

    assert.deepEqual(getCollected().toolsUsed, ["search_handbook"]);
    assert.deepEqual(getCollected().sources, ["S"]);
  });

  test("i tool esposti al modello sono search_handbook e analyze_data", () => {
    const { tools } = createTurnTools({});
    assert.deepEqual(
      tools.map((t) => t.name),
      ["search_handbook", "analyze_data"],
    );
  });
});
