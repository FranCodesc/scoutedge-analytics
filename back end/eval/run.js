/**
 * Valutazione automatica con il modello reale, attraverso POST /api/chat.
 *
 * Per ogni domanda di eval/domande.json manda i turni N volte (una sessione nuova
 * a ogni ripetizione), valuta valori e strumenti con eval/lib.js e salva i risultati
 * in eval/risultati/ (JSON con tutte le risposte + riepilogo in Markdown).
 *
 * NON fa parte di `npm test` e non gira in CI: chiama il modello e costa.
 * Senza --conferma stampa solo il piano e la stima del costo.
 *
 * Prerequisiti: Chroma, data agent e back end avviati (come per `npm run test:api`).
 *
 * Uso (da "back end/"):
 *   npm run eval                          piano e costo stimato, nessuna chiamata
 *   npm run eval -- --conferma            corsa con N = 5
 *   npm run eval -- --conferma --n=3      3 ripetizioni
 *   npm run eval -- --conferma --solo=saluto,fuori_ambito
 *   BASE_URL=http://localhost:3001 npm run eval -- --conferma
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { evaluateTurn, summarize, renderMarkdown } from "./lib.js";

const BASE_URL = (process.env.BASE_URL ?? "http://localhost:3001").replace(
  /\/$/,
  "",
);
const REQUEST_TIMEOUT_MS = 150_000;
const MODELLO = "gpt-4o-mini";

/**
 * Costo stimato per turno, in dollari. Prezzi di gpt-4o-mini: 0,15 $ per milione di
 * token in ingresso, 0,60 $ in uscita. Ipotesi sui token per turno:
 *   nessuno strumento  ~2,5k in,  ~0,15k out
 *   solo manuale       ~5k in,    ~0,4k out
 *   solo dati          ~25k in,   ~1,1k out (l'agente dei dati fa più passaggi)
 *   entrambi           somma dei due
 * Sono ipotesi, non misure: il costo vero si legge dalla dashboard del fornitore.
 */
const COSTO_TURNO = {
  nessuno: 0.0005,
  manuale: 0.001,
  dati: 0.0045,
  entrambi: 0.0055,
};
const MARGINE_PRUDENZIALE = 3;

const args = process.argv.slice(2);
const option = (name) =>
  args.find((a) => a.startsWith(`--${name}=`))?.split("=")[1];
const N = Number(option("n") ?? process.env.EVAL_N ?? 5);
const solo = option("solo")?.split(",");
const confermato = args.includes("--conferma");

if (!Number.isInteger(N) || N < 1) {
  console.error("N deve essere un intero positivo (--n=5).");
  process.exit(1);
}

const file = JSON.parse(
  readFileSync(new URL("./domande.json", import.meta.url), "utf8"),
);
const domande = solo
  ? file.domande.filter((q) => solo.includes(q.id))
  : file.domande;
if (domande.length === 0) {
  console.error(
    `Nessuna domanda selezionata. Id disponibili: ${file.domande.map((q) => q.id).join(", ")}`,
  );
  process.exit(1);
}

function tipoTurno(strumenti) {
  const manuale = strumenti.includes("search_handbook");
  const dati = strumenti.includes("analyze_data");
  if (manuale && dati) return "entrambi";
  if (dati) return "dati";
  if (manuale) return "manuale";
  return "nessuno";
}

const turniPerRipetizione = domande.reduce(
  (somma, q) => somma + q.turni.length,
  0,
);
const richieste = turniPerRipetizione * N;
const costoStimato =
  N *
  domande
    .flatMap((q) => q.turni)
    .reduce(
      (somma, t) => somma + COSTO_TURNO[tipoTurno(t.attese.strumenti)],
      0,
    );

console.log(`Valutazione su ${BASE_URL}`);
console.log(
  `  domande: ${domande.length}, turni per ripetizione: ${turniPerRipetizione}, ripetizioni: ${N}`,
);
console.log(`  richieste a /api/chat: ${richieste}`);
console.log(
  `  costo stimato (${MODELLO}): circa ${costoStimato.toFixed(2)} $, ` +
    `massimo prudenziale ${(costoStimato * MARGINE_PRUDENZIALE).toFixed(2)} $`,
);

if (!confermato) {
  console.log(
    "\nNessuna richiesta fatta. Per lanciare la corsa: npm run eval -- --conferma",
  );
  process.exit(0);
}

console.log(
  "\nAnnota ora il consumo del giorno nella dashboard del fornitore: serve per ricavare il costo reale.",
);

try {
  const health = await fetch(`${BASE_URL}/`, {
    signal: AbortSignal.timeout(5000),
  });
  if (!health.ok) throw new Error(`stato ${health.status}`);
} catch (error) {
  console.error(
    `Il back end non risponde su ${BASE_URL} (${error.message}). Avvia i servizi e riprova.`,
  );
  process.exit(1);
}

/** Una richiesta a /api/chat. Non lancia mai: un fallimento diventa { errore }. */
async function chiedi(message, sessionId) {
  const startedAt = Date.now();
  try {
    const res = await fetch(`${BASE_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, sessionId }),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    const body = await res.json().catch(() => null);
    const durationMs = Date.now() - startedAt;
    if (!res.ok)
      return {
        durationMs,
        errore: `HTTP ${res.status} ${body?.error?.code ?? ""}`.trim(),
      };
    return { durationMs, body };
  } catch (error) {
    const errore =
      error.name === "TimeoutError"
        ? "timeout dello script"
        : `rete: ${error.message}`;
    return { durationMs: Date.now() - startedAt, errore };
  }
}

const inizio = Date.now();
const records = [];

for (let ripetizione = 1; ripetizione <= N; ripetizione++) {
  for (const q of domande) {
    let sessionId; // sessione nuova a ogni ripetizione
    let conversazioneInterrotta = false;

    for (const [i, turno] of q.turni.entries()) {
      const base = {
        domanda: q.id,
        turno: i + 1,
        ripetizione,
        messaggio: turno.messaggio,
        strumentiAttesi: turno.attese.strumenti,
      };
      let record;

      if (conversazioneInterrotta) {
        record = {
          ...base,
          valuesOk: false,
          toolsOk: false,
          durationMs: 0,
          errore: "turno precedente non riuscito",
        };
      } else {
        const r = await chiedi(turno.messaggio, sessionId);
        if (r.errore) {
          conversazioneInterrotta = true;
          record = {
            ...base,
            valuesOk: false,
            toolsOk: false,
            durationMs: r.durationMs,
            errore: r.errore,
          };
        } else {
          sessionId = r.body.sessionId;
          const risposta = {
            reply: r.body.reply,
            chartUrl: r.body.chartUrl,
            toolsUsed: r.body.toolsUsed,
          };
          record = {
            ...base,
            ...evaluateTurn(risposta, turno.attese),
            durationMs: r.durationMs,
            reply: risposta.reply,
            chartUrl: risposta.chartUrl,
            strumentiUsati: risposta.toolsUsed,
            sources: r.body.sources,
          };
        }
      }

      records.push(record);
      const esito = record.errore
        ? `ERRORE (${record.errore})`
        : `valori ${record.valuesOk ? "OK" : "KO"}  strumenti ${record.toolsOk ? "OK" : "KO"}  ${(record.durationMs / 1000).toFixed(1)} s`;
      console.log(
        `[${records.length}/${richieste}] ${q.id}#${i + 1} rip ${ripetizione}  ${esito}`,
      );
    }
  }
}

// Riepilogo e salvataggio. Il JSON si scrive per primo: i dati non si perdono
// nemmeno se la formattazione del Markdown dovesse fallire.
const adesso = new Date();
const result = {
  data: adesso.toISOString().slice(0, 10),
  modello: MODELLO,
  baseUrl: BASE_URL,
  n: N,
  durataTotaleS: Math.round((Date.now() - inizio) / 1000),
  regola: file.regola,
  riepilogo: summarize(records),
  risposte: records,
};

const stamp = adesso
  .toISOString()
  .slice(0, 16)
  .replace(/[-:]/g, "")
  .replace("T", "-");
const cartella = fileURLToPath(new URL("./risultati/", import.meta.url));
mkdirSync(cartella, { recursive: true });
const jsonPath = `${cartella}corsa-${stamp}.json`;
const mdPath = `${cartella}corsa-${stamp}.md`;
writeFileSync(jsonPath, `${JSON.stringify(result, null, 2)}\n`);
try {
  writeFileSync(mdPath, renderMarkdown(result));
} catch (error) {
  console.error(
    `Riepilogo Markdown non scritto (${error.message}): i dati sono nel JSON.`,
  );
}

const t = result.riepilogo.totale;
console.log(`\nValori corretti:    ${t.valuesPct}% (${t.valuesOk}/${t.n})`);
console.log(`Strumenti corretti: ${t.toolsPct}% (${t.toolsOk}/${t.n})`);
console.log(
  `Tempo medio ${(t.timeMeanMs / 1000).toFixed(1)} s, massimo ${(t.timeMaxMs / 1000).toFixed(1)} s, durata totale ${result.durataTotaleS} s`,
);
console.log(`Risultati: ${jsonPath}\n           ${mdPath}`);
console.log(
  "Costo reale: leggi di nuovo il consumo nella dashboard del fornitore e sottrai quello annotato prima.",
);
