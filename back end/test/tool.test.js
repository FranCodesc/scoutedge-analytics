import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  filterRelevantPassages,
  MAX_DISTANCE,
  MAX_DISTANCE_GAP,
} from "../src/agent/tools.js";

// Un passaggio finto: per il filtro contano solo distance (e section per i duplicati).
const p = (distance, section = "S") => ({ distance, section });
const distances = (passages) => passages.map((x) => x.distance);

describe("filterRelevantPassages", () => {
  test("le soglie sono quelle del design: 0,60 assoluta e +0,12 dal migliore", () => {
    assert.equal(MAX_DISTANCE, 0.6);
    assert.equal(MAX_DISTANCE_GAP, 0.12);
  });

  test("nessun passaggio → lista vuota", () => {
    assert.deepEqual(filterRelevantPassages([]), []);
  });

  test("tutti sopra la soglia assoluta → lista vuota (domanda fuori ambito)", () => {
    // Distanze misurate per "capitale della Francia": tra 0.893 e 0.938.
    const result = filterRelevantPassages([
      p(0.893),
      p(0.91),
      p(0.925),
      p(0.938),
    ]);
    assert.deepEqual(result, []);
  });

  test("un solo passaggio: tenuto se ≤ 0,60, scartato se oltre", () => {
    assert.equal(filterRelevantPassages([p(0.6)]).length, 1);
    assert.equal(filterRelevantPassages([p(0.601)]).length, 0);
  });

  test("tutti pertinenti e vicini → restano tutti", () => {
    const input = [p(0.3), p(0.35), p(0.4), p(0.41)];
    assert.deepEqual(
      distances(filterRelevantPassages(input)),
      [0.3, 0.35, 0.4, 0.41],
    );
  });

  test("lo scarto dal migliore taglia i passaggi sotto soglia ma lontani (SLA priorità alta)", () => {
    // Distanze misurate in docs/TEST.md: 0.364 · 0.550 · 0.627 · 0.692.
    // 0.550 è sotto 0,60 ma oltre 0.364 + 0.12: resta solo il migliore.
    const result = filterRelevantPassages([
      p(0.364),
      p(0.55),
      p(0.627),
      p(0.692),
    ]);
    assert.deepEqual(distances(result), [0.364]);
  });

  test("scout_rating: tre passaggi su quattro (0.451 è oltre il gap)", () => {
    const result = filterRelevantPassages([
      p(0.293),
      p(0.336),
      p(0.388),
      p(0.451),
    ]);
    assert.deepEqual(distances(result), [0.293, 0.336, 0.388]);
  });

  test("privacy: restano i primi due; 0.663 e 0.665 superano la soglia assoluta", () => {
    const result = filterRelevantPassages([
      p(0.491),
      p(0.584),
      p(0.663),
      p(0.665),
    ]);
    assert.deepEqual(distances(result), [0.491, 0.584]);
  });

  test("pari merito: due passaggi alla stessa distanza restano entrambi", () => {
    const result = filterRelevantPassages([p(0.4), p(0.4), p(0.7)]);
    assert.deepEqual(distances(result), [0.4, 0.4]);
  });

  test("il migliore si calcola con il minimo, senza fidarsi dell'ordine; l'ordine in uscita è quello in ingresso", () => {
    const result = filterRelevantPassages([p(0.5), p(0.3), p(0.38)]);
    // best = 0.3 → soglia 0.42: 0.5 scartato; 0.3 e 0.38 restano nell'ordine ricevuto.
    assert.deepEqual(distances(result), [0.3, 0.38]);
  });

  test("non modifica la lista ricevuta", () => {
    const input = [p(0.3), p(0.9)];
    const copy = structuredClone(input);
    filterRelevantPassages(input);
    assert.deepEqual(input, copy);
  });

  test("i passaggi tenuti sono gli stessi oggetti, con le loro sezioni", () => {
    const a = p(0.3, "7. SLA");
    const b = p(0.35, "8. FAQ");
    const result = filterRelevantPassages([a, b, p(0.9, "1. Intro")]);
    assert.deepEqual(
      result.map((x) => x.section),
      ["7. SLA", "8. FAQ"],
    );
    assert.equal(result[0], a);
  });
});
