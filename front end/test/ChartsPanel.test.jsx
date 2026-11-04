import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChartsPanel from "../src/components/ChartsPanel";

const SRC = "http://api.test/charts/chart_ab12cd34.png";
const OTHER = "http://api.test/charts/chart_00ff00ff.png";
const ALT = "Grafico generato dall'analisi dei dati";
const FALLBACK = "Il grafico non è al momento disponibile.";

const zoomButton = () => screen.getByRole("button", { name: "Ingrandisci" });
const downloadButton = () => screen.getByRole("button", { name: "Scarica" });

describe("ChartsPanel", () => {
  it("senza grafico mostra lo stato vuoto e spegne i pulsanti", () => {
    render(<ChartsPanel src={null} onZoom={() => {}} onDownload={() => {}} />);

    expect(screen.getByText("Nessun grafico ancora")).toBeInTheDocument();
    expect(screen.queryByAltText(ALT)).toBeNull();
    expect(zoomButton()).toBeDisabled();
    expect(downloadButton()).toBeDisabled();
  });

  it("con un grafico mostra l'immagine e i pulsanti funzionano", () => {
    const onZoom = vi.fn();
    const onDownload = vi.fn();
    render(<ChartsPanel src={SRC} onZoom={onZoom} onDownload={onDownload} />);

    expect(screen.getByAltText(ALT)).toHaveAttribute("src", SRC);
    fireEvent.click(zoomButton());
    fireEvent.click(downloadButton());
    fireEvent.click(
      screen.getByRole("button", { name: "Ingrandisci il grafico" }),
    );

    expect(onZoom).toHaveBeenCalledTimes(2);
    expect(onDownload).toHaveBeenCalledTimes(1);
  });

  it("se l'immagine non si carica: testo di riserva, pulsanti spenti, nessuna nuova richiesta", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<ChartsPanel src={SRC} onZoom={() => {}} onDownload={() => {}} />);

    fireEvent.error(screen.getByAltText(ALT));

    expect(screen.getByText(FALLBACK)).toBeInTheDocument();
    expect(screen.queryByAltText(ALT)).toBeNull();
    expect(zoomButton()).toBeDisabled();
    expect(downloadButton()).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("un grafico nuovo dopo un errore viene mostrato di nuovo", () => {
    const { rerender } = render(
      <ChartsPanel src={SRC} onZoom={() => {}} onDownload={() => {}} />,
    );
    fireEvent.error(screen.getByAltText(ALT));
    expect(screen.getByText(FALLBACK)).toBeInTheDocument();

    rerender(
      <ChartsPanel src={OTHER} onZoom={() => {}} onDownload={() => {}} />,
    );

    expect(screen.queryByText(FALLBACK)).toBeNull();
    expect(screen.getByAltText(ALT)).toHaveAttribute("src", OTHER);
    expect(zoomButton()).toBeEnabled();
  });

  it("mostra l'errore di download e spegne 'Scarica' durante il download", () => {
    render(
      <ChartsPanel
        src={SRC}
        onZoom={() => {}}
        onDownload={() => {}}
        downloading
        downloadError="Il grafico non può essere scaricato."
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Il grafico non può essere scaricato.",
    );
    expect(downloadButton()).toBeDisabled();
  });
});
