import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ChartDialog from "../src/components/ChartDialog";

const SRC = "http://api.test/charts/chart_ab12cd34.png";
const ALT = "Grafico generato dall'analisi dei dati";
const FALLBACK = "Il grafico non è al momento disponibile.";

describe("ChartDialog", () => {
  it("si apre al montaggio e mostra il grafico", () => {
    render(<ChartDialog src={SRC} onClose={() => {}} />);

    const dialog = screen.getByRole("dialog", { name: "Grafico ingrandito" });
    expect(dialog).toHaveAttribute("open");
    expect(screen.getByAltText(ALT)).toHaveAttribute("src", SRC);
  });

  it("il pulsante Chiudi chiude la finestra e avvisa chi l'ha montata", async () => {
    const onClose = vi.fn();
    render(<ChartDialog src={SRC} onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Chiudi" }));

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("se l'immagine non si carica: testo di riserva, finestra aperta, nessuna nuova richiesta", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const onClose = vi.fn();
    render(<ChartDialog src={SRC} onClose={onClose} />);

    fireEvent.error(screen.getByAltText(ALT));

    expect(screen.getByText(FALLBACK)).toBeInTheDocument();
    expect(screen.queryByAltText(ALT)).toBeNull();
    // La finestra resta aperta e si può chiudere con il pulsante.
    expect(screen.getByRole("dialog")).toHaveAttribute("open");
    expect(screen.getByRole("button", { name: "Chiudi" })).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
