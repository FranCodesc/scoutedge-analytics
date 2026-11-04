import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChartImage from "../src/components/ChartImage";

const SRC = "http://api.test/charts/chart_ab12cd34.png";
const ALT = "Grafico generato dall'analisi dei dati";
const FALLBACK = "Il grafico non è al momento disponibile.";

describe("ChartImage", () => {
  it("mostra l'immagine e avvisa quando si è caricata", () => {
    const onLoad = vi.fn();
    render(<ChartImage src={SRC} onLoad={onLoad} />);

    const img = screen.getByAltText(ALT);
    expect(img).toHaveAttribute("src", SRC);
    expect(screen.queryByText(FALLBACK)).toBeNull();

    fireEvent.load(img);
    expect(onLoad).toHaveBeenCalledTimes(1);
  });

  it("se l'immagine non si carica compare il testo di riserva, senza nuove richieste", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const onLoad = vi.fn();
    render(<ChartImage src={SRC} onLoad={onLoad} />);

    fireEvent.error(screen.getByAltText(ALT));

    expect(screen.getByText(FALLBACK)).toBeInTheDocument();
    expect(screen.queryByAltText(ALT)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onLoad).not.toHaveBeenCalled();
  });
});
