import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ToolBadges from "../src/components/ToolBadges";

const labels = () =>
  screen.getAllByRole("listitem").map((li) => li.textContent);

describe("ToolBadges", () => {
  it("mostra un'etichetta per ogni sezione citata dell'handbook", () => {
    render(
      <ToolBadges
        toolsUsed={["search_handbook"]}
        sources={[
          { section: "7. SLA e procedura di supporto" },
          { section: "3. Metodologia" },
        ]}
      />,
    );

    expect(labels()).toEqual([
      "📄 Handbook — 7. SLA e procedura di supporto",
      "📄 Handbook — 3. Metodologia",
    ]);
  });

  it("handbook consultato senza sezioni citate: etichetta neutra", () => {
    render(<ToolBadges toolsUsed={["search_handbook"]} sources={[]} />);

    expect(labels()).toEqual(["📄 Handbook (nessuna sezione citata)"]);
  });

  it("analisi dati: etichetta dedicata", () => {
    render(<ToolBadges toolsUsed={["analyze_data"]} sources={[]} />);

    expect(labels()).toEqual(["📊 Analisi dati"]);
  });

  it("entrambi gli strumenti: etichette nell'ordine di toolsUsed", () => {
    render(
      <ToolBadges
        toolsUsed={["search_handbook", "analyze_data"]}
        sources={[{ section: "4. Dati" }]}
      />,
    );

    expect(labels()).toEqual(["📄 Handbook — 4. Dati", "📊 Analisi dati"]);
  });

  it("nessuno strumento: non rende nulla", () => {
    const { container } = render(<ToolBadges toolsUsed={[]} sources={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("uno strumento sconosciuto viene ignorato", () => {
    render(
      <ToolBadges
        toolsUsed={["nuovo_strumento", "analyze_data"]}
        sources={[]}
      />,
    );

    expect(labels()).toEqual(["📊 Analisi dati"]);
  });
});
