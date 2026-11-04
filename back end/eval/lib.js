/**
 * Metro di giudizio della valutazione automatica: funzioni pure, senza rete.
 *
 * I valori attesi sono scritti come stringhe ("65.11", "72.0", "18680000"):
 * una stringa conserva gli zeri finali, un numero no.
 */

const SEPARATORS = [".", ",", " ", "\u00a0", "\u202f"];

/** Inserisce un separatore ogni tre cifre: group("18680000", ".") → "18.680.000". */
function group(digits, separator) {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, separator);
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Tutti i modi in cui lo stesso numero può comparire in una risposta:
 * "18680000" → 18680000, 18.680.000, 18,680,000, 18 680 000…
 * "65.11" → 65.11 e 65,11. Se i decimali sono tutti zeri ("72.0") vale anche "72".
 */
export function numberForms(spec) {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(spec);
  if (!match) throw new Error(`Valore atteso non valido: "${spec}"`);
  const [, integer, decimals] = match;

  const integers = new Set([integer]);
  if (integer.length > 3) {
    for (const separator of SEPARATORS) integers.add(group(integer, separator));
  }
  if (decimals === undefined) return [...integers];

  const forms = [];
  for (const i of integers) {
    for (const decimalSeparator of [".", ","])
      forms.push(`${i}${decimalSeparator}${decimals}`);
  }
  if (/^0+$/.test(decimals)) forms.push(...integers);
  return forms;
}

/**
 * Il numero compare nel testo come numero intero, non come parte di un altro:
 * "65.11" non è in "165.11" né in "65.119", "72" non è in "72.5".
 */
export function containsNumber(text, spec) {
  const alternatives = numberForms(spec).map(escapeRegExp).join("|");
  const pattern = new RegExp(`(?<![\\d.,])(?:${alternatives})(?!\\d|[.,]\\d)`);
  return pattern.test(text);
}

/** Espressione regolare scritta come stringa nel file delle domande, senza distinguere le maiuscole. */
export function containsText(text, pattern) {
  return new RegExp(pattern, "i").test(text);
}

/**
 * Valuta un turno rispetto alle attese.
 *
 * @param {{ reply: string, chartUrl: string|null, toolsUsed: string[] }} response
 * @param {{ numeri?: string[], testi?: string[], vietati?: string[], grafico?: boolean, strumenti: string[] }} expectation
 * @returns {{ valuesOk: boolean, toolsOk: boolean, missing: string[], forbiddenFound: string[], chartOk: boolean }}
 */
export function evaluateTurn(response, expectation) {
  const { reply, chartUrl, toolsUsed } = response;

  const missing = [
    ...(expectation.numeri ?? []).filter((n) => !containsNumber(reply, n)),
    ...(expectation.testi ?? []).filter((t) => !containsText(reply, t)),
  ];
  const forbiddenFound = (expectation.vietati ?? []).filter((n) =>
    containsNumber(reply, n),
  );
  const chartOk = expectation.grafico ? chartUrl != null : true;

  const expectedTools = [...expectation.strumenti].sort();
  const usedTools = [...toolsUsed].sort();
  const toolsOk =
    expectedTools.length === usedTools.length &&
    expectedTools.every((t, i) => t === usedTools[i]);

  return {
    valuesOk: missing.length === 0 && forbiddenFound.length === 0 && chartOk,
    toolsOk,
    missing,
    forbiddenFound,
    chartOk,
  };
}

const percent = (part, total) =>
  total === 0 ? 0 : Math.round((1000 * part) / total) / 10;

export function median(values) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2;
}

function statsOf(records) {
  const n = records.length;
  const valuesOk = records.filter((r) => r.valuesOk).length;
  const toolsOk = records.filter((r) => r.toolsOk).length;
  const errors = records.filter((r) => r.errore).length;
  const times = records.filter((r) => !r.errore).map((r) => r.durationMs);
  return {
    n,
    valuesOk,
    toolsOk,
    errors,
    valuesPct: percent(valuesOk, n),
    toolsPct: percent(toolsOk, n),
    timeMeanMs:
      times.length === 0
        ? 0
        : Math.round(times.reduce((a, b) => a + b, 0) / times.length),
    timeMedianMs: Math.round(median(times)),
    timeMaxMs: times.length === 0 ? 0 : Math.max(...times),
  };
}

/**
 * Riepilogo di una corsa.
 *
 * @param {Array<{ domanda: string, turno: number, valuesOk: boolean, toolsOk: boolean,
 *   durationMs: number, errore?: string }>} records un elemento per ogni risposta ricevuta
 * @returns {{ perTurno: Record<string, object>, totale: object }} chiavi "domanda#turno"
 */
export function summarize(records) {
  const groups = new Map();
  for (const record of records) {
    const key = `${record.domanda}#${record.turno}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }
  return {
    perTurno: Object.fromEntries(
      [...groups].map(([key, group]) => [key, statsOf(group)]),
    ),
    totale: statsOf(records),
  };
}

const cell = (ok, n, pct) => `${pct}% (${ok}/${n})`;
const seconds = (ms) => (ms / 1000).toFixed(1);

/**
 * Riepilogo leggibile di una corsa, da salvare accanto al JSON.
 *
 * @param {{ data: string, modello: string, n: number, regola: string,
 *   riepilogo: ReturnType<typeof summarize>, risposte: object[] }} result
 */
export function renderMarkdown({
  data,
  modello,
  n,
  regola,
  riepilogo,
  risposte,
}) {
  const lines = [];
  lines.push(`# Valutazione automatica del ${data}`, "");
  lines.push(
    `Ripetizioni per domanda: ${n}. Richieste totali: ${risposte.length}. Modello: ${modello}. ` +
      "Il costo della corsa non è misurato dallo script: va letto dalla dashboard del fornitore.",
    "",
  );
  lines.push("## Regola di valutazione", "", regola, "");

  lines.push("## Risultati per domanda", "");
  lines.push(
    "| Domanda | Turno | Valori corretti | Strumenti corretti | Tempo medio | Mediana | Massimo |",
  );
  lines.push("|---|---|---|---|---|---|---|");
  for (const [key, s] of Object.entries(riepilogo.perTurno)) {
    const [domanda, turno] = key.split("#");
    lines.push(
      `| ${domanda} | ${turno} | ${cell(s.valuesOk, s.n, s.valuesPct)} | ${cell(s.toolsOk, s.n, s.toolsPct)} | ` +
        `${seconds(s.timeMeanMs)} s | ${seconds(s.timeMedianMs)} s | ${seconds(s.timeMaxMs)} s |`,
    );
  }
  const t = riepilogo.totale;
  lines.push(
    `| **Totale** | | **${cell(t.valuesOk, t.n, t.valuesPct)}** | **${cell(t.toolsOk, t.n, t.toolsPct)}** | ` +
      `**${seconds(t.timeMeanMs)} s** | **${seconds(t.timeMedianMs)} s** | **${seconds(t.timeMaxMs)} s** |`,
    "",
  );
  if (t.errors > 0) {
    lines.push(
      `Richieste non riuscite (contate come sbagliate): ${t.errors}.`,
      "",
    );
  }

  lines.push("## Risposte sbagliate", "");
  const wrong = risposte.filter((r) => !r.valuesOk || !r.toolsOk);
  if (wrong.length === 0) {
    lines.push("Nessuna risposta sbagliata.");
  } else {
    for (const r of wrong) {
      const problems = [];
      if (r.errore) problems.push(`richiesta non riuscita (${r.errore})`);
      if (r.missing?.length) problems.push(`mancano: ${r.missing.join(", ")}`);
      if (r.forbiddenFound?.length)
        problems.push(
          `valori vietati presenti: ${r.forbiddenFound.join(", ")}`,
        );
      if (r.chartOk === false) problems.push("grafico atteso ma assente");
      if (!r.toolsOk) {
        problems.push(
          `strumenti usati [${(r.strumentiUsati ?? []).join(", ")}] invece di [${(r.strumentiAttesi ?? []).join(", ")}]`,
        );
      }
      lines.push(
        `- \`${r.domanda}\` turno ${r.turno}, ripetizione ${r.ripetizione}: ${problems.join("; ")}`,
      );
    }
  }
  return `${lines.join("\n")}\n`;
}
