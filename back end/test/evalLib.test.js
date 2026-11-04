import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  numberForms,
  containsNumber,
  containsText,
  evaluateTurn,
  summarize,
  median,
  renderMarkdown,
} from "../eval/lib.js";

describe("numberForms", () => {
  test("intero piccolo: una sola forma", () => {
    assert.deepEqual(numberForms("130"), ["130"]);
  });

  test("intero grande: con e senza separatori delle migliaia", () => {
    const forms = numberForms("18680000");
    for (const form of ["18680000", "18.680.000", "18,680,000", "18 680 000"]) {
      assert.ok(forms.includes(form), form);
    }
  });

  test("decimali: punto e virgola", () => {
    assert.deepEqual(numberForms("65.11").sort(), ["65,11", "65.11"]);
  });

  test("decimali tutti zero: vale anche l'intero", () => {
    assert.ok(numberForms("72.0").includes("72"));
    assert.ok(numberForms("72.0").includes("72,0"));
  });

  test("valore atteso scritto male → errore", () => {
    assert.throws(() => numberForms("65,11"), /non valido/);
    assert.throws(() => numberForms("abc"), /non valido/);
  });
});

describe("containsNumber", () => {
  const yes = [
    ["18.680.000 € (Sato Jun)", "18680000"],
    ["valore di 18,680,000 €", "18680000"],
    ["valore di 18680000", "18680000"],
    ["media 65.11 su 405 osservazioni", "65.11"],
    ["media 65,11 su 405 osservazioni", "65.11"],
    ["**65.11**", "65.11"],
    ["La media è 65.11.", "65.11"],
    ["duels_won_pct 72.0%", "72.0"],
    ["duels_won_pct 72%", "72.0"],
    ["giocatore 120 (Pereira)", "120"],
    ["130 giocatori", "130"],
    ["su 405 osservazioni", "405"],
  ];
  for (const [text, spec] of yes) {
    test(`"${text}" contiene ${spec}`, () => {
      assert.equal(containsNumber(text, spec), true);
    });
  }

  const no = [
    ["media 65.21", "65.11"],
    ["media 68.29 su 14", "68.91"],
    ["media 65.119", "65.11"],
    ["media 165.11", "65.11"],
    ["media 65.1", "65.11"],
    ["vale 72.5", "72.0"],
    ["vale 172", "72.0"],
    ["1300 giocatori", "130"],
    ["il giocatore 1200", "120"],
    ["media 65.11", "6"],
    ["7.156.158 €", "6887985"],
  ];
  for (const [text, spec] of no) {
    test(`"${text}" NON contiene ${spec}`, () => {
      assert.equal(containsNumber(text, spec), false);
    });
  }
});

describe("containsText", () => {
  test("espressione regolare, senza distinguere le maiuscole", () => {
    assert.equal(containsText("Il TEAM LEAD interviene", "Team Lead"), true);
    assert.equal(
      containsText("entro 2 ore lavorative", "\\b2\\s+ore\\b"),
      true,
    );
    assert.equal(containsText("entro 12 ore", "\\b2\\s+ore\\b"), false);
  });
});

describe("evaluateTurn", () => {
  const response = {
    reply: "La media 2025/26 è 65.11 su 405 osservazioni.",
    chartUrl: null,
    toolsUsed: ["analyze_data"],
  };
  const expectation = {
    numeri: ["65.11", "405"],
    vietati: ["65.21"],
    strumenti: ["analyze_data"],
  };

  test("risposta corretta: valori e strumenti ok", () => {
    const result = evaluateTurn(response, expectation);
    assert.equal(result.valuesOk, true);
    assert.equal(result.toolsOk, true);
    assert.deepEqual(result.missing, []);
  });

  test("valore mancante → valori non ok, e dice quale", () => {
    const result = evaluateTurn(
      { ...response, reply: "La media è 65.11." },
      expectation,
    );
    assert.equal(result.valuesOk, false);
    assert.deepEqual(result.missing, ["405"]);
  });

  test("valore vietato presente → valori non ok, anche se quelli giusti ci sono", () => {
    const result = evaluateTurn(
      { ...response, reply: `${response.reply} Lo stato attuale è 65.21.` },
      expectation,
    );
    assert.equal(result.valuesOk, false);
    assert.deepEqual(result.forbiddenFound, ["65.21"]);
  });

  test("testo atteso mancante → valori non ok", () => {
    const result = evaluateTurn(
      {
        reply: "Risponde il supporto.",
        chartUrl: null,
        toolsUsed: ["search_handbook"],
      },
      { testi: ["Team Lead"], strumenti: ["search_handbook"] },
    );
    assert.equal(result.valuesOk, false);
    assert.deepEqual(result.missing, ["Team Lead"]);
  });

  test("grafico atteso: serve un chartUrl non nullo", () => {
    const withChart = { ...expectation, grafico: true };
    assert.equal(evaluateTurn(response, withChart).valuesOk, false);
    assert.equal(evaluateTurn(response, withChart).chartOk, false);
    const ok = evaluateTurn(
      { ...response, chartUrl: "/charts/chart_ab12cd34.png" },
      withChart,
    );
    assert.equal(ok.valuesOk, true);
  });

  test("grafico non atteso: un chartUrl non penalizza", () => {
    const result = evaluateTurn(
      { ...response, chartUrl: "/charts/chart_ab12cd34.png" },
      expectation,
    );
    assert.equal(result.valuesOk, true);
  });

  test("strumenti: l'ordine non conta", () => {
    const result = evaluateTurn(
      { ...response, toolsUsed: ["analyze_data", "search_handbook"] },
      { ...expectation, strumenti: ["search_handbook", "analyze_data"] },
    );
    assert.equal(result.toolsOk, true);
  });

  test("strumenti: uno in più o uno in meno → non ok", () => {
    assert.equal(
      evaluateTurn(
        { ...response, toolsUsed: ["analyze_data", "search_handbook"] },
        expectation,
      ).toolsOk,
      false,
    );
    assert.equal(
      evaluateTurn({ ...response, toolsUsed: [] }, expectation).toolsOk,
      false,
    );
  });

  test("nessuno strumento atteso (fuori ambito, saluto)", () => {
    const none = { strumenti: [] };
    assert.equal(
      evaluateTurn({ reply: "Ciao!", chartUrl: null, toolsUsed: [] }, none)
        .toolsOk,
      true,
    );
    assert.equal(
      evaluateTurn(
        { reply: "Ciao!", chartUrl: null, toolsUsed: ["search_handbook"] },
        none,
      ).toolsOk,
      false,
    );
  });

  test("valori e strumenti sono giudicati separatamente", () => {
    const result = evaluateTurn(
      { ...response, reply: "Non so.", toolsUsed: ["analyze_data"] },
      expectation,
    );
    assert.equal(result.valuesOk, false);
    assert.equal(result.toolsOk, true);
  });
});

describe("summarize", () => {
  const rec = (domanda, turno, valuesOk, toolsOk, durationMs, errore) => ({
    domanda,
    turno,
    valuesOk,
    toolsOk,
    durationMs,
    ...(errore ? { errore } : {}),
  });

  test("accuratezza di valori e strumenti separate, per turno e in totale", () => {
    const records = [
      rec("a", 1, true, true, 1000),
      rec("a", 1, true, false, 2000),
      rec("a", 1, false, true, 3000),
      rec("a", 1, true, true, 4000),
      rec("b", 1, true, true, 500),
    ];
    const { perTurno, totale } = summarize(records);

    assert.equal(perTurno["a#1"].n, 4);
    assert.equal(perTurno["a#1"].valuesPct, 75);
    assert.equal(perTurno["a#1"].toolsPct, 75);
    assert.equal(perTurno["b#1"].valuesPct, 100);
    assert.equal(totale.n, 5);
    assert.equal(totale.valuesPct, 80);
    assert.equal(totale.toolsPct, 80);
  });

  test("tempi: media, mediana e massimo", () => {
    const records = [
      rec("a", 1, true, true, 1000),
      rec("a", 1, true, true, 2000),
      rec("a", 1, true, true, 6000),
    ];
    const { totale } = summarize(records);
    assert.equal(totale.timeMeanMs, 3000);
    assert.equal(totale.timeMedianMs, 2000);
    assert.equal(totale.timeMaxMs, 6000);
  });

  test("turni della stessa domanda restano separati", () => {
    const { perTurno } = summarize([
      rec("c", 1, true, true, 1),
      rec("c", 2, false, true, 1),
    ]);
    assert.equal(perTurno["c#1"].valuesPct, 100);
    assert.equal(perTurno["c#2"].valuesPct, 0);
  });

  test("una richiesta fallita conta come sbagliata, si conta tra gli errori e non entra nei tempi", () => {
    const { totale } = summarize([
      rec("a", 1, true, true, 1000),
      rec("a", 1, false, false, 9999, "timeout"),
    ]);
    assert.equal(totale.valuesPct, 50);
    assert.equal(totale.toolsPct, 50);
    assert.equal(totale.errors, 1);
    assert.equal(totale.timeMaxMs, 1000);
  });

  test("nessun record: tutto a zero, senza errori di divisione", () => {
    const { totale } = summarize([]);
    assert.equal(totale.n, 0);
    assert.equal(totale.valuesPct, 0);
    assert.equal(totale.timeMeanMs, 0);
  });

  test("median: dispari, pari e vuoto", () => {
    assert.equal(median([3, 1, 2]), 2);
    assert.equal(median([4, 1, 2, 3]), 2.5);
    assert.equal(median([]), 0);
  });
});

describe("renderMarkdown", () => {
  const base = { data: "2026-11-04", modello: "gpt-4o-mini", n: 2, regola: "Regola di prova." };
  const rec = (over) => ({
    domanda: "a", turno: 1, ripetizione: 1, valuesOk: true, toolsOk: true, durationMs: 2000,
    missing: [], forbiddenFound: [], chartOk: true, strumentiAttesi: ["analyze_data"], strumentiUsati: ["analyze_data"],
    ...over,
  });

  test("tabella con una riga per turno e il totale; nessun errore", () => {
    const risposte = [rec({ ripetizione: 1 }), rec({ ripetizione: 2 })];
    const md = renderMarkdown({ ...base, riepilogo: summarize(risposte), risposte });

    assert.match(md, /^# Valutazione automatica del 2026-11-04/);
    assert.match(md, /Regola di prova\./);
    assert.match(md, /\| a \| 1 \| 100% \(2\/2\) \| 100% \(2\/2\) \| 2\.0 s \| 2\.0 s \| 2\.0 s \|/);
    assert.match(md, /\| \*\*Totale\*\* \|/);
    assert.match(md, /Nessuna risposta sbagliata\./);
    assert.ok(md.endsWith("\n"));
  });

  test("le risposte sbagliate sono elencate con il motivo", () => {
    const risposte = [
      rec({ ripetizione: 1 }),
      rec({ ripetizione: 2, valuesOk: false, missing: ["405"], forbiddenFound: ["65.21"], toolsOk: false, strumentiUsati: [] }),
    ];
    const md = renderMarkdown({ ...base, riepilogo: summarize(risposte), risposte });

    assert.match(md, /50% \(1\/2\)/);
    assert.match(md, /`a` turno 1, ripetizione 2: mancano: 405; valori vietati presenti: 65\.21; strumenti usati \[\] invece di \[analyze_data\]/);
    assert.doesNotMatch(md, /Nessuna risposta sbagliata/);
  });

  test("una richiesta non riuscita compare tra gli errori e nell'elenco", () => {
    const risposte = [rec({ valuesOk: false, toolsOk: false, errore: "timeout" })];
    const md = renderMarkdown({ ...base, riepilogo: summarize(risposte), risposte });

    assert.match(md, /Richieste non riuscite \(contate come sbagliate\): 1\./);
    assert.match(md, /richiesta non riuscita \(timeout\)/);
  });
});
