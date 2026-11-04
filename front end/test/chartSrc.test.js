import { describe, expect, it } from "vitest";
import { chartSrc } from "../src/api/chatApi";

describe("chartSrc", () => {
  it("accetta il formato del contratto e antepone l'URL del back end", () => {
    expect(chartSrc("/charts/chart_ab12cd34.png")).toBe(
      "http://api.test/charts/chart_ab12cd34.png",
    );
  });

  it.each([
    ["maiuscole nell'esadecimale", "/charts/chart_AB12CD34.png"],
    ["7 cifre", "/charts/chart_ab12cd3.png"],
    ["9 cifre", "/charts/chart_ab12cd345.png"],
    ["cifre non esadecimali", "/charts/chart_ab12cd3g.png"],
    ["altra estensione", "/charts/chart_ab12cd34.jpg"],
    ["path traversal", "/charts/../charts/chart_ab12cd34.png"],
    ["cartella diversa", "/other/chart_ab12cd34.png"],
    ["senza slash iniziale", "charts/chart_ab12cd34.png"],
    ["URL assoluto", "http://evil.test/charts/chart_ab12cd34.png"],
    ["URL senza schema", "//evil.test/charts/chart_ab12cd34.png"],
    ["query string", "/charts/chart_ab12cd34.png?x=1"],
    ["frammento", "/charts/chart_ab12cd34.png#x"],
    ["a capo finale", "/charts/chart_ab12cd34.png\n"],
    ["stringa vuota", ""],
  ])("rifiuta: %s", (_nome, valore) => {
    expect(chartSrc(valore)).toBeNull();
  });

  it.each([
    ["null", null],
    ["undefined", undefined],
    ["numero", 42],
    ["oggetto", {}],
  ])("rifiuta un valore che non è una stringa: %s", (_nome, valore) => {
    expect(chartSrc(valore)).toBeNull();
  });
});
